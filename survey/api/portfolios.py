# Copyright (c) 2022, DjaoDjin inc.
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

import logging

from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.db.models import Q
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response as HttpResponse

from .. import settings, signals
from ..compat import six, gettext_lazy as _
from ..docs import OpenAPIResponse, swagger_auto_schema
from ..mixins import AccountMixin
from ..models import PortfolioDoubleOptIn
from .serializers import (NoModelSerializer, PortfolioOptInSerializer,
    PortfolioGrantCreateSerializer, PortfolioRequestCreateSerializer)
from ..filters import (DateRangeFilter, DoubleOptInStateFilter, OrderingFilter,
     SearchFilter)
from ..utils import datetime_or_now, get_account_model


LOGGER = logging.getLogger(__name__)


class SmartPortfolioListMixin(AccountMixin):

    serializer_class = PortfolioOptInSerializer

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
    Lists grants and requests to be accepted/denied

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
                "campaign": "sustainability",
                "ends_at": "2022-01-01T00:00:00Z",
                "state": "request-initiated",
                "api_accept": "/api/supplier-1/portfolios/requests/\
0000000000000000000000000000000000000002/"
              }
            ]
        }
    """

    def get_queryset(self):
        return PortfolioDoubleOptIn.objects.filter(
            (Q(account=self.account) &
            Q(state=PortfolioDoubleOptIn.OPTIN_REQUEST_INITIATED)) |
            (Q(grantee=self.account) &
            Q(state=PortfolioDoubleOptIn.OPTIN_GRANT_INITIATED)))


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
                  "campaign": "sustainability",
                  "ends_at": "2022-01-01T00:00:00Z",
                  "state": "grant-initiated",
                  "api_accept": "/api/water-utility/portfolios/grants\
/0000000000000000000000000000000000000003/"
                 }
            ]
        }
    """
    serializer_class = PortfolioOptInSerializer
    lookup_field = settings.ACCOUNT_LOOKUP_FIELD

    def get_queryset(self):
        return PortfolioDoubleOptIn.objects.filter(
            Q(account=self.account) &
            Q(state=PortfolioDoubleOptIn.OPTIN_GRANT_INITIATED))

    def get_serializer_class(self):
        if self.request.method.lower() == 'post':
            return PortfolioGrantCreateSerializer
        return super(PortfoliosGrantsAPIView, self).get_serializer_class()

    @swagger_auto_schema(responses={
        201: OpenAPIResponse("Create successful", PortfolioOptInSerializer,
        many=True)})
    def post(self, request, *args, **kwargs):
        """
        Initiates a grant

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
               "grantee": {
                 "slug": "energy-utility",
                 "full_name": "Energy Utility"
               }
            }
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        #pylint:disable=too-many-locals
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
        model_fields = set([
            field.name for field in account_model._meta.get_fields()])
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
        signals.portfolios_grant_initiated.send(sender=__name__,
            portfolios=portfolios, invitee=grantee_data, request=self.request)

        results = []
        serializer_class = PortfolioOptInSerializer
        serializer_kwargs = {'context': self.get_serializer_context()}
        serializer = serializer_class(**serializer_kwargs)
        for portfolio in portfolios:
            results += [serializer.to_representation(portfolio)]

        return HttpResponse(results, status=status_code)


class PortfoliosGrantAcceptAPIView(AccountMixin, generics.DestroyAPIView):
    """
    Accepts a portfolio grant

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

    .. code-block:: json

        {}

    responds

    .. code-block:: json

        {}
    """
    lookup_field = 'verification_key'
    serializer_class = NoModelSerializer

    def get_queryset(self):
        return PortfolioDoubleOptIn.objects.filter(grantee=self.account)

    def post(self, request, *args, **kwargs):
        #pylint:disable=unused-argument
        instance = self.get_object()
        self.perform_create(instance)
        return HttpResponse(status=status.HTTP_201_CREATED)

    def delete(self, request, *args, **kwargs):
        """
        Denies or removes a portfolio grant

        **Tags**: portfolios

        **Examples**

        .. code-block:: http

            DELETE /api/energy-utility/portfolios/grants/0123456789abcef\
 HTTP/1.1
        """
        filter_args = {self.lookup_field: self.kwargs.get(self.lookup_field)}
        try:
            instance = self.get_queryset().get(**filter_args)
            instance.state = PortfolioDoubleOptIn.OPTIN_GRANT_DENIED
            instance.save()
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
                "campaign": "sustainability",
                "ends_at": "2022-01-01T00:00:00Z",
                "state": "request-denied",
                "api_accept": null
              },
              {
                "grantee": "energy-utility",
                "account": "supplier-1",
                "campaign": "sustainability",
                "ends_at": "2022-01-01T00:00:00Z",
                "state": "request-initiated",
                "api_accept": "/api/supplier-1/portfolios/requests/\
0000000000000000000000000000000000000002/"
              },
              {
                "grantee": "energy-utility",
                "account": "andy-shop",
                "campaign": "sustainability",
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
        return PortfolioDoubleOptIn.objects.filter(grantee=self.account)

    def post(self, request, *args, **kwargs):
        """
        Initiates a request

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
        account_model = get_account_model()
        ends_at = datetime_or_now()
        defaults = {
            'state': PortfolioDoubleOptIn.OPTIN_REQUEST_INITIATED,
            'ends_at': ends_at,
            'initiated_by': self.request.user
        }
        accounts = serializer.validated_data['accounts']
        requests_initiated = []
        with transaction.atomic():
            for account in accounts:
                lookups = {self.lookup_field: account.get('slug')}
                account, unused_created = account_model.objects.get_or_create(
                    defaults={
                        'email': account.get('email')
                    }, **lookups)
                campaign = serializer.validated_data.get('campaign')
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
                        **defaults)
                requests_initiated += [(portfolio, account)]

        for request in requests_initiated:
            portfolio = request[0]
            account = request[1]
            signals.portfolio_request_initiated.send(sender=__name__,
                portfolio=portfolio, invitee=account, request=self.request)


class PortfoliosRequestAcceptAPIView(AccountMixin, generics.DestroyAPIView):
    """
    Accepts a portfolio request

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

    .. code-block:: json

        {}

    responds

    .. code-block:: json

        {}
    """
#    lookup_url_kwarg = 'verification_key'
    lookup_field = 'verification_key'
    serializer_class = NoModelSerializer

    def get_queryset(self):
        return PortfolioDoubleOptIn.objects.filter(account=self.account)

    def post(self, request, *args, **kwargs):
        #pylint:disable=unused-argument
        instance = self.get_object()
        self.perform_create(instance)
        return HttpResponse(status=status.HTTP_201_CREATED)

    def delete(self, request, *args, **kwargs):
        """
        Denies a portfolio request

        **Tags**: portfolios

        **Examples**

        .. code-block:: http

            DELETE /api/supplier-1/portfolios/requests/0123456789abcef\
 HTTP/1.1
        """
        return self.destroy(request, *args, **kwargs)

    def perform_create(self, instance):
        instance.request_accepted()
        signals.portfolio_request_accepted.send(sender=__name__,
            portfolio=instance, request=self.request)

    def perform_destroy(self, instance):
        instance.state = PortfolioDoubleOptIn.OPTIN_REQUEST_DENIED
        instance.save()
        signals.portfolio_request_denied.send(sender=__name__,
            portfolio=instance, request=self.request)
