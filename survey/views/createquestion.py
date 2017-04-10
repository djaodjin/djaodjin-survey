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

from django.core.urlresolvers import reverse
from django.shortcuts import get_object_or_404
from django.views.generic import (CreateView, DeleteView, ListView,
    RedirectView, UpdateView)

from ..compat import csrf
from ..forms import QuestionForm
from ..models import Question, SurveyModel
from ..mixins import QuestionMixin, SurveyModelMixin

class QuestionFormMixin(QuestionMixin):

    model = Question
    form_class = QuestionForm
    success_url = 'survey_question_list'

    def __init__(self, *args, **kwargs):
        super(QuestionFormMixin, self).__init__(*args, **kwargs)
        self.survey = None

    def get_initial(self):
        """
        Returns the initial data to use for forms on this view.
        """
        kwargs = super(QuestionFormMixin, self).get_initial()
        self.survey = get_object_or_404(
            SurveyModel, slug__exact=self.kwargs.get('survey'))
        last_rank = Question.objects.filter(survey=self.survey).count()
        kwargs.update({'survey': self.survey,
                       'rank': last_rank + 1})
        return kwargs

    def get_success_url(self):
        return reverse(self.success_url, args=(self.object.survey,))


class QuestionCreateView(QuestionFormMixin, CreateView):
    """
    Create a new question within a survey.
    """
    pass


class QuestionDeleteView(QuestionMixin, DeleteView):
    """
    Delete a question.
    """
    success_url = 'survey_question_list'

    def get_success_url(self):
        return reverse(self.success_url, args=(self.object.survey,))


class QuestionListView(SurveyModelMixin, ListView):
    """
    List of questions for a survey
    """
    model = Question

    def __init__(self, *args, **kwargs):
        super(QuestionListView, self).__init__(*args, **kwargs)
        self.survey = None

    def get_queryset(self):
        self.survey = self.get_survey()
        queryset = Question.objects.filter(survey=self.survey).order_by('rank')
        return queryset

    def get_context_data(self, *args, **kwargs):
        context = super(QuestionListView, self).get_context_data(
            *args, **kwargs)
        context.update(csrf(self.request))
        context.update({'survey': self.survey})
        return context


class QuestionRankView(QuestionMixin, RedirectView):
    """
    Update the rank of a question in a survey
    """

    pattern_name = 'survey_question_list'
    direction = 1                   # defaults to "down"

    def post(self, request, *args, **kwargs):
        question = self.get_object()
        swapped_question = None
        question_rank = question.rank
        if self.direction < 0:
            if question_rank > 1:
                swapped_question = Question.objects.get(
                    survey=question.survey, rank=question_rank - 1)
        else:
            if question_rank < Question.objects.filter(
                survey=question.survey).count():
                swapped_question = Question.objects.get(
                    survey=question.survey, rank=question_rank + 1)
        if swapped_question:
            question.rank = swapped_question.rank
            swapped_question.rank = question_rank
            question.save()
            swapped_question.save()
        kwargs = {'slug': kwargs['survey']}
        return super(QuestionRankView, self).post(request, *args, **kwargs)


class QuestionUpdateView(QuestionFormMixin, UpdateView):
    """
    Update a question
    """
    pass
