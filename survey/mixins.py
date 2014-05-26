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

from django.shortcuts import get_object_or_404
from django.views.generic.detail import SingleObjectMixin

from survey.compat import User
from survey.models import Response, Question, SurveyModel

class IntervieweeMixin(object):
    """
    Returns a User, either based on the interviewee or else, if none exists,
    the request.user.
    """

    interviewee_slug = 'interviewee'

    def get_interviewee(self):
        if self.request.user.is_authenticated():
            try:
                interviewee = User.objects.get(
                    username=self.kwargs.get(self.interviewee_slug))
            except User.DoesNotExist:
                interviewee = self.request.user
        else:
            interviewee = None
        return interviewee


class QuestionMixin(SingleObjectMixin):

    num_url_kwarg = 'num'
    survey_url_kwarg = 'survey'

    def get_object(self, queryset=None):
        """
        Returns a question object based on the URL.
        """
        index = self.kwargs.get(self.num_url_kwarg, 1)
        slug = self.kwargs.get(self.survey_url_kwarg, None)
        survey = get_object_or_404(
            SurveyModel, slug__exact=slug)
        return get_object_or_404(
            Question, survey=survey, order=index)


class SurveyModelMixin(object):
    """
    Returns a ``Survey`` object associated with the request URL.
    """
    survey_url_kwarg = 'survey'

    def get_survey(self):
        return get_object_or_404(SurveyModel, slug=self.kwargs.get(
                self.survey_url_kwarg))


class ResponseMixin(IntervieweeMixin, SurveyModelMixin):
    """
    Returns a ``Response`` to a ``SurveyModel``.
    """

    response_url_kwarg = 'response'

    def get_response(self):
        """
        Returns the ``Response`` object associated with this URL.
        """
        response = None
        response_slug = self.kwargs.get(self.response_url_kwarg)
        if response_slug:
            # We have an id for the response, let's get it and check
            # the user has rights to it.
            response = get_object_or_404(Response, slug=response_slug)
        else:
            # Well no id, let's see if we can find a response from
            # a survey slug and a user
            interviewee = self.get_interviewee()
            response = get_object_or_404(Response,
                survey=self.get_survey(), user=interviewee)
        return response


