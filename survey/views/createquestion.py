# Copyright (c) 2020, DjaoDjin inc.
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

from django.db import transaction
from django.db.models import Max
from django.template.defaultfilters import slugify
from django.views.generic import (CreateView, DeleteView, ListView,
    RedirectView, UpdateView)

from ..compat import csrf, reverse
from ..forms import QuestionForm
from ..models import Choice, EnumeratedQuestions, Question, Unit
from ..mixins import CampaignQuestionMixin


class QuestionFormMixin(CampaignQuestionMixin):

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
            if form.cleaned_data['ui_hint'] == Question.RADIO:
                enum_slug = slugify(form.cleaned_data['text'])
                form.instance.default_unit = Unit.objects.create(
                    slug=enum_slug,
                    system=Unit.SYSTEM_ENUMERATED)
                correct_answer = form.cleaned_data['correct_answer']
                for rank, choice in enumerate(
                        form.cleaned_data['choices'].split('\n')):
                    choice = Choice.objects.create(
                        text=choice.strip(),
                        unit=form.instance.default_unit,
                        rank=rank)
                    if correct_answer and choice.text in correct_answer:
                        form.instance.correct_answer = choice
            result = super(QuestionFormMixin, self).form_valid(form)
            last_rank = EnumeratedQuestions.objects.filter(
                campaign=self.campaign).aggregate(Max('rank')).get(
                    'rank__max', 0)
            _ = EnumeratedQuestions.objects.get_or_create(
                question=self.object,
                campaign=self.campaign,
                defaults={'rank': last_rank + 1})
        return result

    def get_success_url(self):
        return reverse(self.success_url, args=(self.campaign,))


class QuestionCreateView(QuestionFormMixin, CreateView):
    """
    Create a new question within a campaign.
    """
    template_name = 'survey/question_form.html'


class QuestionDeleteView(CampaignQuestionMixin, DeleteView):
    """
    Delete a question.
    """
    success_url = 'survey_question_list'

    def get_success_url(self):
        return reverse(self.success_url, args=(self.campaign,))


class QuestionListView(CampaignQuestionMixin, ListView):
    """
    List of questions for a campaign
    """
    template_name = 'survey/question_list.html'

    def get_context_data(self, **kwargs):
        context = super(QuestionListView, self).get_context_data(**kwargs)
        context.update(csrf(self.request))
        context.update({'campaign': self.campaign})
        return context


class QuestionRankView(CampaignQuestionMixin, RedirectView):
    """
    Update the rank of a question in a campaign
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
        if swapped_enum_question:
            enum_question.rank = swapped_enum_question.rank
            swapped_enum_question.rank = question_rank
            enum_question.save()
            swapped_enum_question.save()
        del kwargs[self.num_url_kwarg]
        return super(QuestionRankView, self).post(request, *args, **kwargs)


class QuestionUpdateView(QuestionFormMixin, UpdateView):
    """
    Update a question
    """
    template_name = 'survey/question_form.html'
