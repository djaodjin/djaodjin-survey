# Copyright (c) 2024, DjaoDjin inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED
# TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
# PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
# CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS;
# OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
# WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR
# OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
# ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import datetime, logging

from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.db.models import Max, Q
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response as HttpResponse

from .. import settings, signals
from ..compat import six, timezone_or_utc, gettext_lazy as _
from ..docs import OpenApiResponse, extend_schema
from ..helpers import datetime_or_now
from ..mixins import AccountMixin, DateRangeContextMixin
from ..models import Portfolio, PortfolioDoubleOptIn, Sample
from .serializers import (PortfolioReceivedSerializer,
    PortfolioOptInSerializer, PortfolioOptInUpdateSerializer,
    PortfolioGrantCreateSerializer, PortfolioRequestCreateSerializer)
from ..filters import (DateRangeFilter, DoubleOptInStateFilter, OrderingFilter,
     SearchFilter)
from ..utils import get_account_model


LOGGER = logging.getLogger(__name__)


class SmartPortfolioListMixin(AccountMixin):

    search_fields = (
        'grantee__full_name',
        'account__full_name',
    )

    ordering_fields = [
        ('grantee__full_name', 'grantee'),
        ('account__full_name', 'account'),
        ('state', 'state'),
        ('ends_at', 'ends_at'),
    ]

    ordering = ('ends_at',)

    filter_backends = (DoubleOptInStateFilter, DateRangeFilter, SearchFilter,
        OrderingFilter)


class PortfoliosAPIView(SmartPortfolioListMixin, generics.ListAPIView):
    """
    Lists active grants and requests

    Lists all grants and requests that have to be accepted or denied
    by *account*.

    If you want to get all requests that have been initiated by *account*,
    see /api/{account}/requests. If you want to get all grants that have been
    initiated *account*, see /api/{account}/grants.

    **Tags**: portfolios

    **Examples**

    .. code-block:: http

        GET /api/energy-utility/portfolios HTTP/1.1

    responds

    .. code-block:: json

        {
            "count": 1,
            "next": null,
            "previous": null,
            "results": [
              {
                "grantee": "energy-utility",
                "account": "supplier-1",
                "campaign": {
                    "slug": "sustainability",
                    "title": "ESG/Environmental practices",
                    "account": "djaopsp"
                },
                "ends_at": "2022-01-01T00:00:00Z",
                "state": "request-initiated",
                "api_accept": "/api/supplier-1/portfolios/requests/\
0000000000000000000000000000000000000002/"
              }
            ]
        }
    """
    serializer_class = PortfolioReceivedSerializer

    def decorate_queryset(self, queryset):
        latest_frozen_by_campaigns = {}
        latest_shared_by_campaigns = {}
        for optin in queryset:
            campaign = optin.campaign
            query_kwargs = {'campaign': campaign} if campaign else {}
            optin.expected_behavior = optin.EXPECTED_CREATE
            if campaign:
                latest_frozen_at = latest_frozen_by_campaigns.get(campaign)
                if (not latest_frozen_at and
                    campaign not in latest_frozen_by_campaigns):
                    latest_frozen_at = Sample.objects.filter(
                        account=self.account, is_frozen=True,
                        **query_kwargs).aggregate(Max('created_at'))
                    if latest_frozen_at:
                        latest_frozen_at = latest_frozen_at.get(
                            'created_at__max')
                    latest_frozen_by_campaigns.update({
                        campaign: latest_frozen_at})

                latest_shared_at = latest_shared_by_campaigns.get(campaign)
                if (not latest_shared_at and
                    campaign not in latest_shared_by_campaigns):
                    latest_shared_at = Portfolio.objects.filter(
                        account=self.account, grantee=optin.grantee,
                        **query_kwargs).aggregate(Max('ends_at'))
                    if latest_shared_at:
                        latest_shared_at = latest_shared_at.get('ends_at__max')
                    latest_shared_by_campaigns.update({
                        campaign: latest_shared_at})

                # compute expected behavior
                if not latest_frozen_at:
                    optin.expected_behavior = optin.EXPECTED_CREATE
                elif (latest_shared_at and
                      latest_frozen_at < latest_shared_at and
                      latest_shared_at < optin.created_at):
                    optin.expected_behavior = optin.EXPECTED_UPDATE
                else:
                    optin.expected_behavior = optin.EXPECTED_SHARE

        return queryset


    def get_queryset(self):
        return PortfolioDoubleOptIn.objects.pending_for(self.account)

    def paginate_queryset(self, queryset):
        page = super(PortfoliosAPIView, self).paginate_queryset(queryset)
        return self.decorate_queryset(page if page else queryset)


