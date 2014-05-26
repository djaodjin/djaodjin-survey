# Copyright (c) 2014, DjaoDjin inc.
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
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import CreateView, TemplateView, UpdateView
from survey.forms import AnswerForm, ResponseCreateForm
from survey.models import Question, Response, Answer
from survey.mixins import IntervieweeMixin, ResponseMixin, SurveyModelMixin


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
            response=self.get_response(), body=None).order_by('index').first()

    def get_object(self, queryset=None):
        index = self.kwargs.get('index', None)
        if index:
            return get_object_or_404(Answer,
                response=self.get_response(), index=index)
        return self.get_next_answer()

    def get_success_url(self):
        kwargs = self.get_url_context()
        next_answer = self.get_next_answer()
        if not next_answer:
            return reverse(self.complete_url,
                kwargs=self.get_url_context())
        kwargs.update({'index': next_answer.index})
        return reverse(self.next_step_url, kwargs=kwargs)

    def get_url_context(self):
        kwargs = {}
        for key in [self.interviewee_slug, 'survey', 'response']:
            if self.kwargs.has_key(key) and self.kwargs.get(key) is not None:
                kwargs[key] = self.kwargs.get(key)
        return kwargs


class AnswerNextView(AnswerUpdateView):

    """
    Straight through to ``Response`` complete when all questions
    have been answered.
    """

    next_step_url = 'survey_answer_next'

    def get_object(self, queryset=None):
        # We always override the *index* by the latest unanswered question
        # to avoid skipping over questions and unintended redirect to results.
        return self.get_next_answer()

    def form_valid(self, form):
        next_answer = self.get_next_answer()
        if not next_answer:
            response = self.get_response()
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

    def get_url_context(self):
        kwargs = {}
        for key in [self.interviewee_slug, 'survey', 'response']:
            if self.kwargs.has_key(key) and self.kwargs.get(key) is not None:
                kwargs[key] = self.kwargs.get(key)
        return kwargs

    def get_context_data(self, **kwargs):
        context = super(ResponseResultView, self).get_context_data(**kwargs)
        response = self.get_response()
        score, answers = Response.objects.get_score(response)
        context.update(self.get_url_context())
        context.update({'response': response,
            # only response slug available through get_url_context()
            'answers': answers, 'score': score})
        return context

    def post(self, request, *args, **kwargs):
        # The csrftoken in valid when we get here. That's all that matters.
        response = self.get_response()
        response.is_frozen = True
        response.save()
        return self.get(request, *args, **kwargs)


class ResponseCreateView(SurveyModelMixin, IntervieweeMixin, CreateView):
    """
    Creates a ``Response`` of a ``User`` to a ``SurveyModel``
    """

    model = Response
    form_class = ResponseCreateForm
    next_step_url = 'survey_answer_next'

    def __init__(self, *args, **kwargs):
        super(ResponseCreateView, self).__init__(*args, **kwargs)
        self.survey = None

    def form_valid(self, form):
        # We are going to create all the Answer records for that Response here.
        result = super(ResponseCreateView, self).form_valid(form)
        response = self.object
        for question in Question.objects.filter(survey=response.survey):
            Answer.objects.create(response=response,
                                  question=question,
                                  index=question.order)
        return result

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
                       'user': self.get_interviewee()})
        return kwargs

    def get_success_url(self):
        kwargs = {}
        for key in [self.interviewee_slug, 'survey']:
            if self.kwargs.has_key(key) and self.kwargs.get(key) is not None:
                kwargs[key] = self.kwargs.get(key)
        kwargs.update({'response': self.object.slug})
        return reverse(self.next_step_url, kwargs=kwargs)
