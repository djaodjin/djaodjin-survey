# Copyright (c) 2022, DjaoDjin inc.
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

from __future__ import unicode_literals

import datetime, logging

from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.db import connections
from django.db.models import Q, F
from django.http import Http404
import monotonic
from rest_framework.generics import get_object_or_404

from . import settings
from .compat import gettext_lazy as _, is_authenticated
from .helpers import datetime_or_now
from .models import (Campaign, EnumeratedQuestions, EditableFilter, Matrix,
    Sample)
from .utils import (get_account_model, get_belongs_model, get_question_model,
    is_portfolios_bypass)


LOGGER = logging.getLogger(__name__)


class AccountMixin(object):
    """
    Mixin to use in views that will retrieve an account object (out of
    ``account_queryset``) associated to a slug parameter (``account_url_kwarg``)
    in the URL.
    If either ``account_url_kwarg`` is ``None`` or absent from the URL pattern,
    ``account`` will default to the ``request.user`` when the account model is
    compatible with the `User` model, else ``account`` will be ``None``.
    """
    account_queryset = get_account_model().objects.all()
    account_lookup_field = settings.ACCOUNT_LOOKUP_FIELD
    account_url_kwarg = settings.ACCOUNT_URL_KWARG

    @property
    def account(self):
        if not hasattr(self, '_account'):
            if (self.account_url_kwarg is not None
                and self.account_url_kwarg in self.kwargs):
                if self.account_queryset is None:
                    raise ImproperlyConfigured(
                        "%(cls)s.account_queryset is None. Define "
                        "%(cls)s.account_queryset." % {
                            'cls': self.__class__.__name__
                        }
                    )
                if self.account_lookup_field is None:
                    raise ImproperlyConfigured(
                        "%(cls)s.account_lookup_field is None. Define "
                        "%(cls)s.account_lookup_field as the field used "
                        "to retrieve accounts in the database." % {
                            'cls': self.__class__.__name__
                        }
                    )
                kwargs = {'%s__exact' % self.account_lookup_field:
                    self.kwargs.get(self.account_url_kwarg)}
                try:
                    self._account = self.account_queryset.filter(**kwargs).get()
                except self.account_queryset.model.DoesNotExist:
                    #pylint: disable=protected-access
                    raise Http404(_("No %(verbose_name)s found matching"\
                        "the query") % {'verbose_name':
                        self.account_queryset.model._meta.verbose_name})
            else:
                self._account = None
                if (isinstance(get_account_model(), get_user_model()) and
                    is_authenticated(self.request)):
                    self._account = self.request.user
        return self._account

    def get_context_data(self, **kwargs):
        context = super(AccountMixin, self).get_context_data(**kwargs)
        context.update({self.account_url_kwarg: self.account})
        return context

    def get_reverse_kwargs(self):
        """
        List of kwargs taken from the url that needs to be passed through
        to ``get_success_url``.
        """
        if self.account_url_kwarg:
            return [self.account_url_kwarg]
        return []

    def get_url_kwargs(self, **kwargs):
        url_kwargs = {}
        if not kwargs:
            kwargs = self.kwargs
        for url_kwarg in self.get_reverse_kwargs():
            url_kwarg_val = kwargs.get(url_kwarg, None)
            if url_kwarg_val:
                url_kwargs.update({url_kwarg: url_kwarg_val})
        return url_kwargs


class BelongsMixin(AccountMixin):
    """
    Mixin to use in views that will retrieve an account object which
    is associated to a campaign or matrix.
    """
    account_queryset = get_belongs_model().objects.all()
    account_lookup_field = settings.BELONGS_LOOKUP_FIELD