class PortfoliosGrantsAPIView(SmartPortfolioListMixin,
                              generics.ListCreateAPIView):
    """
    Lists initiated grants

    Lists all grants currently pending initiated by *account*.

    **Tags**: portfolios

    **Examples**

    .. code-block:: http

        GET /api/supplier-1/portfolios/grants HTTP/1.1

    responds

    .. code-block:: json

        {
            "count": 1,
            "next": null,
            "previous": null,
            "results": [
                {
                  "grantee": "water-utility",
                  "account": "supplier-1",
                  "campaign": {
                      "slug": "sustainability",
                      "title": "ESG/Environmental practices",
                      "account": "djaopsp"
                  },
                  "ends_at": "2022-01-01T00:00:00Z",
                  "state": "grant-initiated",
                  "api_accept": "/api/water-utility/portfolios/grants\
/0000000000000000000000000000000000000003/"
                 }
            ]
        }
    """
    lookup_field = settings.ACCOUNT_LOOKUP_FIELD
    serializer_class = PortfolioOptInSerializer

    def get_queryset(self):
        return PortfolioDoubleOptIn.objects.filter(
            Q(account=self.account) &
            Q(state=PortfolioDoubleOptIn.OPTIN_GRANT_INITIATED))

    def get_serializer_class(self):
        if self.request.method.lower() == 'post':
            return PortfolioGrantCreateSerializer
        return super(PortfoliosGrantsAPIView, self).get_serializer_class()

    @extend_schema(responses={
        201: OpenApiResponse(PortfolioOptInSerializer(many=True))})
    def post(self, request, *args, **kwargs):
        """
        Initiates grant

        Initiate a grant of data to a grantee

        **Tags**: portfolios

        **Examples**

        .. code-block:: http

            POST /api/supplier-1/portfolios/grants HTTP/1.1

        .. code-block:: json

            {
               "grantee": {
                 "slug": "energy-utility",
                 "full_name": "Energy Utility"
               }
            }

        responds

        .. code-block:: json

            {
               "count": 1,
               "results": [{
                 "grantee": "water-utility",
                 "account": "supplier-1",
                 "campaign": null,
                 "ends_at": "2022-01-01T00:00:00Z",
                 "state": "grant-initiated",
                 "api_accept": "/api/water-utility/portfolios/grants\
/0000000000000000000000000000000000000003/"
               }]
            }
        """
        #pylint:disable=too-many-locals
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        created_at = datetime_or_now()
        # If we don't make a copy, we will get an exception "Got KeyError
        # when attempting to get a value for field `slug`" later on in
        # `get_success_headers`.
        grantee_data = {}
        grantee_data.update(serializer.validated_data['grantee'])
        campaign = serializer.validated_data.get('campaign')

        # Django1.11: we need to remove invalid fields when creating
        # a new grantee account otherwise Django1.11 will raise an error.
        # This is not the case with Django>=3.2
        account_model = get_account_model()
        lookups = {self.lookup_field: grantee_data.pop('slug')}
        invalid_fields = []
        # set comprehension py2.7+ syntax
        model_fields = {
            field.name for field in account_model._meta.get_fields()}
        for field_name in six.iterkeys(grantee_data):
            if field_name not in model_fields:
                invalid_fields += [field_name]
        for field_name in invalid_fields:
            grantee_data.pop(field_name)
        grantee, unused_created = account_model.objects.get_or_create(
            defaults=grantee_data, **lookups)

        accounts = []
        # XXX assert self.account has access to each account in `accounts`.
        # accounts = serializer.validated_data.get('accounts', [])
        if not accounts:
            accounts = [self.account]

        # Attempting to grant access to itself is an error.
        for account in accounts:
            if account == grantee:
                raise ValidationError({'grantee': _("The profile already has"\
                    " access to the data you are trying to share.")})

        status_code = status.HTTP_200_OK
        ends_at = created_at + relativedelta(months=4)
        portfolios = []
        requests_accepted = []
        with transaction.atomic():
            for account in accounts:
                # If we have a pending grant initiated, we actualize it.
                portfolio = PortfolioDoubleOptIn.objects.filter(
                    Q(account=account) &
                    Q(grantee=grantee) &
                    Q(campaign=campaign) &
                    Q(state=PortfolioDoubleOptIn.OPTIN_GRANT_INITIATED)
                ).first()
                if portfolio:
                    portfolio.initiated_by = self.request.user
                    portfolio.created_at = created_at
                    portfolio.ends_at = ends_at
                    portfolio.save()
                    portfolios += [portfolio]
                else:
                    # If we have a pending request initiated, we grant it.
                    portfolio = PortfolioDoubleOptIn.objects.filter(
                        Q(account=account) &
                        Q(grantee=grantee) &
                        Q(campaign=campaign) &
                        Q(state=PortfolioDoubleOptIn.OPTIN_REQUEST_INITIATED)
                    ).first()
                    if portfolio:
                        portfolio.request_accepted()
                        requests_accepted += [portfolio]
                    else:
                        portfolio = PortfolioDoubleOptIn.objects.create(
                            created_at=created_at,
                            ends_at=ends_at,
                            account=account,
                            grantee=grantee,
                            campaign=campaign,
                            initiated_by=self.request.user,
                            state=PortfolioDoubleOptIn.OPTIN_GRANT_INITIATED,
                            verification_key=PortfolioDoubleOptIn.generate_key(
                                account))
                        status_code = status.HTTP_201_CREATED
                portfolios += [portfolio]

        for portfolio in requests_accepted:
            signals.portfolio_request_accepted.send(sender=__name__,
                portfolio=portfolio, request=self.request)

        message = serializer.validated_data.get('message')
        recipients = [grantee_data] if grantee_data.get('email') else []
        signals.portfolios_grant_initiated.send(sender=__name__,
            portfolios=portfolios, recipients=recipients, message=message,
            request=self.request)

        results = []
        serializer_class = PortfolioOptInSerializer
        serializer_kwargs = {'context': self.get_serializer_context()}
        serializer = serializer_class(**serializer_kwargs)
        for portfolio in portfolios:
            results += [serializer.to_representation(portfolio)]

        return HttpResponse(results, status=status_code)


