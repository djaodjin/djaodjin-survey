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

"""
URLs for the djaodjin-survey django app testsite.
"""

import debug_toolbar
from django.views.generic import RedirectView, TemplateView
from rules.urldecorators import include, re_path
from survey.compat import reverse_lazy
from survey.settings import SLUG_RE

from .api.auth import LoginAPIView
from .api.accounts import AccountsAPIView

urlpatterns = [
    re_path(r'^__debug__/', include(debug_toolbar.urls)),
    re_path(r'^$',
        TemplateView.as_view(template_name='index.html'), name='home'),
    # survey.urls.api
    re_path(r'^api/', include('survey.urls.api.noauth')),
    re_path(r'^api/', include('survey.urls.api.campaigns')),
    re_path(r'^api/(?P<organization>%s)/' % SLUG_RE,
        include('survey.urls.api.filters')),
    re_path(r'^api/(?P<organization>%s)/' % SLUG_RE,
        include('survey.urls.api.matrix')),
    re_path(r'^api/(?P<organization>%s)/' % SLUG_RE,
        include('survey.urls.api.sample')),
    re_path(r'^api/(?P<organization>%s)/' % SLUG_RE,
        include('survey.urls.api.portfolios')),
    re_path(r'^api/accounts/grant-allowed', AccountsAPIView.as_view(),
        name='api_grant_allowed_candidates'),
    re_path(r'^api/accounts', AccountsAPIView.as_view(),
        name='api_account_candidates'),
    re_path(r'api/auth', LoginAPIView.as_view(), name='api_login'),
    re_path(r'^app/', include('survey.urls.views')),

    re_path(r'^accounts/profile/',
        RedirectView.as_view(url=reverse_lazy('survey_campaign_list'))),
    re_path(r'^', include('django.contrib.auth.urls')),
]