class DateRangeContextMixin(object):

    forced_date_range = True
    default_ends_at = None

    @property
    def start_at(self):
        if not hasattr(self, '_start_at'):
            self._start_at = self.get_query_param('start_at')
            if self._start_at:
                self._start_at = datetime_or_now(self._start_at.strip('"'))
        return self._start_at

    @property
    def ends_at(self):
        if not hasattr(self, '_ends_at'):
            self._ends_at = self.get_query_param('ends_at')
            if self.forced_date_range or self._ends_at:
                if self._ends_at is not None:
                    self._ends_at = self._ends_at.strip('"')
                else:
                    self._ends_at = self.default_ends_at
                self._ends_at = datetime_or_now(self._ends_at)
        return self._ends_at

    @property
    def timezone(self):
        if not hasattr(self, '_timezone'):
            self._timezone = self.get_query_param('timezone')
        return self._timezone

    def get_query_param(self, key, default_value=None):
        try:
            return self.request.query_params.get(key, default_value)
        except AttributeError:
            pass
        return self.request.GET.get(key, default_value)

    def get_context_data(self, **kwargs):
        context = super(DateRangeContextMixin, self).get_context_data(**kwargs)
        if self.start_at:
            context.update({'start_at': self.start_at})
        if self.ends_at:
            context.update({'ends_at': self.ends_at})
        return context


class CampaignMixin(object):
    """
    Returns a ``Campaign`` object associated with the request URL.
    """
    campaign_url_kwarg = 'campaign'
    path_url_kwarg = 'path'

    @property
    def campaign(self):
        if not hasattr(self, '_campaign'):
            campaign_slug = self.kwargs.get(self.campaign_url_kwarg)
            if campaign_slug:
                self._campaign = get_object_or_404(
                    Campaign.objects.all(), slug=campaign_slug)
            else:
                self._campaign = None
        return self._campaign

    @property
    def db_path(self):
        if not hasattr(self, '_db_path'):
            self._db_path = self.kwargs.get(self.path_url_kwarg, '').replace(
                settings.URL_PATH_SEP, settings.DB_PATH_SEP)
            if not self._db_path.startswith(settings.DB_PATH_SEP):
                self._db_path = settings.DB_PATH_SEP + self._db_path
        return self._db_path

    def get_reverse_kwargs(self):
        """
        List of kwargs taken from the url that needs to be passed through
        to ``get_success_url``.
        """
        return super(CampaignMixin, self).get_reverse_kwargs() + [
            self.campaign_url_kwarg]

    def get_context_data(self, **kwargs):
        context = super(CampaignMixin, self).get_context_data(**kwargs)
        context.update({self.campaign_url_kwarg: self.campaign})
        return context


class CampaignQuerysetMixin(BelongsMixin):

    def get_queryset(self):
        if self.account:
            return Campaign.objects.filter(account=self.account)
        return Campaign.objects.all()


class CampaignQuestionMixin(CampaignMixin):

    num_url_kwarg = 'num'
    model = EnumeratedQuestions

    def get_queryset(self):
        return self.model.objects.filter(
            campaign=self.campaign).order_by('rank')

    def get_object(self, queryset=None):
        """
        Returns a question object based on the URL.
        """
        if not queryset:
            queryset = self.get_queryset()
        return get_object_or_404(queryset,
            rank=self.kwargs.get(self.num_url_kwarg, 1))


class EditableFilterMixin(object):

    editable_filter_url_kwarg = 'editable_filter'

    @property
    def editable_filter(self):
        if not hasattr(self, '_editable_filter'):
            self._editable_filter = get_object_or_404(
                EditableFilter.objects.all(),
                slug=self.kwargs.get(self.editable_filter_url_kwarg))
        return self._editable_filter


class MatrixQuerysetMixin(BelongsMixin):

    def get_queryset(self):
        # We want to show all matrices but only populate with account data.
        #if self.account:
        #    return Matrix.objects.filter(account=self.account)
        return Matrix.objects.all()


class MatrixMixin(MatrixQuerysetMixin):

    matrix_url_kwarg = 'path'

    @property
    def matrix(self):
        if not hasattr(self, '_matrix'):
            self._matrix = get_object_or_404(self.get_queryset(),
                    slug=self.kwargs.get(self.matrix_url_kwarg))
        return self._matrix


