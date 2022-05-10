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

from ... import settings
from ...compat import re_path
from ...views.sample import (AnswerUpdateView, SampleCreateView,
    SampleResetView, SampleResultView, SampleUpdateView)


urlpatterns = [
    re_path(r'^(?P<campaign>%s)/(?P<sample>%s)/reset/' % (
        settings.SLUG_RE, settings.SLUG_RE),
        SampleResetView.as_view(), name='survey_sample_reset'),
    re_path(r'^(?P<campaign>%s)/(?P<sample>%s)/results/' % (
        settings.SLUG_RE, settings.SLUG_RE),
        SampleResultView.as_view(), name='survey_sample_results'),
    re_path(r'^(?P<campaign>%s)/(?P<sample>%s)/(?:(?P<rank>\d+)/)'
        % (settings.SLUG_RE, settings.SLUG_RE),
        AnswerUpdateView.as_view(), name='survey_answer_update'),
    re_path(r'^(?P<campaign>%s)/(?P<sample>%s)/' % (
        settings.SLUG_RE, settings.SLUG_RE),
        SampleUpdateView.as_view(), name='survey_sample_update'),
    re_path(r'^(?P<campaign>%s)/' % settings.SLUG_RE,
        SampleCreateView.as_view(), name='survey_sample_new'),
]
