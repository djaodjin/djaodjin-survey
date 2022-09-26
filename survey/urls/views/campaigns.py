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

from ...compat import path
from ...views.campaigns import (CampaignListView, CampaignPublishView,
    CampaignResultView, CampaignSendView, CampaignUpdateView)
from ...views.createquestion import (QuestionCreateView, QuestionDeleteView,
    QuestionListView, QuestionRankView, QuestionUpdateView)
from ...views.matrix import RespondentListView


urlpatterns = [
    path(r'<slug:campaign>/send/',
        CampaignSendView.as_view(), name='survey_send'),
    path(r'<slug:campaign>/result/',
        CampaignResultView.as_view(), name='survey_result'),
    path(r'<slug:campaign>/respondents/',
        RespondentListView.as_view(), name='survey_respondent_list'),
    path(r'<slug:campaign>/publish/',
        CampaignPublishView.as_view(), name='survey_publish'),
    path(r'<slug:campaign>/edit/',
        CampaignUpdateView.as_view(), name='survey_edit'),

    path(r'<slug:campaign>/new/',
        QuestionCreateView.as_view(), name='survey_question_new'),
    path(r'<slug:campaign>/<int:num>/down/',
        QuestionRankView.as_view(), name='survey_question_down'),
    path(r'<slug:campaign>/<int:num>/up/',
        QuestionRankView.as_view(direction=-1), name='survey_question_up'),
    path(r'<slug:campaign>/<int:num>/delete/',
        QuestionDeleteView.as_view(), name='survey_question_delete'),
    path(r'<slug:campaign>/<int:num>/edit/',
        QuestionUpdateView.as_view(), name='survey_question_edit'),

    path('<slug:campaign>/',
        QuestionListView.as_view(), name='survey_question_list'),
    path('',
        CampaignListView.as_view(), name='survey_campaign_list'),
]
