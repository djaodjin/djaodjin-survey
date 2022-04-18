# Copyright (c) 2021, DjaoDjin inc.
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

from django.db import transaction
from django.db.models import Q
from rest_framework import generics
from rest_framework.mixins import DestroyModelMixin
from rest_framework.response import Response as HttpResponse

from .. import signals
from ..mixins import AccountMixin
from ..models import PortfolioDoubleOptIn
from .serializers import (PortfolioOptInSerializer,
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
                    "account": "supplier-1",
                    "grantee": "energy-utility",
                    "endst_at": "2018-01-01T00:00:00Z",
                    "accept_api_url":"http://localhost:8000/api/energy-utility/\
portfolios/0123456789abcdef",
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

        GET /api/envconnect/grants HTTP/1.1

    responds

    .. code-block:: json

        {
            "count": 1,
            "next": null,
            "previous": null,
            "results": [
                {
                    "account": "supplier-1",
                    "grantee": "energy-utility",
                    "endst_at": "2018-01-01T00:00:00Z",
                    "accept_api_url":"http://localhost:8000/api/energy-utility/\
portfolios/0123456789abcdef",
                 }
            ]
        }
    """
    serializer_class = PortfolioOptInSerializer

    def get_queryset(self):
        return PortfolioDoubleOptIn.objects.filter(
            Q(account=self.account) &
            Q(state=PortfolioDoubleOptIn.OPTIN_GRANT_INITIATED))

    def post(self, request, *args, **kwargs):
        """
        Initiates a grant

        Initiate a grant of data to a grantee

        **Tags**: portfolios

        **Examples**

        .. code-block:: http

            POST /api/supplier-1/grants HTTP/1.1

        .. code-block:: json

            {
               "grantee": "energy-utility"
            }

        responds

        .. code-block:: json

            {}
        """
        return self.create(request, *args, **kwargs)

    def get_serializer_class(self):
        if self.request.method.lower() == 'post':
            return PortfolioGrantCreateSerializer
        return super(PortfoliosGrantsAPIView, self).get_serializer_class()

    def perform_create(self, serializer):
        created_at = datetime_or_now()
        # If we don't make a copy, we will get an exception "Got KeyError
        # when attempting to get a value for field `slug`" later on in
        # `get_success_headers`.
        grantee_data = {}
        grantee_data.update(serializer.validated_data['grantee'])
        campaign = serializer.validated_data.get('campaign')
        accounts = serializer.validated_data.get('accounts', [])
        defaults = {
            'initiated_by': self.request.user,
            'state': PortfolioDoubleOptIn.OPTIN_GRANT_INITIATED,
            'ends_at': created_at
        }
        grantee_slug = grantee_data.pop('slug')
        grantee, unused_created = get_account_model().objects.get_or_create(
            slug=grantee_slug, defaults=grantee_data)
        if accounts:
            for account in accounts:
                # XXX assert self.account has access to `account`
                portfolio, unused_created = \
                    PortfolioDoubleOptIn.objects.update_or_create(
                        account=account,
                        grantee=grantee,
                        campaign=campaign,
                        defaults=defaults)
                signals.portfolio_grant_initiated.send(sender=__name__,
                    portfolio=portfolio, request=self.request)

        else:
            serializer.instance = PortfolioDoubleOptIn.objects.update_or_create(
                account=self.account,
                grantee=grantee,
                campaign=campaign,
                defaults=defaults)
            signals.portfolio_grant_initiated.send(sender=__name__,
                portfolio=serializer.instance, request=self.request)


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

        POST /api/envconnect/grants/0123456789abcef HTTP/1.1

    responds

    .. code-block:: json

        {}
    """
    serializer_class = PortfolioOptInSerializer
    lookup_url_kwarg = 'verification_key'

    def get_queryset(self):
        return PortfolioDoubleOptIn.objects.filter(grantee=self.account)

    def post(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_create(instance)
        return HttpResponse(status=status.HTTP_201_CREATED)

    def delete(self, request, *args, **kwargs):
        """
        Denies a portfolio grant

        **Tags**: portfolios

        **Examples**

        .. code-block:: http

            DELETE /api/envconnect/grants/0123456789abcef HTTP/1.1
        """
        return self.destroy(request, *args, **kwargs)

    def perform_create(self, instance):
        with transaction.atomic():
            instance.create_portfolios()
            instance.state = PortfolioDoubleOptIn.OPTIN_GRANT_ACCEPTED
            instance.save()
            signals.portfolio_grant_accepted.send(sender=__name__,
                portfolio=instance, request=self.request)

    def perform_destroy(self, instance):
        instance.state = PortfolioDoubleOptIn.OPTIN_GRANT_DENIED
        instance.save()
        signals.portfolio_grant_denied.send(sender=__name__,
            portfolio=instance, request=self.request)


class PortfoliosRequestsAPIView(SmartPortfolioListMixin,
                                generics.ListCreateAPIView):
    """
    Lists initiated requests

    Lists all requests currently pending initiated by *account*.

    **Tags**: portfolios

    **Examples**

    .. code-block:: http

        GET /api/envconnect/requests HTTP/1.1

    responds

    .. code-block:: json

        {
            "count": 1,
            "next": null,
            "previous": null,
            "results": [
                {
                    "account": "supplier-1",
                    "grantee": "energy-utility",
                    "endst_at": "2018-01-01T00:00:00Z",
                    "accept_api_url":"http://localhost:8000/api/energy-utility/\
portfolios/0123456789abcdef",
                 }
            ]
        }
    """
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

            POST /api/energy-utility/requests HTTP/1.1

        .. code-block:: json

            {
               "account": "supplier-1"
            }

        responds

        .. code-block:: json

            {}
        """
        return self.create(request, *args, **kwargs)

    def get_serializer_class(self):
        if self.request.method.lower() == 'post':
            return PortfolioRequestCreateSerializer
        return super(PortfoliosRequestsAPIView, self).get_serializer_class()

    def perform_create(self, serializer):
        defaults = {
            'state': PortfolioDoubleOptIn.OPTIN_REQUEST_INITIATED,
            'ends_at': datetime_or_now(),
            'initiated_by': self.request.user
        }
        accounts = serializer.validated_data['accounts']
        for account in accounts:
            account, unused_created = get_account_model().objects.get_or_create(
                slug=account.get('slug'),
                defaults={
                    'email': account.get('email')
                })
            portfolio, unused_created = \
                PortfolioDoubleOptIn.objects.update_or_create(
                    grantee=self.account,
                    account=account,
                    campaign=serializer.validated_data.get('campaign'),
                    defaults=defaults)
            signals.portfolio_requests_initiated.send(sender=__name__,
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

        POST /api/envconnect/requests/0123456789abcef HTTP/1.1

    responds

    .. code-block:: json

        {}
    """
    serializer_class = PortfolioOptInSerializer
    lookup_url_kwarg = 'verification_key'

    def get_queryset(self):
        return PortfolioDoubleOptIn.objects.filter(account=self.account)

    def post(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_create(instance)
        return HttpResponse(status=status.HTTP_201_CREATED)

    def delete(self, request, *args, **kwargs):
        """
        Denies a portfolio request

        **Tags**: portfolios

        **Examples**

        .. code-block:: http

            DELETE /api/envconnect/requests/0123456789abcef HTTP/1.1
        """
        return self.destroy(request, *args, **kwargs)

    def perform_create(self, instance):
        with transaction.atomic():
            instance.create_portfolios()
            instance.state = \
                PortfolioDoubleOptIn.OPTIN_REQUEST_ACCEPTED
            instance.save()
            signals.portfolio_request_accepted.send(sender=__name__,
                portfolio=instance, request=self.request)

    def perform_destroy(self, instance):
        instance.state = PortfolioDoubleOptIn.OPTIN_REQUEST_DENIED
        instance.save()
        signals.portfolio_request_denied.send(sender=__name__,
            portfolio=instance, request=self.request)