class PortfoliosGrantAcceptAPIView(AccountMixin, generics.DestroyAPIView):
    """
    Accepts grant

    An `account` has sent its portfolio to a `grantee`. The `grantee`
    accepts the request, making the `account`'s answers up-to-date `ends_at`
    available to `grantee`.

    Note that *account* parameter is the `grantee` we have send data to here,
    while the *account* parameter is the `account` owning that data  when
    calling `POST /api/{account}/grants`.

    **Tags**: portfolios

    **Examples**

    .. code-block:: http

        POST /api/energy-utility/portfolios/grants/0123456789abcef HTTP/1.1

    responds

    .. code-block:: json

        {
            "grantee": "energy-utility",
            "account": "supplier-1",
            "campaign": {
                "slug": "sustainability",
                "title": "ESG/Environmental practices",
                "account": "djaopsp"
            },
            "ends_at": "2025-01-01T00:00:00Z",
            "state": "grant-accepted"
        }
    """
    lookup_field = 'verification_key'
    serializer_class = PortfolioOptInSerializer

    def get_queryset(self):
        # Look up grant to be accepted through the 'verification_key'
        # so it OK to just filter by grantee.
        return PortfolioDoubleOptIn.objects.filter(grantee=self.account)

    @extend_schema(operation_id='portfolios_grants_accept', request=None)
    def post(self, request, *args, **kwargs):
        #pylint:disable=unused-argument
        instance = self.get_object()
        self.perform_create(instance)
        serializer = self.get_serializer(instance=instance)
        return HttpResponse(serializer.to_representation(instance),
            status=status.HTTP_201_CREATED)

    def delete(self, request, *args, **kwargs):
        """
        Ignores grant

        **Tags**: portfolios

        **Examples**

        .. code-block:: http

            DELETE /api/energy-utility/portfolios/grants/0123456789abcef\
 HTTP/1.1
        """
        filter_args = {self.lookup_field: self.kwargs.get(self.lookup_field)}
        try:
            instance = self.get_queryset().get(**filter_args)
            instance.grant_denied()
            signals.portfolio_grant_denied.send(sender=__name__,
                portfolio=instance, request=self.request)
            return HttpResponse(status=status.HTTP_204_NO_CONTENT)

        except PortfolioDoubleOptIn.DoesNotExist:
            pass

        # We cannot find the grant to the grantee, so let's look
        # if the grant was removed by any chance.
        instance = generics.get_object_or_404(
            PortfolioDoubleOptIn.objects.filter(account=self.account),
            **filter_args)
        instance.delete()
        return HttpResponse(status=status.HTTP_204_NO_CONTENT)

    def perform_create(self, instance):
        instance.grant_accepted()
        signals.portfolio_grant_accepted.send(sender=__name__,
            portfolio=instance, request=self.request)


