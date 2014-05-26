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

import datetime, json, logging

from django.core.mail import send_mail
from django.core.urlresolvers import reverse, reverse_lazy
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.views.generic import (CreateView, DeleteView, DetailView,
    FormView, ListView, RedirectView, UpdateView)
from django.views.generic.detail import SingleObjectMixin
from django.template.defaultfilters import slugify
from saas.models import Organization
from survey import settings

from survey.models import Answer, SurveyModel, Response, Question
from survey.forms import SurveyForm, SendSurveyForm


LOGGER = logging.getLogger(__name__)


class SurveyCreateView(CreateView):
    """
    Create a new survey
    """

    model = SurveyModel
    form_class = SurveyForm
    slug_url_kwarg = 'survey'
    success_url = reverse_lazy('survey_list')

    def get_initial(self):
        """
        Returns the initial data to use for forms on this view.
        """
        kwargs = super(SurveyCreateView, self).get_initial()
        if self.kwargs.has_key('organization'):
            organization = get_object_or_404(
                Organization, slug__exact=self.kwargs.get('organization'))
        else:
            managed = Organization.objects.find_managed(self.request.user)
            if managed.exists():
                organization = managed.first()
            else:
                raise Http404
        kwargs.update({'organization': organization})
        return kwargs


class SurveyDeleteView(DeleteView):
    """
    Delete a survey
    """
    model = SurveyModel
    slug_url_kwarg = 'survey'
    success_url = reverse_lazy('survey_list')


class SurveyListView(ListView):
    """
    List of surveys for an organization.
    """
    model = SurveyModel
    slug_url_kwarg = 'survey'

    def get_queryset(self):
        if self.kwargs.has_key('organization'):
            organization = get_object_or_404(
                Organization, slug__exact=self.kwargs.get('organization'))
            queryset = SurveyModel.objects.filter(organization=organization)
        else:
            queryset = SurveyModel.objects.all()
        return queryset

    def get_context_data(self, *args, **kwargs):
        context = super(SurveyListView, self).get_context_data(*args, **kwargs)
        return context


class SurveyPublishView(RedirectView):
    """
    Toggle Publish/Publish for a survey.
    """

    url = 'survey_list'
    slug_url_kwarg = 'survey'

    def post(self, request, *args, **kwargs):
        survey = get_object_or_404(SurveyModel, slug__exact=kwargs.get('slug'))
        if survey.published:
            survey.published = False
            survey.end_date = datetime.datetime.now()
        else:
            survey.published = True
            if not survey.start_date:
                survey.start_date = datetime.datetime.now()
        survey.save()
        return super(SurveyPublishView, self).post(request, *args, **kwargs)


class SurveyResultView(DetailView):
    """
    Show the results of a survey.
    """

    model = SurveyModel
    slug_url_kwarg = 'survey'
    template_name = 'survey/result.html'

    def get_context_data(self, **kwargs):
        context = super(SurveyResultView, self).get_context_data(**kwargs)
        number_interviewees = Response.objects.filter(
            survey=self.object).count()
        questions = Question.objects.filter(
            survey=self.object).order_by('order')
        # Answers that cannot be aggregated.
        #
        # The structure of the aggregated dataset returned to the client will
        # look like:
        # [ { "key": ``slug for Question``,
        #     "values": [ ``Answer.body`` ... ] },
        #   ... ]
        individuals = []
        for question in Question.objects.filter(
            survey=self.object, question_type=Question.TEXT):
            individuals += [{
                 'key': slugify("%d" % question.order),
# XXX Might be better
#                'key': slugify("%s-%d"
#                    % (question.survey.slug, question.order)),
                'values': Answer.objects.filter(
                    question=question).values('body')}]

        # Aggregate results for questions which have a fixed given number of
        # possible choices.
        #
        # The structure of the aggregated dataset returned to the client will
        # look like:
        # [ { "key": ``Question.slug``,
        #     "values": [ { "label": ``One possible choice for a Question``,
        #                   "value": ``Number of Answers for that choice``,
        #                 }, ...] },
        #   ... ]
        aggregates = []
        for question in Question.objects.filter(
            survey=self.object).exclude(question_type=Question.TEXT):
            aggregate = {}
            for choice, _ in question.get_choices():
                aggregate[choice] = 0

            # Populate the aggregate
            for answer in Answer.objects.filter(question=question):
                if question.question_type == Question.INTEGER:
                    choice = answer.body
                    if choice in aggregate:
                        aggregate[choice] = aggregate[choice] + 1
                    else:
                        LOGGER.error("'%s' not found in %s", choice, aggregate)

                elif question.question_type == Question.RADIO:
                    choice = answer.body
                    if choice in aggregate:
                        aggregate[choice] = aggregate[choice] + 1
                    else:
                        LOGGER.error("'%s' not found in %s", choice, aggregate)

                elif question.question_type == Question.SELECT_MULTIPLE:
                    for choice in answer.get_multiple_choices():
                        if choice in aggregate:
                            aggregate[choice] = aggregate[choice] + 1
                        else:
                            LOGGER.error(
                                "'%s' not found in %s", choice, aggregate)

            # Convert to json-ifiable format
            values = []
            for label, value in aggregate.items():
                if self.object.quizz_mode and label == question.correct_answer:
                    values += [{
                        "label": "%s %s" % (label, settings.CORRECT_MARKER),
                        "value": value}]
                else:
                    values += [{"label": label, "value": value}]
            aggregates += [{
                # XXX Might be better to use 'key': slugify("%s-%d"
                #     % (question.survey.slug, question.order))
                'key': slugify("%d" % question.order),
                'values': values}]

        context.update({
                'survey': self.object,
                'questions': questions,
                'number_interviewees': number_interviewees,
                'individuals': individuals,
                'aggregates': json.dumps(aggregates)})
        return context


class SurveySendView(SingleObjectMixin, FormView):
    """
    Send an email to a set of users to take a survey.
    """

    model = SurveyModel
    form_class = SendSurveyForm
    slug_url_kwarg = 'survey'
    template_name = 'survey/send.html'
    success_url = reverse_lazy('survey_list')

    def __init__(self, *args, **kwargs):
        super(SurveySendView, self).__init__(*args, **kwargs)
        self.object = None

    def get_initial(self):
        self.object = self.get_object()
        kwargs = super(SurveySendView, self).get_initial()
        kwargs.update({'from_address': settings.DEFAULT_FROM_EMAIL,
            'message': "Please complete our quick survey at %s"
            % self.request.build_absolute_uri(
                    reverse('survey_response_new', args=(self.object,)))})
        return kwargs

    def form_valid(self, form):
        email_addresses = form.cleaned_data['to_addresses'].split('\r\n')
        send_mail('Please complete %s' % self.object.name,
                  form.cleaned_data['message'],
                  form.cleaned_data['from_address'],
                  email_addresses, fail_silently=False)
        return super(SurveySendView, self).form_valid(form)


class SurveyUpdateView(UpdateView):
    """
    Update an existing survey.
    """

    model = SurveyModel
    form_class = SurveyForm
    slug_url_kwarg = 'survey'
    success_url = reverse_lazy('survey_list')
