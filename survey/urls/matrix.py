# Copyright (c) 2015, DjaoDjin inc.
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

from django.conf.urls import patterns, url

from survey.views.matrix import (MatrixView,
                                 MatrixApi,
                                 PortfolioView,
                                 PortfolioApi,
                                 QuestionCategoryApi,
                                 QuestionCategoryView)


urlpatterns = patterns('',
   url(r'^api/survey',
       MatrixApi.as_view(), name='matrix_api'),
   url(r'^portfolios',
       PortfolioView.as_view(), name='portfolio_view'),
   url(r'^questions',
       QuestionCategoryView.as_view(), name='portfolio_view'),
   url(r'^api/portfolio',
       PortfolioApi.as_view(), name='portfolio_api'),
   url(r'^api/question',
       QuestionCategoryApi.as_view(), name='questioncategory_api'),
   url(r'^',
       MatrixView.as_view(), name='matrix_View'),


)
