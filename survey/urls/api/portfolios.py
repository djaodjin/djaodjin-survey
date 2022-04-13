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

from django.conf.urls import url

from ... import settings
from ...api.portfolios import (PortfoliosAPIView,
    PortfoliosGrantsAPIView, PortfoliosGrantAcceptAPIView,
    PortfoliosRequestsAPIView, PortfoliosRequestAcceptAPIView)


urlpatterns = [
    url(r'^portfolios/grants/(?P<request_key>%s)/' % settings.SLUG_RE,
        PortfoliosGrantAcceptAPIView.as_view(),
        name='api_portfolios_grant_accept'),
    url(r'^portfolios/requests/(?P<request_key>%s)/' % settings.SLUG_RE,
        PortfoliosRequestAcceptAPIView.as_view(),
        name='api_portfolios_request_accept'),
    url(r'^portfolios/requests',
        PortfoliosRequestsAPIView.as_view(),
        name='survey_api_portfolios_requests'),
    url(r'^portfolios/grants',
        PortfoliosGrantsAPIView.as_view(),
        name='survey_api_portfolios_grants'),
    url(r'^portfolios',
        PortfoliosAPIView.as_view(),
        name='survey_api_portfolios_received'),
]
