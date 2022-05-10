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
from ...views.campaigns import (CampaignListView, CampaignPublishView,
    CampaignResultView, CampaignSendView, CampaignUpdateView)
from ...views.createquestion import (QuestionCreateView, QuestionDeleteView,
    QuestionListView, QuestionRankView, QuestionUpdateView)
from ...views.matrix import RespondentListView


urlpatterns = [
    re_path(r'^(?P<campaign>%s)/send/' % settings.SLUG_RE,
        CampaignSendView.as_view(), name='survey_send'),
    re_path(r'^(?P<campaign>%s)/result/' % settings.SLUG_RE,
        CampaignResultView.as_view(), name='survey_result'),
    re_path(r'^(?P<campaign>%s)/respondents/' % settings.SLUG_RE,
        RespondentListView.as_view(), name='survey_respondent_list'),
    re_path(r'^(?P<campaign>%s)/publish/' % settings.SLUG_RE,
        CampaignPublishView.as_view(), name='survey_publish'),
    re_path(r'^(?P<campaign>%s)/edit/' % settings.SLUG_RE,
        CampaignUpdateView.as_view(), name='survey_edit'),

    re_path(r'^(?P<campaign>%s)/new/' % settings.SLUG_RE,
        QuestionCreateView.as_view(), name='survey_question_new'),
    re_path(r'^(?P<campaign>%s)/(?P<num>\d+)/down/' % settings.SLUG_RE,
        QuestionRankView.as_view(), name='survey_question_down'),
    re_path(r'^(?P<campaign>%s)/(?P<num>\d+)/up/' % settings.SLUG_RE,
        QuestionRankView.as_view(direction=-1), name='survey_question_up'),
    re_path(r'^(?P<campaign>%s)/(?P<num>\d+)/delete/' % settings.SLUG_RE,
        QuestionDeleteView.as_view(), name='survey_question_delete'),
    re_path(r'^(?P<campaign>%s)/(?P<num>\d+)/edit/' % settings.SLUG_RE,
        QuestionUpdateView.as_view(), name='survey_question_edit'),

    re_path(r'^(?P<campaign>%s)/' % settings.SLUG_RE,
        QuestionListView.as_view(), name='survey_question_list'),
    re_path(r'^',
        CampaignListView.as_view(), name='survey_campaign_list'),
]