class PortfoliosRequestsAPIView(SmartPortfolioListMixin,
                                generics.ListCreateAPIView):
    """
    Lists initiated requests

    Lists all requests currently pending initiated by *account*.

    **Tags**: portfolios

    **Examples**

    .. code-block:: http

        GET /api/energy-utility/portfolios/requests HTTP/1.1

    responds

    .. code-block:: json

        {
            "count": 3,
            "next": null,
            "previous": null,
            "results": [
              {
                "grantee": "energy-utility",
                "account": "supplier-1",
                "campaign": {
                    "slug": "sustainability",
                    "title": "ESG/Environmental practices",
                    "account": "djaopsp"
                },
                "ends_at": "2022-01-01T00:00:00Z",
                "state": "request-denied",
                "api_accept": null
              },
              {
                "grantee": "energy-utility",
                "account": "supplier-1",
                "campaign": {
                    "slug": "sustainability",
                    "title": "ESG/Environmental practices",
                    "account": "djaopsp"
                },
                "ends_at": "2022-01-01T00:00:00Z",
                "state": "request-initiated",
                "api_accept": "/api/supplier-1/portfolios/requests/\
0000000000000000000000000000000000000002/"
              },
              {
                "grantee": "energy-utility",
                "account": "andy-shop",
                "campaign": {
                    "slug": "sustainability",
                    "title": "ESG/Environmental practices",
                    "account": "djaopsp"
                },
                "ends_at": "2022-01-01T00:00:00Z",
                "state": "request-initiated",
                "api_accept": "/api/andy-shop/portfolios/requests/\
0000000000000000000000000000000000000004/"
              }
            ]
        }
    """
    lookup_field = settings.ACCOUNT_LOOKUP_FIELD
    serializer_class = PortfolioOptInSerializer

    def get_queryset(self):
        # Look up request to be accepted through the 'verification_key'
        # so it OK to just filter by grantee.
        return PortfolioDoubleOptIn.objects.filter(grantee=self.account)

    def post(self, request, *args, **kwargs):
        """
        Initiates request

        Initiate a request of data for an account.

        **Tags**: portfolios

        **Examples**

        .. code-block:: http

            POST /api/energy-utility/portfolios/requests HTTP/1.1

        .. code-block:: json

            {
               "accounts": [
                 {
                   "slug": "supplier-1",
                   "full_name": "Supplier 1"
                 }
               ]
            }

        responds

        .. code-block:: json

            {
               "accounts": [
                 {
                   "slug": "supplier-1",
                   "full_name": "Supplier 1"
                 }
               ]
             }
        """
        return self.create(request, *args, **kwargs)

    def get_serializer_class(self):
        if self.request.method.lower() == 'post':
            return PortfolioRequestCreateSerializer
        return super(PortfoliosRequestsAPIView, self).get_serializer_class()

    def perform_create(self, serializer):
        #pylint:disable=too-many-locals
        account_model = get_account_model()
        ends_at = datetime_or_now()
        defaults = {
            'state': PortfolioDoubleOptIn.OPTIN_REQUEST_INITIATED,
            'initiated_by': self.request.user
        }
        campaign = serializer.validated_data.get('campaign')
        accounts = serializer.validated_data['accounts']
        requests_initiated = []
        with transaction.atomic():
            for serialized_account in accounts:
                account_data = {}
                account_data.update(serialized_account)

                # Django1.11: we need to remove invalid fields when creating
                # a new grantee account otherwise Django1.11 will raise
                # an error.
                # This is not the case with Django>=3.2
                lookups = {self.lookup_field: account_data.pop('slug')}
                invalid_fields = []
                # set comprehension py2.7+ syntax
                model_fields = {
                    field.name for field in account_model._meta.get_fields()}
                for field_name in six.iterkeys(account_data):
                    if field_name not in model_fields:
                        invalid_fields += [field_name]
                for field_name in invalid_fields:
                    account_data.pop(field_name)
                account, unused_created = account_model.objects.get_or_create(
                    defaults=account_data, **lookups)

                double_optin_queryset = PortfolioDoubleOptIn.objects.filter(
                    Q(ends_at__isnull=True) | Q(ends_at__gt=ends_at),
                    grantee=self.account,
                    account=account,
                    campaign=campaign).order_by('-created_at')
                portfolio = double_optin_queryset.first()
                if portfolio:
                    portfolio.state = defaults.get('state')
                    portfolio.ends_at = defaults.get('ends_at')
                    portfolio.initiated_by = defaults.get('initiated_by')
                    portfolio.save()
                else:
                    portfolio = PortfolioDoubleOptIn.objects.create(
                        grantee=self.account,
                        account=account,
                        campaign=campaign,
                    verification_key=PortfolioDoubleOptIn.generate_key(account),
                        **defaults)
                requests_initiated += [(portfolio, [account_data])]

        message = serializer.validated_data.get('message')
        for request in requests_initiated:
            portfolio = request[0]
            recipients = request[1]
            signals.portfolios_request_initiated.send(sender=__name__,
                portfolios=[portfolio], recipients=recipients, message=message,
                request=self.request)


