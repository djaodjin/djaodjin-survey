# Copyright (c) 2023, DjaoDjin inc.
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

import logging

from django.core.exceptions import NON_FIELD_ERRORS
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import (CreateView, RedirectView, TemplateView,
    UpdateView)
from rest_framework.exceptions import ValidationError

from ..api.sample import update_or_create_answer
from ..compat import is_authenticated, reverse
from ..forms import AnswerForm, SampleCreateForm, SampleUpdateForm
from ..helpers import datetime_or_now
from ..mixins import AccountMixin, CampaignMixin, SampleMixin
from ..models import Answer, Choice, EnumeratedQuestions, Sample
from ..utils import get_question_model


LOGGER = logging.getLogger(__name__)


class AnswerUpdateView(SampleMixin, UpdateView):
    """
    Update an ``Answer``.
    """

    model = Answer
    form_class = AnswerForm
    lookup_rank_kwarg = 'rank'
    next_step_url = 'survey_answer_update'
    complete_url = 'survey_sample_results'

    def __init__(self, **kwargs):
        super(AnswerUpdateView, self).__init__(**kwargs)
        self.object = None

    @property
    def rank(self):
        return int(self.kwargs.get(self.lookup_rank_kwarg))

    @property
    def question(self):
        #pylint:disable=attribute-defined-outside-init
        if not hasattr(self, '_question'):
            if self.sample:
                self._question = get_object_or_404(
                    get_question_model().objects.all(),
                    enumeratedquestions__campaign=self.sample.campaign,
                    enumeratedquestions__rank=self.rank)
            else:
                self._question = None  # API docs get here.
        return self._question

    def dispatch(self, request, *args, **kwargs):
        """
        Shows the Question or redirects to the complete URL if the ``Sample``
        instance is frozen.
        """
        # Implementation Note:
        #    The "is_frozen" test is done in dispatch because we want
        #    to prevent updates on any kind of requests.
        self.object = self.get_object()
        if not self.object or self.object.sample.is_frozen:
            return redirect(reverse(self.complete_url,
                kwargs=self.get_url_kwargs()))
        return super(AnswerUpdateView, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(AnswerUpdateView, self).get_context_data(**kwargs)
        context.update(self.get_url_kwargs())
        return context

    def get_next_answer(self):
        return self.sample.get_answers_by_rank().filter(measured=None).first()

    def get_object(self, queryset=None):
        if self.rank:
            return get_object_or_404(Answer,
                sample=self.sample, question=self.question)
        return self.get_next_answer()

    def get_success_url(self):
        kwargs = self.get_url_kwargs()
        next_answer = self.get_next_answer()
        if not next_answer:
            return reverse(self.complete_url,
                kwargs=self.get_url_kwargs())
        kwargs.update({'rank': next_answer.rank}) #XXX rank
        return reverse(self.next_step_url, kwargs=kwargs)

    def form_valid(self, form):
        user = self.request.user if is_authenticated(self.request) else None

        errors = []
        datapoints = []
        if isinstance(form.cleaned_data['text'], list):
            for measured in form.cleaned_data['text']:
                datapoints += [{'measured': measured}]
        else:
            datapoints = [{'measured': form.cleaned_data['text']}]
        for datapoint in datapoints:
            measured = datapoint.get('measured', None)
            if not measured:
                continue
            try:
                with transaction.atomic():
                    created_at = datetime_or_now()
                    update_or_create_answer(
                        datapoint, question=self.object.question,
                        sample=self.object.sample, created_at=created_at,
                        collected_by=user)
            except ValidationError as err:
                errors += [err]
        if errors:
            form.add_error(NON_FIELD_ERRORS, errors)
            return super(AnswerUpdateView, self).form_invalid(form)
        return super(AnswerUpdateView, self).form_valid(form)


class AnswerNextView(AnswerUpdateView):

    """
    Straight through to ``Sample`` complete when all questions
    have been answered.
    """

    next_step_url = 'survey_answer_update'

    def get_object(self, queryset=None):
        # We always override the *rank* by the latest unanswered question
        # to avoid skipping over questions and unintended redirect to results.
        return self.get_next_answer()

    def form_valid(self, form):
        next_answer = self.get_next_answer()
        if not next_answer:
            sample = self.object.sample
            sample.is_frozen = True
            sample.save()
        return super(AnswerNextView, self).form_valid(form)

    def get_success_url(self):
        kwargs = self.get_url_kwargs()
        next_answer = self.get_next_answer()
        if not next_answer:
            return reverse(self.complete_url,
                kwargs=self.get_url_kwargs())
        return reverse(self.next_step_url, kwargs=kwargs)


class SampleResultView(SampleMixin, TemplateView):
    """
    Presents a ``Sample`` when it is frozen or an empty page
    with the option to freeze the sample otherwise.
    """

    template_name = 'survey/result_quizz.html'

    def get_context_data(self, **kwargs):
        context = super(SampleResultView, self).get_context_data(**kwargs)
        score, answers = Sample.objects.get_score(self.sample)
        context.update(self.get_url_kwargs())
        context.update({'sample': self.sample,
            # only sample slug available through get_url_kwargs()
            'answers': answers, 'score': score})
        return context

    def post(self, request, *args, **kwargs):
        # The csrftoken in valid when we get here. That's all that matters.
        at_time = datetime_or_now()
        self.sample.updated_at = at_time
        self.sample.is_frozen = True
        self.sample.save()
        return self.get(request, *args, **kwargs)


class SampleCreateView(CampaignMixin, AccountMixin, CreateView):
    """
    Creates a ``Sample`` of a ``Account`` to a ``Campaign``
    """

    model = Sample
    form_class = SampleCreateForm
    next_step_url = 'survey_answer_update'
    single_page_next_step_url = 'survey_sample_update'
    template_name = 'survey/sample_create.html'

    def __init__(self, **kwargs):
        super(SampleCreateView, self).__init__(**kwargs)
        self.object = None

    def form_valid(self, form):
        # We are going to create all the Answer records for that Sample here,
        # initialize them with a text when present in the submitted form.
        at_time = datetime_or_now()
        self.object = form.save()
        for enum_q in EnumeratedQuestions.objects.filter(
                campaign=self.object.campaign):
            kwargs = {
                'created_at': at_time,
                'sample': self.object,
                'question': enum_q.question}
            answer_text = form.cleaned_data.get(
                'question-%d' % enum_q.rank, None)
            if answer_text:
                kwargs.update({'text': answer_text})
            Answer.objects.create(
                unit=enum_q.question.default_unit, **kwargs)
        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(SampleCreateView, self).get_context_data(**kwargs)
        context.update({'campaign': self.campaign})
        return context

    def get_initial(self):
        """
        Returns the initial data to use for forms on this view.
        """
        kwargs = super(SampleCreateView, self).get_initial()
        kwargs.update({'campaign': self.campaign,
                       'account': self.account})
        return kwargs

    def get_success_url(self):
        kwargs = self.get_url_kwargs(**self.kwargs)
        kwargs.update({SampleMixin.sample_url_kwarg: self.object.slug})
        if self.campaign and self.campaign.defaults_single_page:
            next_step_url = self.single_page_next_step_url
        else:
            first_answer = self.object.get_answers_by_rank().first()
            kwargs.update({'rank': first_answer.rank})
            next_step_url = self.next_step_url
        return reverse(next_step_url, kwargs=kwargs)


class SampleResetView(SampleMixin, RedirectView):
    """
    Resets all ``Answer`` of a ``Sample`` from a ``Account``.
    """

    pattern_name = 'survey_sample_update'

    def get(self, request, *args, **kwargs):
        if self.sample.campaign and not self.sample.campaign.one_sample_only:
            with transaction.atomic():
                for answer in self.sample.answers.all():
                    answer.measured = None
                    answer.save()
                self.sample.is_frozen = False
                self.sample.save()
        return super(SampleResetView, self).get(request, *args, **kwargs)


class SampleUpdateView(SampleMixin, UpdateView):
    """
    Updates all ``Answer`` of a ``Sample`` from a ``Account``
    in a single shot.
    """
    model = Sample
    form_class = SampleUpdateForm
    next_step_url = 'survey_sample_results'
    template_name = 'survey/sample_update.html'

    def form_valid(self, form):
        # We are updating all ``Answer`` for the ``Sample`` here.
        for answer in self.sample.get_answers_by_rank():
            answer.measured, _ = Choice.objects.get_or_create(
                unit=answer.question.unit,
                text=form.cleaned_data['question-%d' % answer.rank]) # XXX rank
            answer.save()
        return super(SampleUpdateView, self).form_valid(form)

    def get_object(self, queryset=None):
        return self.sample

    def get_context_data(self, **kwargs):
        context = super(SampleUpdateView, self).get_context_data(**kwargs)
        context.update({'campaign': self.sample.campaign})
        return context

    def get_success_url(self):
        return reverse(self.next_step_url, kwargs=self.get_url_kwargs())
