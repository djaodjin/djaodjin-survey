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

import datetime, json, logging

from django.core.mail import send_mail
from django.core.urlresolvers import reverse, reverse_lazy
from django.shortcuts import get_object_or_404
from django.views.generic import (CreateView, DeleteView, DetailView,
    FormView, ListView, RedirectView, UpdateView)
from django.views.generic.detail import SingleObjectMixin
from django.template.defaultfilters import slugify
from django.utils import six

from .. import settings
from ..mixins import AccountMixin
from ..models import Answer, Campaign, Sample, Question
from ..forms import CampaignForm, SendCampaignForm


LOGGER = logging.getLogger(__name__)


class CampaignCreateView(AccountMixin, CreateView):
    """
    Create a new survey
    """

    model = Campaign
    form_class = CampaignForm
    slug_url_kwarg = 'survey'
    pattern_name = 'survey_edit'

    def get_initial(self):
        """
        Returns the initial data to use for forms on this view.
        """
        kwargs = super(CampaignCreateView, self).get_initial()
        kwargs.update({'account': self.account})
        return kwargs

    def get_success_url(self):
        return reverse_lazy(self.pattern_name, args=(self.object,))


class CampaignDeleteView(DeleteView):
    """
    Delete a survey
    """
    model = Campaign
    slug_url_kwarg = 'survey'
    success_url = reverse_lazy('survey_list')


class CampaignListView(AccountMixin, ListView):
    """
    List of surveys for an account.
    """
    model = Campaign
    slug_url_kwarg = 'survey'

    def get_queryset(self):
        if self.account:
            queryset = Campaign.objects.filter(account=self.account)
        else:
            queryset = Campaign.objects.all()
        return queryset

    def get_context_data(self, *args, **kwargs):
        context = super(CampaignListView, self).get_context_data(
            *args, **kwargs)
        return context


class CampaignPublishView(RedirectView):
    """
    Toggle Publish/Publish for a survey.
    """

    url = 'survey_list'
    slug_url_kwarg = 'survey'

    def post(self, request, *args, **kwargs):
        survey = get_object_or_404(Campaign,
            slug__exact=kwargs.get('survey'))
        if survey.active:
            survey.active = False
        else:
            survey.active = True
            if not survey.created_at:
                survey.created_at = datetime.datetime.now()
        survey.save()
        return super(CampaignPublishView, self).post(request, *args, **kwargs)


class CampaignResultView(DetailView):
    """
    Show the results of a survey.
    """

    model = Campaign
    slug_url_kwarg = 'survey'
    template_name = 'survey/result.html'

    def get_context_data(self, **kwargs):
        #pylint:disable=too-many-locals
        context = super(CampaignResultView, self).get_context_data(**kwargs)
        number_interviewees = Sample.objects.filter(
            survey=self.object).count()
        questions = Question.objects.filter(
            survey=self.object).order_by('rank')
        # Answers that cannot be aggregated.
        #
        # The structure of the aggregated dataset returned to the client will
        # look like:
        # [ { "key": ``slug for Question``,
        #     "values": [ ``Answer.measured`` ... ] },
        #   ... ]
        individuals = []
        for question in Question.objects.filter(
            survey=self.object, question_type=Question.TEXT):
            individuals += [{
                 'key': slugify("%d" % question.rank),
# XXX Might be better
#                'key': slugify("%s-%d"
#                    % (question.survey.slug, question.rank)),
                'values': Answer.objects.filter(
                    question=question).values('text')}]

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
        with_errors = {}
        for question in Question.objects.filter(
            survey=self.object).exclude(question_type=Question.TEXT):
            aggregate = {}
            for choice, _ in question.get_choices():
                aggregate[choice] = 0

            # Populate the aggregate
            for answer in Answer.objects.filter(question=question):
                if question.question_type == Question.INTEGER:
                    choice = answer.measured
                    if choice in aggregate:
                        aggregate[choice] = aggregate[choice] + 1
                    else:
                        with_errors[question] = with_errors.get(
                            question, []) + [answer]

                elif question.question_type == Question.RADIO:
                    choice = answer.measured
                    if choice in aggregate:
                        aggregate[choice] = aggregate[choice] + 1
                    else:
                        with_errors[question] = with_errors.get(
                            question, []) + [answer]

                elif question.question_type == Question.SELECT_MULTIPLE:
                    for choice in answer.get_multiple_choices():
                        if choice in aggregate:
                            aggregate[choice] = aggregate[choice] + 1
                        else:
                            with_errors[question] = with_errors.get(
                                question, []) + [answer]

            # Convert to json-ifiable format
            values = []
            for label, value in six.iteritems(aggregate):
                if self.object.quizz_mode and label == question.correct_answer:
                    values += [{
                        "label": "%s %s" % (label, settings.CORRECT_MARKER),
                        "value": value}]
                else:
                    values += [{"label": label, "value": value}]
            aggregates += [{
                # XXX Might be better to use 'key': slugify("%s-%d"
                #     % (question.survey.slug, question.rank))
                'key': slugify("%d" % question.rank),
                'values': values}]
        if with_errors:
            LOGGER.error("Answers with an invalid choice\n%s",
                with_errors, extra={'request': self.request})

        context.update({
                'survey': self.object,
                'questions': questions,
                'number_interviewees': number_interviewees,
                'individuals': individuals,
                ## Careful! Allowing user generated text in this object
                ## would allow XSS attacks
                ## https://code.djangoproject.com/ticket/17419
                'aggregates': json.dumps(aggregates)})
        return context


class CampaignSendView(SingleObjectMixin, FormView):
    """
    Send an email to a set of users to take a survey.
    """

    model = Campaign
    form_class = SendCampaignForm
    slug_url_kwarg = 'survey'
    template_name = 'survey/send.html'
    success_url = reverse_lazy('survey_list')

    def __init__(self, *args, **kwargs):
        super(CampaignSendView, self).__init__(*args, **kwargs)
        self.object = None

    def get_initial(self):
        self.object = self.get_object()
        kwargs = super(CampaignSendView, self).get_initial()
        kwargs.update({'from_address': settings.DEFAULT_FROM_EMAIL,
            'message': "Please complete our quick survey at %s"
            % self.request.build_absolute_uri(
                    reverse('survey_sample_new', args=(self.object,)))})
        return kwargs

    def form_valid(self, form):
        email_addresses = form.cleaned_data['to_addresses'].split('\r\n')
        send_mail('Please complete %s' % self.object.title,
                  form.cleaned_data['message'],
                  form.cleaned_data['from_address'],
                  email_addresses, fail_silently=False)
        return super(CampaignSendView, self).form_valid(form)


class CampaignUpdateView(UpdateView):
    """
    Update an existing survey.
    """

    model = Campaign
    form_class = CampaignForm
    slug_url_kwarg = 'survey'
    success_url = reverse_lazy('survey_list')