class PortfoliosRequestAcceptAPIView(AccountMixin, generics.DestroyAPIView):

    lookup_field = 'verification_key'
    serializer_class = PortfolioOptInSerializer

    def get_queryset(self):
        # Look up request to be accepted through the 'verification_key'
        # so it OK to just filter by account.
        return PortfolioDoubleOptIn.objects.filter(account=self.account)

    @extend_schema(operation_id='portfolios_requests_accept', request=None)
    def post(self, request, *args, **kwargs):
        """
        Accepts request

        A `grantee` has made a request to *account*'s portfolio. The *account*
        accepts the request, making the *account*'s answers up-to-date `ends_at`
        available to `grantee`.

        Note that *account* is the actual *account* we are looking to access data
        from here, while the *account* parameter is the `grantee` when calling
        `POST /api/{account}/requests`.

        **Tags**: portfolios

        **Examples**

        .. code-block:: http

            POST /api/supplier-1/portfolios/requests/0123456789abcef HTTP/1.1

        responds

        .. code-block:: json

            {
                "grantee": "energy-utility",
                "account": "supplier-1",
                "campaign": {
                    "slug": "sustainability",
                    "title": "ESG/Environmental practices",
                    "account": "djaopsp"
                },
                "ends_at": "2025-01-01T00:00:00Z",
                "state": "request-accepted"
            }
        """
        #pylint:disable=unused-argument
        instance = self.get_object()
        self.perform_create(instance)
        serializer = self.get_serializer(instance=instance)
        return HttpResponse(serializer.to_representation(instance),
            status=status.HTTP_201_CREATED)

    def perform_create(self, instance):
        instance.request_accepted()
        signals.portfolio_request_accepted.send(sender=__name__,
            portfolio=instance, request=self.request)

    def delete(self, request, *args, **kwargs):
        """
        Ignores request

        **Tags**: portfolios

        **Examples**

        .. code-block:: http

            DELETE /api/supplier-1/portfolios/requests/0123456789abcef\
 HTTP/1.1
        """
        filter_args = {self.lookup_field: self.kwargs.get(self.lookup_field)}
        try:
            instance = self.get_queryset().get(**filter_args)
            instance.request_denied()
            signals.portfolio_request_denied.send(sender=__name__,
                portfolio=instance, request=self.request)
            return HttpResponse(status=status.HTTP_204_NO_CONTENT)
        except PortfolioDoubleOptIn.DoesNotExist:
            pass

        # We cannot find the grant to the grantee, so let's look
        # if the grant was removed by any chance.
        instance = generics.get_object_or_404(
            PortfolioDoubleOptIn.objects.filter(grantee=self.account),
            **filter_args)
        instance.delete()
        return HttpResponse(status=status.HTTP_204_NO_CONTENT)


