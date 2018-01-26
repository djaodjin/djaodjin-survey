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

import datetime

from django.db import transaction
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import (CreateView, RedirectView, TemplateView,
    UpdateView)
from django.utils.timezone import utc

from ..forms import AnswerForm, SampleCreateForm, SampleUpdateForm
from ..mixins import IntervieweeMixin, SampleMixin, CampaignMixin
from ..models import Choice, Question, Sample, Answer


def _datetime_now():
    return datetime.datetime.utcnow().replace(tzinfo=utc)


class AnswerUpdateView(SampleMixin, UpdateView):
    """
    Update an ``Answer``.
    """

    model = Answer
    form_class = AnswerForm
    next_step_url = 'survey_answer_update'
    complete_url = 'survey_sample_results'

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
                kwargs=self.get_url_context()))
        return super(AnswerUpdateView, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(AnswerUpdateView, self).get_context_data(**kwargs)
        context.update(self.get_url_context())
        return context

    def get_next_answer(self):
        return Answer.objects.filter(
            sample=self.sample, text=None).order_by('rank').first()

    def get_object(self, queryset=None):
        rank = self.kwargs.get('rank', None)
        if rank:
            return get_object_or_404(Answer,
                sample=self.sample, rank=rank)
        return self.get_next_answer()

    def get_success_url(self):
        kwargs = self.get_url_context()
        next_answer = self.get_next_answer()
        if not next_answer:
            return reverse(self.complete_url,
                kwargs=self.get_url_context())
        kwargs.update({'rank': next_answer.rank})
        return reverse(self.next_step_url, kwargs=kwargs)

    def form_valid(self, form):
        sample = self.object.sample
        sample.time_spent = _datetime_now() - sample.created_at
        sample.save()
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
        kwargs = self.get_url_context()
        next_answer = self.get_next_answer()
        if not next_answer:
            return reverse(self.complete_url,
                kwargs=self.get_url_context())
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
        context.update(self.get_url_context())
        context.update({'sample': self.sample,
            # only sample slug available through get_url_context()
            'answers': answers, 'score': score})
        return context

    def post(self, request, *args, **kwargs):
        # The csrftoken in valid when we get here. That's all that matters.
        self.sample.time_spent = _datetime_now() - self.sample.created_at
        self.sample.is_frozen = True
        self.sample.save()
        return self.get(request, *args, **kwargs)


class SampleCreateView(CampaignMixin, IntervieweeMixin, CreateView):
    """
    Creates a ``Sample`` of a ``Account`` to a ``Campaign``
    """

    model = Sample
    form_class = SampleCreateForm
    next_step_url = 'survey_answer_update'
    single_page_next_step_url = 'survey_sample_update'

    template_name = 'survey/sample_create.html'

    def __init__(self, *args, **kwargs):
        super(SampleCreateView, self).__init__(*args, **kwargs)
        self.survey = None

    def form_valid(self, form):
        # We are going to create all the Answer records for that Sample here,
        # initialize them with a text when present in the submitted form.
        self.object = form.save()
        for question in Question.objects.filter(survey=self.object.survey):
            kwargs = {'sample': self.object,
                'question': question, 'rank': question.rank}
            answer_text = form.cleaned_data.get(
                'question-%d' % question.rank, None)
            if answer_text:
                kwargs.update({'text': answer_text})
            Answer.objects.create(**kwargs)
        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(SampleCreateView, self).get_context_data(**kwargs)
        context.update({'survey': self.survey})
        return context

    def get_initial(self):
        """
        Returns the initial data to use for forms on this view.
        """
        kwargs = super(SampleCreateView, self).get_initial()
        self.survey = self.get_survey()
        kwargs.update({'survey': self.survey,
                       'account': self.get_interviewee()})
        return kwargs

    def get_success_url(self):
        kwargs = self.get_url_context()
        kwargs.update({SampleMixin.sample_url_kwarg: self.object.slug})
        if self.survey and self.survey.defaults_single_page:
            next_step_url = self.single_page_next_step_url
        else:
            kwargs.update({'rank': Answer.objects.filter(
                sample=self.object).order_by('rank').first().rank})
            next_step_url = self.next_step_url
        return reverse(next_step_url, kwargs=kwargs)


class SampleResetView(SampleMixin, RedirectView):
    """
    Resets all ``Answer`` of a ``Sample`` from a ``Account``.
    """

    pattern_name = 'survey_sample_update'

    def get(self, request, *args, **kwargs):
        if self.sample.survey and not self.sample.survey.one_sample_only:
            with transaction.atomic():
                for answer in self.sample.answers.all():
                    answer.measured = None
                    answer.save()
                self.sample.is_frozen = False
                self.sample.save()
        return super(SampleResetView, self).get(request, *args, **kwargs)


class SampleUpdateView(SampleMixin, IntervieweeMixin, UpdateView):
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
        for answer in self.sample.answers.order_by('rank'):
            answer.measured, _ = Choice.objects.get_or_create(
                unit=answer.question.unit,
                text=form.cleaned_data['question-%d' % answer.rank])
            answer.save()
        return super(SampleUpdateView, self).form_valid(form)

    def get_object(self, queryset=None):
        return self.sample

    def get_context_data(self, **kwargs):
        context = super(SampleUpdateView, self).get_context_data(**kwargs)
        context.update({'survey': self.sample.survey})
        return context

    def get_success_url(self):
        kwargs = self.get_url_context()
        # XXX not sure we need to set this.
        kwargs.update({self.sample_url_kwarg: self.sample.slug})
        return reverse(self.next_step_url, kwargs=kwargs)
