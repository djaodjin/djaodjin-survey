# Copyright (c) 2016, DjaoDjin inc.
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

from . import settings
from .models import Matrix, EditableFilter, Question, Response, SurveyModel
from .utils import get_account_model


class AccountMixin(object):

    account_kwarg_url = 'organization'

    @property
    def account(self):
        if not hasattr(self, '_account'):
            self._account = self.get_account()
        return self._account

    def get_account(self):
        if self.kwargs.has_key(self.account_kwarg_url):
            account_model = get_account_model()
            kwargs = {'%s__exact' % settings.ACCOUNT_LOOKUP_FIELD:
                self.kwargs.get(self.account_kwarg_url)}
            return get_object_or_404(account_model, **kwargs)
        return None

    def get_context_data(self, *args, **kwargs):
        context = super(AccountMixin, self).get_context_data(*args, **kwargs)
        context.update({'account': self.account})
        return context

    def get_url_kwargs(self):
        kwargs = {}
        for url_kwarg in [self.account_kwarg_url]:
            url_kwarg_val = self.kwargs.get(url_kwarg, None)
            if url_kwarg_val:
                kwargs.update({url_kwarg: url_kwarg_val})
        return kwargs


class IntervieweeMixin(object):
    """
    Returns an Account, either based on the interviewee or else, if none exists,
    the request.user.
    """

    interviewee_slug = 'interviewee'

    def get_interviewee(self):
        if self.request.user.is_authenticated():
            account_model = get_account_model()
            try:
                kwargs = {'%s__exact' % settings.ACCOUNT_LOOKUP_FIELD:
                    self.kwargs.get(self.interviewee_slug)}
                interviewee = get_object_or_404(account_model, **kwargs)
            except account_model.DoesNotExist:
                interviewee = self.request.user
        else:
            interviewee = None
        return interviewee

    def get_reverse_kwargs(self):
        """
        List of kwargs taken from the url that needs to be passed through
        to ``get_success_url``.
        """
        return [self.interviewee_slug, 'survey']

    def get_url_context(self):
        """
        Returns ``kwargs`` value to use when calling ``reverse``
        in ``get_success_url``.
        """
        kwargs = {}
        for key in self.get_reverse_kwargs():
            if self.kwargs.has_key(key) and self.kwargs.get(key) is not None:
                kwargs[key] = self.kwargs.get(key)
        return kwargs


class QuestionMixin(SingleObjectMixin):

    num_url_kwarg = 'num'
    survey_url_kwarg = 'survey'

    def get_object(self, queryset=None):
        """
        Returns a question object based on the URL.
        """
        rank = self.kwargs.get(self.num_url_kwarg, 1)
        slug = self.kwargs.get(self.survey_url_kwarg, None)
        survey = get_object_or_404(
            SurveyModel, slug__exact=slug)
        return get_object_or_404(
            Question, survey=survey, rank=rank)


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

    @property
    def sample(self):
        if not hasattr(self, '_sample'):
            self._sample = self.get_response()
        return self._sample

    def get_response(self, url_kwarg=None):
        """
        Returns the ``Response`` object associated with this URL.
        """
        if not url_kwarg:
            url_kwarg = self.response_url_kwarg
        response = None
        response_slug = self.kwargs.get(url_kwarg)
        if response_slug:
            # We have an id for the response, let's get it and check
            # the user has rights to it.
            response = get_object_or_404(Response, slug=response_slug)
        else:
            # Well no id, let's see if we can find a response from
            # a survey slug and a account
            interviewee = self.get_interviewee()
            response = get_object_or_404(Response,
                survey=self.get_survey(), account=interviewee)
        return response

    def get_reverse_kwargs(self):
        """
        List of kwargs taken from the url that needs to be passed through
        to ``get_success_url``.
        """
        return [self.interviewee_slug, 'survey', self.response_url_kwarg]


class MatrixQuerysetMixin(AccountMixin):

    @staticmethod
    def get_queryset():
        return Matrix.objects.all()


class MatrixMixin(MatrixQuerysetMixin):

    matrix_url_kwarg = 'matrix'

    @property
    def matrix(self):
        if not hasattr(self, '_matrix'):
            self._matrix = get_object_or_404(Matrix,
                    slug=self.kwargs.get(self.matrix_url_kwarg))
        return self._matrix


class EditableFilterMixin(AccountMixin):

    editable_filter_url_kwarg = 'editable_filter'

    @property
    def editable_filter(self):
        if not hasattr(self, '_editable_filter'):
            self._editable_filter = get_object_or_404(EditableFilter,
                    slug=self.kwargs.get(self.editable_filter_url_kwarg))
        return self._editable_filter
