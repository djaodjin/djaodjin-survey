# Copyright (c) 2017, DjaoDjin inc.
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

from ...api.matrix import (MatrixCreateAPIView, MatrixDetailAPIView,
    EditableFilterListAPIView, EditableFilterDetailAPIView,
    AccountListAPIView, QuestionListAPIView)
from ... import settings

urlpatterns = [
   url(r'^filters/(?P<editable_filter>%s)/?' % settings.SLUG_RE,
       EditableFilterDetailAPIView.as_view(), name='editable_filter_api'),
   url(r'^filters/?',
       EditableFilterListAPIView.as_view(), name='editable_filter_api_base'),
   url(r'^accounts/(?P<editable_filter>%s)/?' % settings.SLUG_RE,
       AccountListAPIView.as_view(), name='accounts_api'),
   url(r'^accounts/?',
       AccountListAPIView.as_view(), name='accounts_api_base'),
   url(r'^questions/(?P<editable_filter>%s)/?' % settings.SLUG_RE,
       QuestionListAPIView.as_view(), name='questions_api'),
   url(r'^questions/?',
       QuestionListAPIView.as_view(), name='questions_api_base'),
   url(r'^(?P<path>%s)/?' % settings.PATH_RE,
       MatrixDetailAPIView.as_view(), name='matrix_api'),
   url(r'^',
       MatrixCreateAPIView.as_view(), name='matrix_api_base'),
]