class QuestionMixin(object):
    """
    Mixin when a ``path`` identifying a question is passed as a query
    parameter.
    """
    path_url_kwarg = 'path'

    @property
    def db_path(self):
        if not hasattr(self, '_db_path'):
            self._db_path = self.kwargs.get(self.path_url_kwarg, '').replace(
                settings.URL_PATH_SEP, settings.DB_PATH_SEP)
            if not self._db_path.startswith(settings.DB_PATH_SEP):
                self._db_path = settings.DB_PATH_SEP + self._db_path
        return self._db_path

    @property
    def question(self):
        if not hasattr(self, '_question'):
            self._question = get_object_or_404(
                get_question_model().objects.all(),
                path=self.db_path)
        return self._question


class SampleMixin(QuestionMixin, AccountMixin):
    """
    Returns a ``Sample`` to a ``Campaign``.
    """

    # We have to use a special url_kwarg here because 'sample'
    # interfers with the way rest_framework handles **kwargs.
    sample_url_kwarg = 'sample'
    campaign_url_kwarg = 'campaign'

    def get_reverse_kwargs(self):
        """
        List of kwargs taken from the url that needs to be passed through
        to ``get_success_url``.
        """
        return super(SampleMixin, self).get_reverse_kwargs() + [
            self.sample_url_kwarg, self.campaign_url_kwarg,
            self.path_url_kwarg]

    @property
    def path(self):
        if not hasattr(self, '_path'):
            self._path = self.kwargs.get(self.path_url_kwarg, '')
            if self._path and not self._path.startswith('/'):
                self._path = '/%s' % self._path
        return self._path

    @property
    def sample(self):
        if not hasattr(self, '_sample'):
            self._sample = self.get_sample()
        return self._sample

    def get_sample(self, url_kwarg=None):
        """
        Returns the ``Sample`` object associated with this URL.
        """
        if not url_kwarg:
            url_kwarg = self.sample_url_kwarg
        sample = None
        sample_slug = self.kwargs.get(url_kwarg)
        if sample_slug:
            # We have an id for the sample, let's get it and check
            # the user has rights to it.
            try:
                if is_portfolios_bypass(self.account, request=self.request):
                    queryset = Sample.objects.filter(slug=sample_slug)
                else:
                    queryset = Sample.objects.filter(
                        Q(account=self.account) |
                        (Q(is_frozen=True) &
                         Q(account__portfolios__grantee=self.account) &
                         Q(account__portfolios__ends_at__gte=F('created_at'))),
                        slug=sample_slug)
                sample = queryset.select_related('campaign').distinct().get()
            except Sample.DoesNotExist:
                raise Http404(_("Cannot find Sample(slug='%(sample)s')") % {
                    'sample': sample_slug})
        else:
            # Well no id, let's see if we can find a sample from
            # a campaign slug and a account
            campaign_slug = self.kwargs.get(self.campaign_url_kwarg)
            if campaign_slug:
                try:
                    sample = Sample.objects.filter(account=self.account,
                        campaign__slug=campaign_slug).select_related(
                        'campaign').get()
                except Sample.DoesNotExist:
                    raise Http404(_("Cannot find Sample("\
                        "account__slug='%(account)s',"\
                        " campaign__slug='%(campaign)s')") % {
                        'account': self.account,
                        'campaign': campaign_slug})
        return sample


class TimersMixin(object):
    """
    Mixin used to track performance of queries
    """
    enable_report_queries = True

    def _start_time(self):
        if not self.enable_report_queries:
            return
        self.start_time = monotonic.monotonic()

    def _report_queries(self, descr=None):
        if not self.enable_report_queries:
            return
        if not hasattr(self, 'start_time'):
            return
        end_time = monotonic.monotonic()
        if descr is None:
            descr = ""
        nb_queries = 0
        duration = datetime.timedelta()
        for conn in connections.all():
            nb_queries += len(conn.queries)
            for query in conn.queries:
                try:
                    convert = datetime.datetime.strptime(query['time'], "%S.%f")
                    duration += datetime.timedelta(
                        0, convert.second, convert.microsecond)
                except ValueError:
                    duration += datetime.timedelta()
                    # days, seconds, microseconds
        LOGGER.debug("(elapsed: %.2fs) %s: %s for %d SQL queries",
            (end_time - self.start_time), descr, duration, nb_queries)
