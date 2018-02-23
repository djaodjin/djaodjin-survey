# Copyright (c) 2018, DjaoDjin inc.
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

from django.core.urlresolvers import reverse
from django.db import transaction
from django.db.models import Max
from django.shortcuts import get_object_or_404
from django.views.generic import (CreateView, DeleteView, ListView,
    RedirectView, UpdateView)

from ..compat import csrf
from ..forms import QuestionForm
from ..models import EnumeratedQuestions
from ..mixins import CampaignMixin, CampaignQuestionMixin
from ..utils import get_question_model


class QuestionFormMixin(CampaignQuestionMixin):

    model = get_question_model()
    form_class = QuestionForm
    success_url = 'survey_question_list'

    def get_object(self, queryset=None):
        """
        Returns a question object based on the URL.
        """
        return super(QuestionFormMixin, self).get_object(
            queryset=queryset).question

    def form_valid(self, form):
        with transaction.atomic():
            result = super(QuestionFormMixin, self).form_valid(form)
            last_rank = EnumeratedQuestions.objects.filter(
                campaign=self.campaign).aggregate(Max('rank')).get(
                    'rank__max', 0)
            _ = EnumeratedQuestions.objects.get_or_create(
                question=self.object,
                campaign=self.campaign,
                defaults={'rank': last_rank})
        return result

    def get_success_url(self):
        return reverse(self.success_url, args=(self.campaign,))


class QuestionCreateView(QuestionFormMixin, CreateView):
    """
    Create a new question within a survey.
    """
    pass


class QuestionDeleteView(CampaignQuestionMixin, DeleteView):
    """
    Delete a question.
    """
    success_url = 'survey_question_list'

    def get_success_url(self):
        return reverse(self.success_url, args=(self.campaign,))


class QuestionListView(CampaignQuestionMixin, ListView):
    """
    List of questions for a survey
    """
    template_name = 'survey/question_list.html'

    def get_context_data(self, **kwargs):
        context = super(QuestionListView, self).get_context_data(**kwargs)
        context.update(csrf(self.request))
        context.update({'campaign': self.campaign})
        return context


class QuestionRankView(CampaignQuestionMixin, RedirectView):
    """
    Update the rank of a question in a survey
    """

    pattern_name = 'survey_question_list'
    direction = 1                   # defaults to "down"

    def post(self, request, *args, **kwargs):
        enum_question = self.get_object()
        swapped_enum_question = None
        question_rank = enum_question.rank
        if self.direction < 0:
            if question_rank > 1:
                swapped_enum_question = self.model.objects.get(
                    campaign=enum_question.campaign, rank=question_rank - 1)
        else:
            if question_rank < self.model.objects.filter(
                campaign=enum_question.campaign).count():
                swapped_enum_question = self.model.objects.get(
                    campaign=enum_question.campaign, rank=question_rank + 1)
        print("XXX %d swap %s(%d) for %s(%d)" % (question_rank, enum_question, enum_question.rank, swapped_enum_question, swapped_enum_question.rank))
        if swapped_enum_question:
            enum_question.rank = swapped_enum_question.rank
            swapped_enum_question.rank = question_rank
            print("XXX updated to %s(%d) for %s(%d)" % (enum_question, enum_question.rank, swapped_enum_question, swapped_enum_question.rank))
            enum_question.save()
            swapped_enum_question.save()
        del kwargs[self.num_url_kwarg]
        return super(QuestionRankView, self).post(request, *args, **kwargs)


class QuestionUpdateView(QuestionFormMixin, UpdateView):
    """
    Update a question
    """
    pass
