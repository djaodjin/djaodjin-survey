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
from ...views.matrix import (MatrixListView, MatrixDetailView,
    AccountListView, QuestionListView)
from ...compat import re_path


urlpatterns = [
    re_path(r'^accounts/(?P<editable_filter>%s)/?' % settings.SLUG_RE,
        AccountListView.as_view(), name='accounts_list'),
    re_path(r'^accounts/',
        AccountListView.as_view(), name='accounts_base'),
    re_path(r'^questions/(?P<editable_filter>%s)/?' % settings.SLUG_RE,
        QuestionListView.as_view(), name='questions_list'),
    re_path(r'^questions/',
        QuestionListView.as_view(), name='questions_base'),
    re_path(r'^(?P<path>%s)/' % settings.SLUG_RE,
        MatrixDetailView.as_view(), name='matrix_chart'),
    re_path(r'^$',
        MatrixListView.as_view(), name='matrix_base'),
]
