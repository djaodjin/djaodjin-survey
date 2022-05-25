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

from django.views.generic.base import TemplateView

from ..compat import reverse, NoReverseMatch
from ..mixins import AccountMixin
from ..utils import update_context_urls

LOGGER = logging.getLogger(__name__)


class PortfoliosView(AccountMixin, TemplateView):

    template_name = 'survey/portfolios.html'

    def get_context_data(self, **kwargs):
        context = super(PortfoliosView, self).get_context_data(**kwargs)
        url_kwargs = self.get_url_kwargs()
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