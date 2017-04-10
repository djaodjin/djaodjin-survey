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

import datetime

from django.db import transaction
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import (CreateView, RedirectView, TemplateView,
    UpdateView)
from django.utils.timezone import utc

from survey.forms import AnswerForm, ResponseCreateForm, ResponseUpdateForm
from survey.mixins import IntervieweeMixin, ResponseMixin, SurveyModelMixin
from survey.models import Question, Response, Answer


def _datetime_now():
    return datetime.datetime.utcnow().replace(tzinfo=utc)


class AnswerUpdateView(ResponseMixin, UpdateView):
    """
    Update an ``Answer``.
    """

    model = Answer
    form_class = AnswerForm
    next_step_url = 'survey_answer_update'
    complete_url = 'survey_response_results'

    def dispatch(self, request, *args, **kwargs):
        """
        Shows the Question or redirects to the complete URL if the ``Response``
        instance is frozen.
        """
        # Implementation Note:
        #    The "is_frozen" test is done in dispatch because we want
        #    to prevent updates on any kind of requests.
        self.object = self.get_object()
        if not self.object or self.object.response.is_frozen:
            return redirect(reverse(self.complete_url,
                kwargs=self.get_url_context()))
        return super(AnswerUpdateView, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(AnswerUpdateView, self).get_context_data(**kwargs)
        context.update(self.get_url_context())
        return context

    def get_next_answer(self):
        return Answer.objects.filter(
            response=self.get_response(), text=None).order_by('rank').first()

    def get_object(self, queryset=None):
        rank = self.kwargs.get('rank', None)
        if rank:
            return get_object_or_404(Answer,
                response=self.get_response(), rank=rank)
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
        response = self.object.response
        response.time_spent = _datetime_now() - response.created_at
        response.save()
        return super(AnswerUpdateView, self).form_valid(form)


class AnswerNextView(AnswerUpdateView):

    """
    Straight through to ``Response`` complete when all questions
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
            response = self.object.response
            response.is_frozen = True
            response.save()
        return super(AnswerNextView, self).form_valid(form)

    def get_success_url(self):
        kwargs = self.get_url_context()
        next_answer = self.get_next_answer()
        if not next_answer:
            return reverse(self.complete_url,
                kwargs=self.get_url_context())
        return reverse(self.next_step_url, kwargs=kwargs)


class ResponseResultView(ResponseMixin, TemplateView):
    """
    Presents a ``Response`` when it is frozen or an empty page
    with the option to freeze the response otherwise.
    """

    template_name = 'survey/result_quizz.html'

    def get_context_data(self, **kwargs):
        context = super(ResponseResultView, self).get_context_data(**kwargs)
        score, answers = Response.objects.get_score(self.response)
        context.update(self.get_url_context())
        context.update({'response': self.response,
            # only response slug available through get_url_context()
            'answers': answers, 'score': score})
        return context

    def get(self, request, *args, **kwargs):
        self.response = self.get_response()
        return super(ResponseResultView, self).get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        # The csrftoken in valid when we get here. That's all that matters.
        self.response = self.get_response()
        self.response.time_spent = _datetime_now() - self.response.created_at
        self.response.is_frozen = True
        self.response.save()
        return self.get(request, *args, **kwargs)


class ResponseCreateView(SurveyModelMixin, IntervieweeMixin, CreateView):
    """
    Creates a ``Response`` of a ``Account`` to a ``SurveyModel``
    """

    model = Response
    form_class = ResponseCreateForm
    next_step_url = 'survey_answer_update'
    single_page_next_step_url = 'survey_response_update'

    template_name = 'survey/response_create.html'

    def __init__(self, *args, **kwargs):
        super(ResponseCreateView, self).__init__(*args, **kwargs)
        self.survey = None

    def form_valid(self, form):
        # We are going to create all the Answer records for that Response here,
        # initialize them with a text when present in the submitted form.
        self.object = form.save()
        for question in Question.objects.filter(survey=self.object.survey):
            kwargs = {'response': self.object,
                'question': question, 'rank': question.rank}
            answer_text = form.cleaned_data.get(
                'question-%d' % question.rank, None)
            if answer_text:
                kwargs.update({'text': answer_text})
            Answer.objects.create(**kwargs)
        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(ResponseCreateView, self).get_context_data(**kwargs)
        context.update({'survey': self.survey})
        return context

    def get_initial(self):
        """
        Returns the initial data to use for forms on this view.
        """
        kwargs = super(ResponseCreateView, self).get_initial()
        self.survey = self.get_survey()
        kwargs.update({'survey': self.survey,
                       'account': self.get_interviewee()})
        return kwargs

    def get_success_url(self):
        kwargs = self.get_url_context()
        kwargs.update({ResponseMixin.response_url_kwarg: self.object.slug})
        if self.survey and self.survey.defaults_single_page:
            next_step_url = self.single_page_next_step_url
        else:
            kwargs.update({'rank': Answer.objects.filter(
                response=self.object).order_by('rank').first().rank})
            next_step_url = self.next_step_url
        return reverse(next_step_url, kwargs=kwargs)


class ResponseResetView(ResponseMixin, RedirectView):
    """
    Resets all ``Answer`` of a ``Response`` from a ``Account``.
    """

    pattern_name = 'survey_response_update'

    def get(self, request, *args, **kwargs):
        self.object = self.get_response()
        if self.object.survey and not self.object.survey.one_response_only:
            with transaction.atomic():
                for answer in self.object.answers.all():
                    answer.text = None
                    answer.save()
                self.object.is_frozen = False
                self.object.save()
        return super(ResponseResetView, self).get(request, *args, **kwargs)


class ResponseUpdateView(ResponseMixin, IntervieweeMixin, UpdateView):
    """
    Updates all ``Answer`` of a ``Response`` from a ``Account``
    in a single shot.
    """
    model = Response
    form_class = ResponseUpdateForm
    next_step_url = 'survey_response_results'
    template_name = 'survey/response_update.html'

    def __init__(self, *args, **kwargs):
        super(ResponseUpdateView, self).__init__(*args, **kwargs)
        self.survey = None

    def form_valid(self, form):
        # We are updating all ``Answer`` for the ``Response`` here.
        for answer in self.object.answers.order_by('rank'):
            answer.text = form.cleaned_data['question-%d' % answer.rank]
            answer.save()
        return super(ResponseUpdateView, self).form_valid(form)

    def get_object(self, queryset=None):
        return self.get_response()

    def get_context_data(self, **kwargs):
        context = super(ResponseUpdateView, self).get_context_data(**kwargs)
        context.update({'survey': self.survey})
        return context

    def get_initial(self):
        """
        Returns the initial data to use for forms on this view.
        """
        kwargs = super(ResponseUpdateView, self).get_initial()
        self.survey = self.get_survey()
        kwargs.update({'survey': self.survey,
                       'account': self.get_interviewee()})
        return kwargs

    def get_success_url(self):
        kwargs = self.get_url_context()
        kwargs.update({self.response_url_kwarg: self.object.slug})
        return reverse(self.next_step_url, kwargs=kwargs)