class PortfolioUpdateAPIView(AccountMixin, generics.UpdateAPIView):
    """
    Updates extra field in a portfolio

    The requestor/grantor uses this API call to add metadata about
    the request/grant.

    **Tags**: portfolios

    **Examples**

    .. code-block:: http

        PUT /api/energy-utility/portfolios/metadata/supplier-1 HTTP/1.1

    .. code-block:: json

        {
          "extra": {"tags": "tier1"}
        }

    responds

    .. code-block:: json

        {
          "grantee": "energy-utility",
          "account": "supplier-1",
          "campaign": {
              "slug": "sustainability",
              "title": "ESG/Environmental practices",
              "account": "djaopsp"
          },
          "ends_at": "2022-01-01T00:00:00Z",
          "state": "request-denied",
          "api_accept": null,
          "extra": {"tags": "tier1"}
        }
    """
    target_url_kwarg = 'target'
    serializer_class = PortfolioOptInSerializer

    def get_serializer_class(self):
        if self.request.method.lower() in ('put', 'patch'):
            return PortfolioOptInUpdateSerializer
        return super(PortfolioUpdateAPIView, self).get_serializer_class()

    @extend_schema(responses={
      200: OpenApiResponse(PortfolioOptInSerializer)})
    def put(self, request, *args, **kwargs):
        return super(PortfolioUpdateAPIView, self).put(
            request, *args, **kwargs)

    @extend_schema(responses={
      200: OpenApiResponse(PortfolioOptInSerializer)})
    def patch(self, request, *args, **kwargs):
        return super(PortfolioUpdateAPIView, self).patch(
            request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        serializer = self.get_serializer(data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        # If we have a portfolio, let's update the extra metadata.
        extra = serializer.validated_data.get('extra')
        portfolios = Portfolio.objects.filter(grantee=self.account,
            account__slug=self.kwargs.get(self.target_url_kwarg))
        if portfolios.exists():
            portfolios.update(extra=extra)
        else:
            account_model = get_account_model()
            account = generics.get_object_or_404(account_model,
                slug=self.kwargs.get(self.target_url_kwarg))
            Portfolio.objects.create(
                grantee=self.account,
                account=account,
                # This project didn't exist before 1970, so we are not
                # sharing any data inadvertently.
                ends_at=datetime.datetime.fromtimestamp(0,
                    tz=timezone_or_utc()),
                extra=extra)
        return HttpResponse(serializer.data)


class PortfolioDoubleOptinUpdateAPIView(DateRangeContextMixin,
                                        PortfolioUpdateAPIView):
    """
    Updates extra field in a request/grant

    The requestor/grantor uses this API call to add metadata about
    the request/grant.

    **Tags**: portfolios

    **Examples**

    .. code-block:: http

        PUT /api/energy-utility/portfolios/requests/metadata/supplier-1 HTTP/1.1

    .. code-block:: json

        {
          "extra": {"tags": "tier1"}
        }

    responds

    .. code-block:: json

        {
          "grantee": "energy-utility",
          "account": "supplier-1",
          "campaign": {
              "slug": "sustainability",
              "title": "ESG/Environmental practices",
              "account": "djaopsp"
          },
          "ends_at": "2022-01-01T00:00:00Z",
          "state": "request-denied",
          "api_accept": null,
          "extra": {"tags": "tier1"}
        }
    """
    target_url_kwarg = 'target'
    serializer_class = PortfolioOptInSerializer

    def get_serializer_class(self):
        if self.request.method.lower() in ('put', 'patch'):
            return PortfolioOptInUpdateSerializer
        return super(
            PortfolioDoubleOptinUpdateAPIView, self).get_serializer_class()

    @extend_schema(responses={
      200: OpenApiResponse(PortfolioOptInSerializer)})
    def put(self, request, *args, **kwargs):
        return super(PortfolioDoubleOptinUpdateAPIView, self).put(
            request, *args, **kwargs)

    @extend_schema(responses={
      200: OpenApiResponse(PortfolioOptInSerializer)})
    def patch(self, request, *args, **kwargs):
        return super(PortfolioDoubleOptinUpdateAPIView, self).patch(
            request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        serializer = self.get_serializer(data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        filter_kwargs = {}
        if self.start_at:
            filter_kwargs.update({'created_at__gte': self.start_at})
        if self.ends_at:
            filter_kwargs.update({'created_at__lt': self.ends_at})
        optins = PortfolioDoubleOptIn.objects.requested(self.account).filter(
            account__slug=self.kwargs.get(self.target_url_kwarg),
            **filter_kwargs)

        optins.update(extra=serializer.validated_data.get('extra'))

        last_optin = optins.order_by('-created_at').first()
        return HttpResponse(self.get_serializer(instance=last_optin).data)
