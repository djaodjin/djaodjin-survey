# Copyright (c) 2023, DjaoDjin inc.
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

from django.conf import settings as django_settings
from django.views.generic.base import RedirectView, TemplateView
from django.views.generic.detail import SingleObjectMixin

from .. import signals
from ..compat import reverse, NoReverseMatch
from ..helpers import update_context_urls
from ..mixins import AccountMixin
from ..models import PortfolioDoubleOptIn
from ..utils import validate_redirect

LOGGER = logging.getLogger(__name__)


class PortfoliosView(AccountMixin, TemplateView):

    template_name = 'survey/portfolios.html'

    def get_context_data(self, **kwargs):
        context = super(PortfoliosView, self).get_context_data(**kwargs)
        url_kwargs = self.get_url_kwargs(**kwargs)
        urls = {
            'survey_api_portfolios_grants':
                reverse('survey_api_portfolios_grants', kwargs=url_kwargs),
            'survey_api_portfolios_requests':
                reverse('survey_api_portfolios_requests', kwargs=url_kwargs),
            'survey_api_portfolios_received':
                reverse('survey_api_portfolios_received', kwargs=url_kwargs),
        }
        try:
            urls.update({
                'api_account_candidates': reverse('api_account_candidates'),
                'api_grant_allowed_candidates':
                    reverse('api_grant_allowed_candidates'),
            })
        except NoReverseMatch:
            # We just don't have a way to find candidates to grant and request
            # portfolios from.
            pass
        update_context_urls(context, urls)
        return context


class PortfoliosAcceptView(RedirectView):

    def get_redirect_url(self, *args, **kwargs):
        redirect_path = validate_redirect(self.request)
        if not redirect_path:
            redirect_path = django_settings.LOGIN_REDIRECT_URL
        return redirect_path


class PortfoliosGrantAcceptView(AccountMixin, SingleObjectMixin,
                                PortfoliosAcceptView):

    # SingleObjectMixin would override `slug_field` and `slug_url_kwarg`.
    slug_field = 'verification_key'
    slug_url_kwarg = 'verification_key'

    def get_queryset(self):
        # Look up grant to be accepted through the 'verification_key'
        # so it OK to just filter by grantee.
        return PortfolioDoubleOptIn.objects.filter(grantee=self.account)

    def get(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.grant_accepted()
        signals.portfolio_grant_accepted.send(sender=__name__,
            portfolio=instance, request=self.request)
        return super(PortfoliosGrantAcceptView, self).get(
            request, *args, **kwargs)


class PortfoliosRequestAcceptView(AccountMixin, SingleObjectMixin,
                                  PortfoliosAcceptView):

    # SingleObjectMixin would override `slug_field` and `slug_url_kwarg`.
    slug_field = 'verification_key'
    slug_url_kwarg = 'verification_key'

    def get_queryset(self):
        # Look up request to be accepted through the 'verification_key'
        # so it OK to just filter by account.
        return PortfolioDoubleOptIn.objects.filter(account=self.account)

    def get(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.request_accepted()
        signals.portfolio_request_accepted.send(sender=__name__,
            portfolio=instance, request=self.request)
        return super(PortfoliosRequestAcceptView, self).get(
            request, *args, **kwargs)
