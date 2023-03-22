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

import datetime, json, logging

from django.core.mail import send_mail
from django.views.generic import (DetailView,
    FormView, ListView, RedirectView, UpdateView)
from django.template.defaultfilters import slugify

from .. import settings
from ..compat import six, reverse, reverse_lazy
from ..helpers import update_context_urls
from ..mixins import BelongsMixin, CampaignMixin
from ..models import Answer, Campaign, Sample
from ..forms import CampaignForm, SendCampaignForm
from ..utils import get_question_model


LOGGER = logging.getLogger(__name__)


class CampaignListView(BelongsMixin, ListView):
    """
    List of campaigns for an account.
    """
    model = Campaign
    slug_url_kwarg = 'campaign'
    template_name = 'survey/campaigns/index.html'

    def get_queryset(self):
        if self.account:
            queryset = Campaign.objects.filter(account=self.account)
        else:
            queryset = Campaign.objects.all()
        return queryset

    def get_context_data(self, **kwargs):
        context = super(CampaignListView, self).get_context_data(**kwargs)
        update_context_urls(context, {
            'survey_api_campaign_list': reverse('survey_api_campaign_list',
                kwargs=self.get_url_kwargs(**kwargs))})
        return context


class CampaignPublishView(CampaignMixin, RedirectView):
    """
    Toggle Publish/Publish for a campaign.
    """

    url = 'survey_campaign_list'
    slug_url_kwarg = 'campaign'

    def post(self, request, *args, **kwargs):
        campaign = self.campaign
        if campaign.active:
            campaign.active = False
        else:
            campaign.active = True
            if not campaign.created_at:
                campaign.created_at = datetime.datetime.now()
        campaign.save()
        return super(CampaignPublishView, self).post(request, *args, **kwargs)


class CampaignResultView(CampaignMixin, DetailView):
    """
    Show the results of a campaign.
    """
    model = Campaign
    template_name = 'survey/result.html'

    def get_context_data(self, **kwargs):
        #pylint:disable=too-many-locals
        context = super(CampaignResultView, self).get_context_data(**kwargs)
        question_model = get_question_model()
        number_interviewees = Sample.objects.filter(
            campaign=self.object).count()
        questions = question_model.objects.filter(
            campaign=self.object).order_by('rank') #XXX rank
        # Answers that cannot be aggregated.
        #
        # The structure of the aggregated dataset returned to the client will
        # look like:
        # [ { "slug": ``slug for Question``,
        #     "values": [ ``Answer.measured`` ... ] },
        #   ... ]
        individuals = []
        for question in question_model.objects.filter(
            campaign=self.object, ui_hint=question_model.TEXT):
            individuals += [{
                 'slug': slugify("%d" % question.rank), # XXX rank
# XXX Might be better
#                'slug': slugify("%s-%d"
#                    % (question.campaign.slug, question.rank)),
                'values': Answer.objects.filter(
                    question=question).values('text')}]

        # Aggregate results for questions which have a fixed given number of
        # possible choices.
        #
        # The structure of the aggregated dataset returned to the client will
        # look like:
        # [ { "key": ``question_model.slug``,
        #     "values": [ { "label": ``One possible choice for a Question``,
        #                   "value": ``Number of Answers for that choice``,
        #                 }, ...] },
        #   ... ]
        aggregates = []
        with_errors = {}
        for question in question_model.objects.filter(
            campaign=self.object).exclude(ui_hint=question_model.TEXT):
            aggregate = {}
            for choice, _ in question.choices:
                aggregate[choice] = 0

            # Populate the aggregate
            for answer in Answer.objects.filter(question=question):
                choice = answer.measured
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
                # XXX Might be better to use 'slug': slugify("%s-%d"
                #     % (question.campaign.slug, question.rank))
                'slug': slugify("%d" % question.rank),  # XXX rank
                'values': values}]
        if with_errors:
            LOGGER.error("Answers with an invalid choice\n%s",
                with_errors, extra={'request': self.request})

        context.update({
                'campaign': self.object,
                'questions': questions,
                'number_interviewees': number_interviewees,
                'individuals': individuals,
                ## Careful! Allowing user generated text in this object
                ## would allow XSS attacks
                ## https://code.djangoproject.com/ticket/17419
                'aggregates': json.dumps(aggregates)})
        return context


class CampaignSendView(CampaignMixin, FormView):
    """
    Send an email to a set of users to take a campaign.
    """
    model = Campaign
    form_class = SendCampaignForm
    template_name = 'survey/send.html'
    success_url = reverse_lazy('survey_campaign_list')

    def __init__(self, *args, **kwargs):
        super(CampaignSendView, self).__init__(*args, **kwargs)
        self.object = None

    def get_initial(self):
        self.object = self.campaign
        kwargs = super(CampaignSendView, self).get_initial()
        kwargs.update({'from_address': settings.DEFAULT_FROM_EMAIL,
            'message': "Please complete our quick campaign at %s"
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


class CampaignUpdateView(CampaignMixin, UpdateView):
    """
    Update an existing campaign.
    """
    model = Campaign
    form_class = CampaignForm
    success_url = reverse_lazy('survey_campaign_list')
    slug_url_kwarg = CampaignMixin.campaign_url_kwarg
