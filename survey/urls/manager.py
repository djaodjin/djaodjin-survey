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

from survey.views.createsurvey import (SurveyCreateView, SurveyDeleteView,
    SurveyListView, SurveyPublishView, SurveyResultView, SurveySendView,
    SurveyUpdateView)
from survey.views.createquestion import (QuestionCreateView, QuestionDeleteView,
    QuestionListView, QuestionRankView, QuestionUpdateView)
from survey.views.matrix import RespondentListView


urlpatterns = [
   url(r'^new/',
       SurveyCreateView.as_view(), name='survey_create'),
   url(r'^(?P<survey>[a-zA-Z0-9-]+)/send/',
       SurveySendView.as_view(), name='survey_send'),
   url(r'^(?P<survey>[a-zA-Z0-9-]+)/result/',
       SurveyResultView.as_view(), name='survey_result'),
   url(r'^(?P<survey>[a-zA-Z0-9-]+)/respondents/',
       RespondentListView.as_view(), name='survey_respondent_list'),
   url(r'^(?P<survey>[a-zA-Z0-9-]+)/publish/',
       SurveyPublishView.as_view(), name='survey_publish'),
   url(r'^(?P<survey>[a-zA-Z0-9-]+)/edit/',
       SurveyUpdateView.as_view(), name='survey_edit'),
   url(r'^(?P<survey>[a-zA-Z0-9-]+)/delete/',
       SurveyDeleteView.as_view(), name='survey_delete'),

   url(r'^(?P<survey>[a-zA-Z0-9-]+)/new/',
       QuestionCreateView.as_view(), name='survey_question_new'),
   url(r'^(?P<survey>[a-zA-Z0-9-]+)/(?P<num>\d+)/down/',
       QuestionRankView.as_view(), name='survey_question_down'),
   url(r'^(?P<survey>[a-zA-Z0-9-]+)/(?P<num>\d+)/up/',
       QuestionRankView.as_view(direction=-1), name='survey_question_up'),
   url(r'^(?P<survey>[a-zA-Z0-9-]+)/(?P<num>\d+)/delete/',
       QuestionDeleteView.as_view(), name='survey_question_delete'),
   url(r'^(?P<survey>[a-zA-Z0-9-]+)/(?P<num>\d+)/edit/',
       QuestionUpdateView.as_view(), name='survey_question_edit'),

   url(r'^(?P<survey>[a-zA-Z0-9-]+)/',
       QuestionListView.as_view(), name='survey_question_list'),
   url(r'^',
       SurveyListView.as_view(), name='survey_list'),
]
