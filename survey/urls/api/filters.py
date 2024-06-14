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

from ...api.matrix import (AccountsFilterDetailAPIView,
    AccountsFilterListAPIView, AccountsFilterEnumeratedAPIView,
    EditableFilterListAPIView, QuestionsFilterDetailAPIView,
    QuestionsFilterListAPIView)
from ...api.metrics import AccountsValuesAPIView, AccountsFilterValuesAPIView
from ...compat import path


urlpatterns = [
    path('filters/accounts/values',
        AccountsValuesAPIView.as_view(),
        name='survey_api_accounts_values'),
    path('filters/accounts/<slug:editable_filter>/values',
        AccountsFilterValuesAPIView.as_view(),
        name='survey_api_accounts_filter_values'),
    path('filters/accounts/<slug:editable_filter>/<int:rank>',
        AccountsFilterEnumeratedAPIView.as_view(),
        name='survey_api_accounts_filter_enumerated'),
    path('filters/accounts/<slug:editable_filter>',
        AccountsFilterDetailAPIView.as_view(),
        name='survey_api_accounts_filter'),
    path('filters/accounts',
        AccountsFilterListAPIView.as_view(),
        name='survey_api_accounts_filter_list'),
#    path('filters/questions/<slug:editable_filter>',
#        QuestionsFilterDetailAPIView.as_view(),
#        name='survey_api_questions_filter'),
#    path('filters/questions',
#        QuestionsFilterListAPIView.as_view(),
#        name='survey_api_questions_filter_list'),
#    path('filters',
#        EditableFilterListAPIView.as_view(),
#        name='survey_api_filter_list'),
]
