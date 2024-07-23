# Copyright (c) 2024, DjaoDjin inc.
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

import datetime, logging, re
from collections import OrderedDict

from django.db import transaction, IntegrityError, models
from django.http import Http404
from django.template.defaultfilters import slugify
from rest_framework import generics, response as http, status
from rest_framework.exceptions import ValidationError
from rest_framework.mixins import DestroyModelMixin, UpdateModelMixin

from .. import settings
from ..compat import reverse, six
from ..docs import extend_schema
from ..filters import AggregateByPeriodFilter, OrderingFilter, SearchFilter
from ..helpers import construct_periods, convert_dates_to_utc, datetime_or_now
from ..mixins import (AccountMixin, CampaignMixin, DateRangeContextMixin,
    EditableFilterMixin as EditableFilterBaseMixin, MatrixMixin, SampleMixin)
from ..models import (Answer, Choice, Matrix, EditableFilter,
    EditableFilterEnumeratedAccounts, Sample, Unit, UnitEquivalences)
from ..pagination import MetricsPagination
from ..queries import get_benchmarks_counts
from ..utils import (get_accessible_accounts, get_account_model,
    get_question_model, get_engaged_accounts, get_account_serializer,
    get_question_serializer, handle_uniq_error)
from .base import QuestionListAPIView
from .serializers import (AccountsDateRangeQueryParamSerializer,
    UnitQueryParamSerializer, CohortSerializer, CohortAddSerializer,
    CompareQuestionSerializer,
    EditableFilterSerializer, EditableFilterCreateSerializer,
    EditableFilterUpdateSerializer,
    MatrixSerializer, SampleBenchmarksSerializer)


LOGGER = logging.getLogger(__name__)


class AccountsDateRangeMixin(object):

    accounts_start_at_url_kwarg = 'accounts_start_at'
    accounts_ends_at_url_kwarg = 'accounts_ends_at'

    @property
    def accounts_start_at(self):
        if not hasattr(self, '_accounts_start_at'):
            self._accounts_start_at = self.get_query_param(
                self.accounts_start_at_url_kwarg)
            if self._accounts_start_at:
                self._accounts_start_at = datetime_or_now(
                    self._accounts_start_at.strip('"'))
        return self._accounts_start_at

    @property
    def accounts_ends_at(self):
        if not hasattr(self, '_accounts_ends_at'):
            self._accounts_ends_at = self.get_query_param(
                self.accounts_ends_at_url_kwarg)
            if self._accounts_ends_at:
                self._accounts_ends_at = datetime_or_now(
                    self._accounts_ends_at.strip('"'))
        return self._accounts_ends_at

    def get_query_param(self, key, default_value=None):
        if not hasattr(self, '_accounts_date_range_serializer'):
            try:
                self._accounts_date_range_serializer = \
                    AccountsDateRangeQueryParamSerializer(
                        data=self.request.query_params)
            except AttributeError:
                self._accounts_date_range_serializer = \
                    AccountsDateRangeQueryParamSerializer(
                        data=self.request.GET)
            self._accounts_date_range_serializer.is_valid(raise_exception=True)
        param = self._accounts_date_range_serializer.validated_data.get(
            key, None)
        if param:
            return param
        try:
            return self.request.query_params.get(key, default_value)
        except AttributeError:
            pass
        return self.request.GET.get(key, default_value)


class EditableFilterMixin(AccountMixin, EditableFilterBaseMixin):

    @property
    def editable_filter(self):
        if not hasattr(self, '_editable_filter'):
            slug = self.kwargs.get(self.editable_filter_url_kwarg)
            self._editable_filter = generics.get_object_or_404(
                EditableFilter.objects.all(),
                account=self.account, slug=slug)
        return self._editable_filter


class BenchmarkMixin(DateRangeContextMixin, CampaignMixin):
    """
    Base class to aggregate answers
    """
    period_type_param = 'period_type'
    nb_periods_param = 'nb_periods'
    scale = 1
    default_unit = 'profiles'
    valid_units = ('percentage',)
    title = "Benchmarks"

    filter_backends = (AggregateByPeriodFilter,)

    @property
    def period_type(self):
        #pylint:disable=attribute-defined-outside-init
        if not hasattr(self, '_period_type'):
            self._period_type = self.get_query_param(self.period_type_param)
        return self._period_type

    @property
    def unit(self):
        #pylint:disable=attribute-defined-outside-init
        if not hasattr(self, '_unit'):
            self._unit = self.default_unit
            param_unit = self.get_query_param('unit')
            if param_unit is not None and param_unit in self.valid_units:
                self._unit = param_unit
        return self._unit


    def get_title(self):
        return self.title


    def get_accounts(self):
        """
        By default return all accounts. This method is intended to be overriden
        in subclasses to select specific set of accounts whose answers are
        aggregated.
        """
        return get_account_model().objects.all()


    def _flush_choices(self, questions_by_key, row, choices):
        """
        Populates `questions_by_key` with benchmark data aggregated in choices.
        """
        question_id = row.pk
        start_at = getattr(row, 'period', None)
        if question_id not in questions_by_key:
            question_path = row.question_path
            question_title = row.question_title
            default_unit = Unit(
                slug=row.question_default_unit_slug,
                title=row.question_default_unit_title,
                system=row.question_default_unit_system)
            questions_by_key[question_id] = {
                'path': question_path,
                'title': question_title,
                'ui_hint': None, # XXX unnecessary in benchmarks
                'default_unit': default_unit
            }
        question = questions_by_key[question_id]
        if not 'benchmarks' in question:
            question['benchmarks'] = [{
                'slug': slugify(self.get_title()),
                'title': self.get_title(),
                'values': []
            }]
        assert len(question['benchmarks']) == 1
        values = question['benchmarks'][0].get('values')
        if start_at:
            values += [(start_at, choices)]
        else:
            values += choices


    def get_questions_by_key(self, prefix=None, initial=None):
        """
        Returns a dictionnary of questions indexed by `pk` populated
        with aggregated benchmarks.
        """
        #pylint:disable=too-many-locals
        questions_by_key = super(BenchmarkMixin, self).get_questions_by_key(
            prefix=prefix, initial=initial)

        accounts = self.get_accounts()
        self.nb_accounts = accounts.count()
        if self.nb_accounts < 1:
            return questions_by_key

        period_type = self.period_type
        first_date = self.start_at
        if not first_date:
            first_sample_queryset = Sample.objects.filter(
                is_frozen=True, account__in=accounts).order_by('created_at')
            if self.campaign:
                first_sample_queryset = first_sample_queryset.filter(
                    campaign=self.campaign)
            first_sample = first_sample_queryset.first()
            if first_sample:
                # `construct_periods` will create periods that lands
                # on the same month/day each year.
                first_date = datetime.datetime(first_sample.created_at.year,
                    1, 1, tzinfo=first_sample.created_at.tzinfo)
            else:
                # XXX default because we need a date to pass
                # to `construct_periods`.
                first_date = datetime_or_now(
                    datetime.datetime(2018, 1, 1))

        date_periods = convert_dates_to_utc(
            construct_periods(first_date, self.ends_at,
                period_type=period_type, tzone=self.timezone))

        start_at = date_periods[0]
        for ends_at in date_periods[1:]:
            samples = []
            if accounts:
                # Calling `get_completed_assessments_at_by` with an `accounts`
                # arguments evaluating to `False` will return all the latest
                # frozen samples.
                samples = Sample.objects.get_completed_assessments_at_by(
                    self.campaign, start_at=start_at, ends_at=ends_at,
                    accounts=accounts)

            # samples that will be counted in the benchmark
            if samples:
                sql_query = get_benchmarks_counts(samples, prefix=prefix,
                    period_type=period_type)
                queryset = get_question_model().objects.raw(sql_query)

                choices = []
                prev_row = None
                prev_period_start_at = None
                for question in queryset:
                    question_id = question.pk
                    choice = question.choice
                    count = question.nb_samples
                    period_start_at = getattr(question, 'period', None)
                    if ((prev_row and prev_row.pk != question_id) or
                        (period_start_at and (prev_period_start_at and
                        prev_period_start_at != period_start_at))):
                        self._flush_choices(
                            questions_by_key, prev_row, choices)
                        choices = []
                    prev_period_start_at = period_start_at
                    prev_row = question
                    choices += [(choice, count)]
                if prev_row:
                    self._flush_choices(
                        questions_by_key, prev_row, choices)

            start_at = ends_at

        return questions_by_key


class BenchmarkAPIView(BenchmarkMixin, QuestionListAPIView):
    """
    Benchmarks against all profiles for a subset of questions

    Returns a list of questions decorated with a 'benchmarks' field
    that contains aggregated statistics accross the set of all profiles
    on the platform.

    Aggregation can be done for samples created in the time period
    [start_at,ends_at[, either as a whole period, or as period
    trenches (`yearly`, `monthly`).

    When `period_type` is specified, `nb_periods` and `ends_at` can
    be used instead of `start_at` to filter the samples.

    **Tags**: benchmarks

    **Examples**:

    .. code-block:: http

        GET /api/energy-utility/benchmarks/all/sustainability/\
esg-strategy-heading/formalized-esg-strategy HTTP/1.1

    responds

    .. code-block:: json

        {
            "title": "All",
            "unit": "profiles",
            "scale": 1,
            "labels": null,
            "count": 1,
            "results": [{
         "path": "/sustainability/esg-strategy-heading/formalized-esg-strategy",
              "title": "1.1 Does your company have a formalized ESG strategy?",
              "default_unit": {
                "slug": "yes-no",
                "title": "Yes/No",
                "system": "enum",
                "choices": []
              },
              "benchmarks": [{
                "slug": "all",
                "title": "All",
                "values": [
                  ["2018-01-01T00:00:00Z", ["Yes", 1] ]
                ]
              }]
           }]
        }
    """
    serializer_class = SampleBenchmarksSerializer
    pagination_class = MetricsPagination
    title = "All"


class BenchmarkAllIndexAPIView(BenchmarkAPIView):
    """
    Benchmarks against all profiles

    Returns a list of questions decorated with a 'benchmarks' field
    that contains aggregated statistics accross the set of all profiles
    on the platform.

    Aggregation can be done for samples created in the time period
    [start_at,ends_at[, either as a whole period, or as period
    trenches (`yearly`, `monthly`).

    When `period_type` is specified, `nb_periods` and `ends_at` can
    be used instead of `start_at` to filter the samples.

    **Tags**: benchmarks

    **Examples**:

    .. code-block:: http

        GET /api/energy-utility/benchmarks/all HTTP/1.1

    responds

    .. code-block:: json


        {
            "title": "All",
            "unit": "profiles",
            "scale": 1,
            "labels": null,
            "count": 2,
            "results": [{
         "path": "/sustainability/esg-strategy-heading/formalized-esg-strategy",
              "title": "1.1 Does your company have a formalized ESG strategy?",
              "default_unit": {
                "slug": "yes-no",
                "title": "Yes/No",
                "system": "enum",
                "choices": []
              },
              "benchmarks": [{
                "slug": "all",
                "title": "All",
                "values": [
                  ["2018-01-01T00:00:00Z", ["Yes", 1] ]
                ]
              }]
            }, {
         "path": "/sustainability/esg-strategy-heading/esg-point-person",
              "title": "1.1 Does your company have a ESG point person?",
              "default_unit": {
                "slug": "yes-no",
                "title": "Yes/No",
                "system": "enum",
                "choices": []
              },
              "benchmarks": [{
                "slug": "all",
                "title": "All",
                "values": [
                  ["2018-01-01T00:00:00Z", ["Yes", 1] ]
                ]
              }]
           }]
        }
    """

    @extend_schema(operation_id='benchmark_all_index')
    def get(self, request, *args, **kwargs):
        return super(BenchmarkAllIndexAPIView, self).get(
            request, *args, **kwargs)


class BenchmarkIndexAPIView(BenchmarkAllIndexAPIView):
    """
    Benchmarks against all profiles

    **Examples**:

    .. code-block:: http

        GET /api/energy-utility/benchmarks HTTP/1.1

    responds

    .. code-block:: json


        {
          "count": 4,
          "results": []
        }
    """

    @extend_schema(operation_id='benchmark_index')
    def get(self, request, *args, **kwargs):
        return super(BenchmarkIndexAPIView, self).get(request, *args, **kwargs)


class AccessiblesAccountsMixin(AccountsDateRangeMixin,
                               CampaignMixin, AccountMixin):
    """
    Query accounts by 'accessibles' affinity
    """

    def get_accounts(self):
        """
        Returns account accessibles by a profile in a specific date range.
        """
        return get_accessible_accounts([self.account], campaign=self.campaign,
            start_at=self.accounts_start_at, ends_at=self.accounts_ends_at,
            aggregate_set=True)


class AccessiblesBenchmarkAPIView(AccessiblesAccountsMixin, BenchmarkAPIView):
    """
    Benchmarks against accessible profiles for a subset of questions

    Returns a list of questions whose path is prefixed by `{path}`,
    decorated with a 'benchmarks' field that contains aggregated statistics
    accross the set of profiles accessible to a grantee `profile`.

    The set of profiles whose responses are taken into account in
    the aggregate can be reduced to a subset of profiles accessbile
    in the time period [accounts_start_at, accounts_ends_at[.

    Aggregation can be done for samples created in the time period
    [start_at,ends_at[, either as a whole period, or as period
    trenches (`yearly`, `monthly`).

    When `period_type` is specified, `nb_periods` and `ends_at` can
    be used instead of `start_at` to filter the samples.

    **Tags**: benchmarks

    **Examples**:

    .. code-block:: http

        GET /api/energy-utility/benchmarks/accessibles/sustainability/\
esg-strategy-heading/formalized-esg-strategy HTTP/1.1

    responds

    .. code-block:: json

        {
            "title": "Accessibles",
            "unit": "profiles",
            "scale": 1,
            "labels": null,
            "count": 1,
            "results": [{
         "path": "/sustainability/esg-strategy-heading/formalized-esg-strategy",
              "title": "1.1 Does your company have a formalized ESG strategy?",
              "default_unit": {
                "slug": "yes-no",
                "title": "Yes/No",
                "system": "enum",
                "choices": []
              },
              "benchmarks": [{
                "slug": "accessibles",
                "title": "Accessibles",
                "values": [
                  ["2018-01-01T00:00:00Z", {"Yes": 1}]
                ]
              }]
           }]
        }
    """
    title = "Tracked"

    def get_title(self):
        return self.account.printable_name

    @extend_schema(parameters=[AccountsDateRangeQueryParamSerializer,
        UnitQueryParamSerializer])
    def get(self, request, *args, **kwargs):
        return super(AccessiblesBenchmarkAPIView, self).get(
            request, *args, **kwargs)


class AccessiblesBenchmarkIndexAPIView(AccessiblesBenchmarkAPIView):
    """
    Benchmarks against accessible profiles

    Returns a list of questions decorated with a 'benchmarks' field
    that contains aggregated statistics accross the set of profiles
    accessible to a grantee `{profile}`.

    The set of profiles whose responses are taken into account in
    the aggregate can be reduced to a subset of profiles accessbile
    in the time period [accounts_start_at, accounts_ends_at[.

    Aggregation can be done for samples created in the time period
    [start_at, ends_at[, either as a whole period, or as period
    trenches (`yearly`, `monthly`).

    When `period_type` is specified, `nb_periods` and `ends_at` can
    be used instead of `start_at` to filter the samples.

    **Tags**: benchmarks

    **Examples**:

    .. code-block:: http

        GET /api/energy-utility/benchmarks/accessibles HTTP/1.1

    responds

    .. code-block:: json

        {
            "title": "Accessibles",
            "unit": "profiles",
            "scale": 1,
            "labels": null,
            "count": 1,
            "results": [{
         "path": "/sustainability/esg-strategy-heading/formalized-esg-strategy",
              "title": "1.1 Does your company have a formalized ESG strategy?",
              "default_unit": {
                "slug": "yes-no",
                "title": "Yes/No",
                "system": "enum",
                "choices": []
              },
              "benchmarks": [{
                "slug": "accessibles",
                "title": "Accessibles",
                "values": [
                  ["2018-01-01T00:00:00Z", {"Yes": 1}]
                ]
              }]
           }]
        }
    """

    @extend_schema(operation_id='accessibles_benchmark_index',
        parameters=[AccountsDateRangeQueryParamSerializer,
            UnitQueryParamSerializer])
    def get(self, request, *args, **kwargs):
        return super(AccessiblesBenchmarkIndexAPIView, self).get(
            request, *args, **kwargs)


class EngagedAccountsMixin(AccountsDateRangeMixin,
                           CampaignMixin, AccountMixin):
    """
    Query accounts by 'accessibles' affinity
    """

    def get_accounts(self):
        """
        Returns account accessibles by a profile in a specific date range.
        """
        return get_engaged_accounts([self.account], campaign=self.campaign,
            start_at=self.accounts_start_at, ends_at=self.accounts_ends_at,
            aggregate_set=True)


class EngagedBenchmarkAPIView(EngagedAccountsMixin, BenchmarkAPIView):
    """
    Benchmarks against engaged profiles for a subset of questions

    Returns a list of questions whose path is prefixed by `{path}`,
    decorated with a 'benchmarks' field that contains aggregated statistics
    accross the set of profiles engaged by a `profile`.

    The set of profiles whose responses are taken into account in
    the aggregate can be reduced to a subset of profiles engaged
    in the time period [accounts_start_at, accounts_ends_at[.

    Aggregation can be done for samples created in the time period
    [start_at,ends_at[, either as a whole period, or as period
    trenches (`yearly`, `monthly`).

    When `period_type` is specified, `nb_periods` and `ends_at` can
    be used instead of `start_at` to filter the samples.

    **Tags**: benchmarks

    **Examples**:

    .. code-block:: http

        GET /api/energy-utility/benchmarks/engaged/sustainability/\
esg-strategy-heading/formalized-esg-strategy HTTP/1.1

    responds

    .. code-block:: json

        {
            "title": "Engaged",
            "unit": "profiles",
            "scale": 1,
            "labels": null,
            "count": 1,
            "results": [{
         "path": "/sustainability/esg-strategy-heading/formalized-esg-strategy",
              "title": "1.1 Does your company have a formalized ESG strategy?",
              "default_unit": {
                "slug": "yes-no",
                "title": "Yes/No",
                "system": "enum",
                "choices": []
              },
              "benchmarks": [{
                "slug": "engaged",
                "title": "Engaged",
                "values": [
                  ["2018-01-01T00:00:00Z", {"Yes": 1}]
                ]
              }]
           }]
        }
    """
    title = "Engaged"

    def get_title(self):
        return self.account.printable_name

    @extend_schema(parameters=[AccountsDateRangeQueryParamSerializer,
        UnitQueryParamSerializer])
    def get(self, request, *args, **kwargs):
        return super(EngagedBenchmarkAPIView, self).get(
            request, *args, **kwargs)


class EngagedBenchmarkIndexAPIView(EngagedBenchmarkAPIView):
    """
    Benchmarks against engaged profiles

    Returns a list of questions decorated with a 'benchmarks' field
    that contains aggregated statistics accross the set of profiles
    engaged by a `profile`.

    The set of profiles whose responses are taken into account in
    the aggregate can be reduced to a subset of profiles engaged
    in the time period [accounts_start_at, accounts_ends_at[.

    Aggregation can be done for samples created in the time period
    [start_at,ends_at[, either as a whole period, or as period
    trenches (`yearly`, `monthly`).

    When `period_type` is specified, `nb_periods` and `ends_at` can
    be used instead of `start_at` to filter the samples.

    **Tags**: benchmarks

    **Examples**:

    .. code-block:: http

        GET /api/energy-utility/benchmarks/engaged HTTP/1.1

    responds

    .. code-block:: json

        {
            "title": "Engaged",
            "unit": "profiles",
            "scale": 1,
            "labels": null,
            "count": 1,
            "results": [{
         "path": "/sustainability/esg-strategy-heading/formalized-esg-strategy",
              "title": "1.1 Does your company have a formalized ESG strategy?",
              "default_unit": {
                "slug": "yes-no",
                "title": "Yes/No",
                "system": "enum",
                "choices": []
              },
              "benchmarks": [{
                "slug": "engaged",
                "title": "Engaged",
                "values": [
                  ["2018-01-01T00:00:00Z", {"Yes": 1}]
                ]
              }]
           }]
        }
    """

    @extend_schema(operation_id='engaged_benchmark_index',
        parameters=[AccountsDateRangeQueryParamSerializer,
            UnitQueryParamSerializer])
    def get(self, request, *args, **kwargs):
        return super(EngagedBenchmarkIndexAPIView, self).get(
            request, *args, **kwargs)


class EditableFilterAccountsMixin(AccountsDateRangeMixin,
                                  CampaignMixin, EditableFilterMixin):
    """
    Query accounts for a custom filter
    """

    def get_accounts(self):
        """
        Returns account accessibles by a profile in a specific date range.
        """
        accounts_start_at = self.accounts_start_at
        accounts_ends_at = self.accounts_ends_at

        select_by_answers = EditableFilterEnumeratedAccounts.objects.filter(
            editable_filter=self.editable_filter).exclude(
                question__isnull=True)
        if select_by_answers.exists():
            # Select accounts based on answers to a question.
            kwargs = {}
            if accounts_start_at:
                kwargs.update({'samples__created_at__gte': accounts_start_at})
            if accounts_ends_at:
                kwargs.update({'samples__created_at__lt': accounts_ends_at})
            # XXX supports only one predicate
            select_by = select_by_answers.first()
            return get_account_model().objects.filter(
                samples__is_frozen=True,
                samples__answers__question=select_by.question,
                samples__answers__unit=select_by.question.default_unit,
                samples__answers__measured=select_by.measured,
                *kwargs)

        # we are dealing with a nomminative group of accounts
        return get_account_model().objects.filter(
            filters__editable_filter=self.editable_filter)


class EditableFilterBenchmarkAPIView(EditableFilterAccountsMixin,
                                     BenchmarkAPIView):
    """
    Benchmarks against selected profiles for a subset of questions

    Returns a list of questions whose path is prefixed by `{path}`,
    decorated with a 'benchmarks' field that contains aggregated statistics
    accross the set of profiles selected by the `{editable_filter}` filter.

    The set of profiles whose responses are taken into account in
    the aggregate can be reduced to a subset of profiles created
    in the time period [accounts_start_at, accounts_ends_at[.

    Aggregation can be done for samples created in the time period
    [start_at,ends_at[, either as a whole period, or as period
    trenches (`yearly`, `monthly`).

    When `period_type` is specified, `nb_periods` and `ends_at` can
    be used instead of `start_at` to filter the samples.

    **Tags**: benchmarks

    **Examples**:

    .. code-block:: http

        GET /api/energy-utility/benchmarks/tier1-suppliers/sustainability\
esg-strategy-heading/formalized-esg-strategy HTTP/1.1

    responds

    .. code-block:: json

        {
            "title": "Tier1 suppliers",
            "unit": "profiles",
            "scale": 1,
            "labels": null,
            "count": 1,
            "results": [{
         "path": "/sustainability/esg-strategy-heading/formalized-esg-strategy",
              "title": "1.1 Does your company have a formalized ESG strategy?",
              "default_unit": {
                "slug": "yes-no",
                "title": "Yes/No",
                "system": "enum",
                "choices": []
              },
              "benchmarks": [{
                "slug": "tier1-suppliers",
                "title": "Tier1 suppliers",
                "values": [
                  ["2018-01-01T00:00:00Z", {"Yes": 1}]
                ]
              }]
           }]
        }
    """
    def get_title(self):
        return self.editable_filter.title

    @extend_schema(parameters=[AccountsDateRangeQueryParamSerializer,
        UnitQueryParamSerializer])
    def get(self, request, *args, **kwargs):
        return super(EditableFilterBenchmarkAPIView, self).get(
            request, *args, **kwargs)


class EditableFilterBenchmarkIndexAPIView(EditableFilterBenchmarkAPIView):
    """
    Benchmarks against selected profiles

    Returns a list of questions decorated with a 'benchmarks' field
    that contains aggregated statistics accross the set of profiles
    selected by the `{editable_filter}` filter.

    The set of profiles whose responses are taken into account in
    the aggregate can be reduced to a subset of profiles created
    in the time period [accounts_start_at, accounts_ends_at[.

    Aggregation can be done for samples created in the time period
    [start_at,ends_at[, either as a whole period, or as period
    trenches (`yearly`, `monthly`).

    When `period_type` is specified, `nb_periods` and `ends_at` can
    be used instead of `start_at` to filter the samples.

    **Tags**: benchmarks

    **Examples**:

    .. code-block:: http

        GET /api/energy-utility/benchmarks/tier1-suppliers HTTP/1.1

    responds

    .. code-block:: json

        {
            "title": "Tier1 suppliers",
            "unit": "profiles",
            "scale": 1,
            "labels": null,
            "count": 1,
            "results": [{
         "path": "/sustainability/esg-strategy-heading/formalized-esg-strategy",
              "title": "1.1 Does your company have a formalized ESG strategy?",
              "default_unit": {
                "slug": "yes-no",
                "title": "Yes/No",
                "system": "enum",
                "choices": []
              },
              "benchmarks": [{
                "slug": "tier1-suppliers",
                "title": "Tier1 suppliers",
                "values": [
                  ["2018-01-01T00:00:00Z", {"Yes": 1}]
                ]
              }]
           }]
        }
    """

    @extend_schema(operation_id='editable_filter_benchmark_index',
        parameters=[AccountsDateRangeQueryParamSerializer,
            UnitQueryParamSerializer])
    def get(self, request, *args, **kwargs):
        return super(EditableFilterBenchmarkIndexAPIView, self).get(
            request, *args, **kwargs)



class SampleBenchmarkMixin(SampleMixin, BenchmarkMixin):

    filter_backends = tuple([])
    title = "All"

    @property
    def campaign(self):
        #pylint:disable=attribute-defined-outside-init
        if not hasattr(self, '_campaign'):
            self._campaign = self.sample.campaign
        return self._campaign

    @property
    def ends_at(self):
        #pylint:disable=attribute-defined-outside-init
        if not hasattr(self, '_ends_at'):
            self._ends_at = (self.sample.created_at if self.sample.is_frozen
                else datetime_or_now())
        return self._ends_at

    @property
    def period_type(self):
        #pylint:disable=attribute-defined-outside-init
        if not hasattr(self, '_period_type'):
            self._period_type = None # does not take period_type into account
                                     # when sampling all from a benchmark.
        return self._period_type


class SampleBenchmarksAPIView(SampleBenchmarkMixin, QuestionListAPIView):
    """
    Benchmarks against all peers for a subset of questions

    Returns a list of questions whose path is prefixed by `{path}`,
    decorated with a 'benchmarks' field that contains aggregated statistics
    accross the set of all profiles on the platform at the time the `{sample}`
    was created.

    Aggregation can be done for samples created in the time period
    [start_at,ends_at[, either as a whole period, or as period
    trenches (`yearly`, `monthly`).

    When `period_type` is specified, `nb_periods` and `ends_at` can
    be used instead of `start_at` to filter the samples.

    **Tags**: benchmarks

    **Examples**:

    .. code-block:: http

        GET /api/supplier-1/sample/46f66f70f5ad41b29c4df08f683a9a7a/benchmarks\
/sustainability/esg-strategy-heading/formalized-esg-strategy HTTP/1.1

    responds

    .. code-block:: json

        {
            "title": "All",
            "unit": "profiles",
            "scale": 1,
            "labels": null,
            "count": 1,
            "results": [{
         "path": "/sustainability/esg-strategy-heading/formalized-esg-strategy",
              "title": "1.1 Does your company have a formalized ESG strategy?",
              "default_unit": {
                "slug": "yes-no",
                "title": "Yes/No",
                "system": "enum",
                "choices": []
              },
              "benchmarks": [{
                "slug": "all",
                "title": "All",
                "values": [
                  ["2018-01-01T00:00:00Z", ["Yes", 1] ]
                ]
              }]
           }]
        }
    """
    serializer_class = SampleBenchmarksSerializer
    pagination_class = MetricsPagination


class SampleBenchmarksIndexAPIView(SampleBenchmarksAPIView):
    """
    Benchmarks against all peers

    Returns a list of questions decorated with a 'benchmarks' field
    that contains aggregated statistics accross the set of all profiles
    on the platform at the time the `{sample}` was created.

    Aggregation can be done for samples created in the time period
    [start_at,ends_at[, either as a whole period, or as period
    trenches (`yearly`, `monthly`).

    When `period_type` is specified, `nb_periods` and `ends_at` can
    be used instead of `start_at` to filter the samples.

    **Tags**: benchmarks

    **Examples**:

    .. code-block:: http

        GET /api/supplier-1/sample/46f66f70f5ad41b29c4df08f683a9a7a/benchmarks\
 HTTP/1.1

    responds

    .. code-block:: json

        {
            "title": "All",
            "unit": "profiles",
            "scale": 1,
            "labels": null,
            "count": 1,
            "results": [{
         "path": "/sustainability/esg-strategy-heading/formalized-esg-strategy",
              "title": "1.1 Does your company have a formalized ESG strategy?",
              "default_unit": {
                "slug": "yes-no",
                "title": "Yes/No",
                "system": "enum",
                "choices": []
              },
              "benchmarks": [{
                "slug": "all",
                "title": "All",
                "values": [
                  ["2018-01-01T00:00:00Z", ["Yes", 1] ]
                ]
              }]
           }]
        }
    """


class CompareAPIView(DateRangeContextMixin, CampaignMixin, AccountMixin,
                     QuestionListAPIView):
    """
    Lists compared samples

    **Examples**:

    .. code-block:: http

        GET /api/energy-utility/reporting/sustainability/matrix/compare\
/sustainability HTTP/1.1

    responds

    .. code-block:: json


        {
          "count": 4,
          "results": []
        }
    """
    serializer_class = CompareQuestionSerializer

    @property
    def samples(self):
        """
        Samples to compare

        One per column
        """
        #pylint:disable=attribute-defined-outside-init
        if not hasattr(self, '_samples'):
            accessible_accounts = get_accessible_accounts(
                [self.account], campaign=self.campaign)
            if accessible_accounts:
                # Calling `get_completed_assessments_at_by` with an `accounts`
                # arguments evaluating to `False` will return all the latest
                # frozen samples.
                self._samples = Sample.objects.get_completed_assessments_at_by(
                    self.campaign,
                    start_at=self.start_at, ends_at=self.ends_at,
                    accounts=accessible_accounts)
            else:
                self._samples = Sample.objects.none()
        return self._samples

    @property
    def labels(self):
        """
        Labels for columns
        """
        #pylint:disable=attribute-defined-outside-init
        if not hasattr(self, '_labels'):
            self._labels = sorted([
                sample.account.printable_name for sample in self.samples])
        return self._labels

    @staticmethod
    def next_answer(answers_iterator, questions_by_key, extra_fields):
        answer = next(answers_iterator)
        question_pk = answer.question_id
        value = questions_by_key.get(question_pk)
        if not value:
            question = answer.question
            default_unit = question.default_unit
            value = {
                'path': question.path,
                'title': question.title,
                'rank': answer.rank,
                'required': answer.required,
                'default_unit': default_unit,
                'ui_hint': question.ui_hint,
            }
            for field_name in extra_fields:
                value.update({field_name: getattr(question, field_name)})
            questions_by_key.update({question_pk: value})
        else:
            default_unit = value.get('default_unit')

        if( answer.unit == default_unit or
            UnitEquivalences.objects.filter(
                source=default_unit, target=answer.unit).exists() or
            UnitEquivalences.objects.filter(
                source=answer.unit, target=default_unit).exists() ):
            # we have the answer we are looking for.
            nb_respondents = value.get('nb_respondents', 0) + 1
            value.update({'nb_respondents': nb_respondents})
        return answer

    def as_answer(self, key):
        return key

    @staticmethod
    def equiv_default_unit(values):
        results = []
        for val in values:
            found = False
            for resp in val:
                try:
                    if resp.is_equiv_default_unit:
                        found = {
                            'measured': resp.measured_text,
                            'unit': resp.unit,
                            'created_at': resp.created_at,
                            'collected_by': resp.collected_by,
                        }
                        break
                except AttributeError:
                    pass
            results += [[found]]
        return results

    def attach_results(self, questions_by_key, answers,
                       extra_fields=None):
        if extra_fields is None:
            extra_fields = []

        question = None
        values = []
        key = None
        answer = None
        keys_iterator = iter(self.labels)
        answers_iterator = iter(answers)
        try:
            answer = self.next_answer(answers_iterator,
                questions_by_key, extra_fields=extra_fields)
            question = answer.question
        except StopIteration:
            pass
        try:
            key = self.as_answer(next(keys_iterator))
        except StopIteration:
            pass
        # `answers` will be populated even when there is no `Answer` model
        # just so we can get the list of questions.
        # On the other hand self.labels will be an empty list if there are
        # no samples to compare.
        try:
            while answer:
                if answer.question != question:
                    try:
                        while key:
                            values += [[{}]]
                            key = self.as_answer(next(keys_iterator))
                    except StopIteration:
                        keys_iterator = iter(self.labels)
                        try:
                            key = self.as_answer(next(keys_iterator))
                        except StopIteration:
                            key = None
                    questions_by_key[question.pk].update({
                        'values': self.equiv_default_unit(values)})
                    values = []
                    question = answer.question

                if key and answer.sample.account.printable_name > key:
                    while answer.sample.account.printable_name > key:
                        values += [[{}]]
                        key = self.as_answer(next(keys_iterator))
                elif key and answer.sample.account.printable_name < key:
                    try:
                        try:
                            sample = values[-1][0].sample
                        except AttributeError:
                            sample = values[-1][0].get('sample')
                        if answer.sample != sample:
                            values += [[answer]]
                        else:
                            values[-1] += [answer]
                    except IndexError:
                        values += [[answer]]
                    try:
                        answer = self.next_answer(answers_iterator,
                            questions_by_key, extra_fields=extra_fields)
                    except StopIteration:
                        answer = None
                else:
                    try:
                        try:
                            sample = values[-1][0].sample
                        except AttributeError:
                            sample = values[-1][0].get('sample')
                        if answer.sample != sample:
                            values += [[answer]]
                        else:
                            values[-1] += [answer]
                    except IndexError:
                        values += [[answer]]
                    try:
                        answer = self.next_answer(answers_iterator,
                            questions_by_key, extra_fields=extra_fields)
                    except StopIteration:
                        answer = None
                    try:
                        key = self.as_answer(next(keys_iterator))
                    except StopIteration:
                        key = None
            while key:
                values += [[{}]]
                key = self.as_answer(next(keys_iterator))
        except StopIteration:
            pass
        if question:
            questions_by_key[question.pk].update({
                'values': self.equiv_default_unit(values)})


    def get_questions_by_key(self, prefix=None, initial=None):
        """
        Returns a list of questions based on the answers available
        in the compared samples.
        """
        questions_by_key = super(CompareAPIView, self).get_questions_by_key(
            prefix=prefix, initial=initial)

        if self.samples:
            self.attach_results(
                questions_by_key,
                Answer.objects.get_frozen_answers(
                    self.campaign, self.samples, prefix=prefix))

        return questions_by_key


    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        # Ready to serialize
        serializer = self.get_serializer_class()(
            queryset, many=True, context=self.get_serializer_context())

        return self.get_paginated_response(serializer.data)


    def get_paginated_response(self, data):
        return http.Response(OrderedDict([
            ('count', len(data)),
            ('results', data),
            ('units', {}),
            ('labels', self.labels),
        ]))


class CompareIndexAPIView(CompareAPIView):
    """
    Lists compared samples

    **Examples**:

    .. code-block:: http

        GET /api/energy-utility/reporting/sustainability/matrix/compare HTTP/1.1

    responds

    .. code-block:: json


        {
          "count": 4,
          "results": []
        }
    """


class MatrixCreateAPIView(generics.ListCreateAPIView):
    """
    Lists matrices

    **Examples**:

    .. code-block:: http

        GET /api/energy-utility/reporting/sustainability/matrix HTTP/1.1

    responds

    .. code-block:: json

        {
          "count": 1,
          "results": [
            {
              "slug": "all",
              "title": "All accounts against all questions",
              "metric": {
                "slug": "all-questions",
                "title": "All questions",
                "predicates": []
              },
              "cohorts": [{
                 "slug": "all-accounts",
                 "title": "All accounts",
                 "predicates": []
              }]
            }
          ]
        }
    """
    serializer_class = MatrixSerializer

    def get_queryset(self):
        return Matrix.objects.all()

    def post(self, request, *args, **kwargs):
        """
        Creates a new matrix

        **Examples**:

        .. code-block:: http

            POST /api/energy-utility/reporting/sustainability/matrix HTTP/1.1

        .. code-block:: json

            {
              "slug": "all",
              "title": "All accounts against all questions",
              "metric": {
                "slug": "all-questions",
                "title": "All questions",
                "predicates": []
              },
              "cohorts": [{
                "slug": "all-accounts",
                "title": "All accounts",
                "predicates": []
              }]
            }

        responds

        .. code-block:: json

            {
              "slug": "all",
              "title": "All accounts against all questions",
              "metric": {
                "slug": "all-questions",
                "title": "All questions",
                "predicates": []
              },
              "cohorts": [{
                "slug": "all-accounts",
                "title": "All accounts",
                "predicates": []
              }]
            }
        """
        #pylint:disable=useless-super-delegation
        return super(MatrixCreateAPIView, self).post(request, *args, **kwargs)


class MatrixDetailAPIView(MatrixMixin, generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieves a matrix of scores for cohorts aganist a metric.

    **Tags**: reporting

    **Examples**

    .. code-block:: http

        GET /api/energy-utility/reporting/sustainability/matrix/languages HTTP/1.1

   responds

    .. code-block:: json

        {
           "slug": "languages",
           "title": "All cohorts for all questions",
           "values": {
               "portfolio-a": 0.1,
               "portfolio-b": 0.5
           }
        }
    """

    serializer_class = MatrixSerializer
    lookup_field = 'slug'
    lookup_url_kwarg = 'path'
    question_model = get_question_serializer().Meta.model

    def put(self, request, *args, **kwargs):
        """
        Updates a matrix of scores for cohorts against a metric

        **Tags**: reporting

        **Examples**

        .. code-block:: http

            PUT /api/energy-utility/reporting/sustainability/matrix/languages HTTP/1.1

        .. code-block:: json

            {
              "title": "Average scores by supplier industry sub-sector",
              "cohorts": []
            }

        responds

        .. code-block:: json

            {
              "slug": "languages",
              "title": "All cohorts for all questions",
              "cohorts": []
            }
        """
        #pylint:disable=useless-super-delegation
        return super(MatrixDetailAPIView, self).put(
            request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        """
        Deletes a matrix of scores for cohorts against a metric

        **Tags**: reporting

        **Examples**

        .. code-block:: http

            DELETE /api/energy-utility/reporting/sustainability/matrix/languages HTTP/1.1
        """
        #pylint:disable=useless-super-delegation
        return super(MatrixDetailAPIView, self).put(
            request, *args, **kwargs)

    def aggregate_scores(self, metric, cohorts, cut=None, accounts=None):
        #pylint:disable=unused-argument,too-many-locals
        if accounts is None:
            accounts = get_account_model().objects.all()
        scores = {}
        if metric:
            assert 'metric' in metric.tags, \
                "filter '%s' is not tagged as a metric" % str(metric)
            includes, excludes = metric.as_kwargs()
            questions = self.question_model.objects.filter(
                **includes).exclude(**excludes)
            nb_questions = len(questions)
            if nb_questions > 0:
                for cohort in cohorts:
                    if isinstance(cohort, EditableFilter):
                        includes, excludes = cohort.as_kwargs()
                        qs_accounts = accounts.filter(
                            **includes).exclude(**excludes)
                    else:
                        # If `matrix.cohorts is None`, the `cohorts` argument
                        # will be a list of single account objects.
                        qs_accounts = [cohort]
                    nb_accounts = len(qs_accounts)
                    if nb_accounts > 0:
                        nb_correct_answers = Answer.objects.filter(
                            question__in=questions,
                            sample__account__in=qs_accounts).filter(
                                measured=models.F('question__correct_answer')).count()
                        score = nb_correct_answers * 100 / (
                            nb_questions * nb_accounts)
                        LOGGER.debug("score for '%s' = (%d * 100) "\
                            "/ (%d * %d) = %f", str(cohort), nb_correct_answers,
                            nb_questions, nb_accounts, score)
                        assert score <= 100
                        scores.update({str(cohort): score})
        return {"scores": scores}

    @property
    def matrix(self):
        #pylint:disable=attribute-defined-outside-init
        if not hasattr(self, '_matrix'):
            self._matrix = Matrix.objects.filter(
                slug=self.kwargs.get(self.matrix_url_kwarg)).first()
        return self._matrix

    def get_accounts(self):
        #pylint:disable=unused-argument
        return get_account_model().objects.all()

    def get_likely_metric(self, cohort_slug):
        """
        Returns a URL to a ``Matrix`` derived from *cohort*.

        Many times people will use the same name to either mean a cohort
        or a metric and expect the system will magically switch between
        both meaning. This is an attempt at magic.
        """
        likely_metric = None
        look = re.match(r"(\S+)(-\d+)", cohort_slug)
        if look:
            try:
                likely_metric = self.request.build_absolute_uri(
                    reverse('matrix_chart', args=(
                        EditableFilter.objects.get(slug=look.group(1)).slug,)))
            except EditableFilter.DoesNotExist:
                pass
        return likely_metric


    def get(self, request, *args, **kwargs):
        #pylint:disable=unused-argument,too-many-locals
        matrix = self.matrix
        if matrix:
            metric = self.matrix.metric
        else:
            parts = self.kwargs.get(self.matrix_url_kwarg).split('/')
            metric = generics.get_object_or_404(EditableFilter.objects.all(),
                slug=parts[-1])
            matrix = Matrix.objects.filter(slug=parts[0]).first()
        if not matrix:
            raise Http404()

        cohort_serializer = EditableFilterSerializer
        cohorts = matrix.cohorts.exclude(tags__contains='aggregate')
        public_cohorts = matrix.cohorts.filter(tags__contains='aggregate')
        cut = matrix.cut
        if not cohorts:
            # We don't have any cohorts, let's show individual accounts instead.
            if cut:
                includes, excludes = cut.as_kwargs()
                accounts = self.get_accounts().filter(
                    **includes).exclude(**excludes)
            else:
                accounts = self.get_accounts()
            cohort_serializer = get_account_serializer()
            # Implementation Note: switch cohorts from an queryset
            # of `EditableFilter` to a queryset of `Account` ...
            cohorts = accounts

        result = []
        scores = {}
        val = {
            'slug': metric.slug,
            'title': metric.title,
            'metric': EditableFilterSerializer().to_representation(metric),
            'cut': (EditableFilterSerializer().to_representation(cut)
                if cut else None),
            'cohorts': cohort_serializer(many=True).to_representation(cohorts)}

        # In some case, a metric and cohort have a connection
        # and could have the same name.
        for cohort in val['cohorts']:
            likely_metric = self.get_likely_metric(cohort['slug'])
            if likely_metric:
                cohort['likely_metric'] = likely_metric

        scores.update(val)
        scores.update({"values": self.aggregate_scores(
            metric, cohorts, cut, accounts=self.get_accounts())})
        result += [scores]
        if public_cohorts:
            public_scores = {}
            public_scores.update(val)
            public_scores.update(
                {"cohorts": EditableFilterSerializer(
                    public_cohorts, many=True).data,
                 "values": self.aggregate_scores(metric, public_cohorts)})
            result += [public_scores]
        return http.Response(result)


class EditableFilterQuerysetMixin(AccountMixin):

    def get_queryset(self):
        return EditableFilter.objects.filter(
            models.Q(account__isnull=True) |
            models.Q(account=self.account)).order_by('slug')


class EditableFilterListAPIView(EditableFilterQuerysetMixin,
                                generics.ListAPIView):
    """
    Lists fitlers

    **Tags**: reporting

    **Examples**

    .. code-block:: http

         GET /api/energy-utility/filters HTTP/1.1

    responds

    .. code-block:: json

      {
          "count": 2,
          "next": null,
          "previous": null,
          "results": [{
              "slug": "boxes-and-enclosures",
              "title": "Boxes & enclosures",
              "extra": ""
          }]
      }
    """
    serializer_class = EditableFilterSerializer
    ordering_fields = ('slug',)
    search_fields = (
        'tags',
    )
    filter_backends = (SearchFilter, OrderingFilter)


class AccountsFilterDetailAPIView(EditableFilterMixin,
                                  DestroyModelMixin,
                                  UpdateModelMixin,
                                  generics.ListCreateAPIView):
    """
    Lists profiles in a group

    Returns a list of {{PAGE_SIZE}} nomminative profiles and
    select-profiles-by-answer filters that form the group.

    `{profile}` must be the owner of the `{editable_filter}`.

    **Tags**: cohorts

    **Examples**

    .. code-block:: http

         GET /api/energy-utility/filters/accounts/suppliers HTTP/1.1

    responds

    .. code-block:: json

         {
           "count": 1,
           "results": [{
                "facility": "Main factory",
                "fuel_type": "natural-gas",
                "allocation": "Energy utility",
                "created_at": null,
                "ends_at": null,
                "amount": 100,
                "unit": "mmbtu"
            }]
        }
    """
    model = EditableFilterEnumeratedAccounts
    serializer_class = CohortSerializer

    def get_queryset(self):
        return self.model.objects.filter(
            editable_filter=self.editable_filter).order_by('rank')

    def get_serializer_class(self):
        if self.request.method.lower() == 'post':
            return CohortAddSerializer
        if self.request.method.lower() == 'put':
            return EditableFilterUpdateSerializer
        return super(AccountsFilterDetailAPIView, self).get_serializer_class()

    @extend_schema(request=EditableFilterUpdateSerializer)
    def put(self, request, *args, **kwargs):
        """
        Renames a group of profiles

        Updates the name of a group of profiles.

        `{profile}` must be the owner of the `{editable_filter}`.

        **Tags**: cohorts

        **Examples**

        .. code-block:: http

             PUT /api/energy-utility/filters/accounts/suppliers HTTP/1.1

        .. code-block:: json

            {
                "title": "Energy utility suppliers"
            }

        responds

        .. code-block:: json

         {
           "slug": "suppliers",
           "title": "Energy utility suppliers",
           "extra": null
         }
        """
        return self.update(request, *args, **kwargs)


    def delete(self, request, *args, **kwargs):
        """
        Deletes a group of profiles

        `{profile}` must be the owner of the `{editable_filter}`.

        **Tags**: cohorts

        **Examples**

        .. code-block:: http

             DELETE /api/energy-utility/filters/accounts/suppliers HTTP/1.1
        """
        return self.destroy(request, *args, **kwargs)

    @extend_schema(operation_id='filters_accounts_list_item')
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)

    @extend_schema(operation_id='filters_accounts_add_item')
    def post(self, request, *args, **kwargs):
        """
        Adds a profile to a group

        Either `full_name` (optionally `slug`) or a pair
        (`question`, `measured`) must be specified.

        When a `full_name`/`slug` is specified, the associated nomminative
        profile will be added to the group.

        When a (`question`, `measured`) pair is specified,
        a select-profiles-by-answer filter will be used
        to add all profiles that answered `measured` to a `question`
        to the group.

        `{profile}` must be the owner of the `{editable_filter}`.

        **Tags**: cohorts

        **Examples**

        .. code-block:: http

             POST /api/energy-utility/filters/accounts/suppliers HTTP/1.1

        .. code-block:: json

            {
                "full_name": "Main"
            }

        responds

        .. code-block:: json

            {
                "slug": "main",
                "full_name": "Main"
            }
        """
        #pylint:disable=useless-super-delegation
        return self.create(request, *args, **kwargs)

    def create(self, request, *args, **kwargs): # XXX unnecessary?
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = self.perform_create(serializer)
        data = self.serializer_class(
            context=self.get_serializer_context()).to_representation(instance)
        headers = self.get_success_headers(data)
        return http.Response(data, status=status.HTTP_201_CREATED,
            headers=headers)


    def perform_create(self, serializer):
        full_name = serializer.validated_data.get('full_name')
        account_slug = serializer.validated_data.get('slug')
        if full_name or account_slug:
            return self.get_or_create_nominative_predicate(
                serializer.validated_data)
        return self.create_by_answers_predicate(
            serializer.validated_data)


    def get_or_create_nominative_predicate(self, validated_data):
        # Create the `Account` (if necessary) and add it to the filter.
        full_name = validated_data.get('full_name')
        account_slug = validated_data.get('slug')
        with transaction.atomic():
            extra = validated_data.get('extra')
            if account_slug:
                # We can only add nomminative accounts that we track.
                account_queryset = get_account_model().objects.filter(
                    portfolios__grantee=self.account)
                account_lookup_field = settings.ACCOUNT_LOOKUP_FIELD
                filter_args = {account_lookup_field: account_slug}
                account = generics.get_object_or_404(account_queryset,
                    **filter_args)
            else:
                try:
                    # We rely on the account model to create a unique slug
                    # on `save()`.
                    account = get_account_model().objects.create(
                        # XXX Candidate slug with account prefix...
                        full_name=full_name, extra=extra)
                except IntegrityError as err:
                    handle_uniq_error(err)
            last_rank = EditableFilterEnumeratedAccounts.objects.filter(
                editable_filter=self.editable_filter).aggregate(
                models.Max('rank')).get('rank__max')
            if not last_rank:
                last_rank = 0
            enum_account = EditableFilterEnumeratedAccounts.objects.create(
                account=account,
                editable_filter=self.editable_filter,
                rank=last_rank + 1)
            account.rank = enum_account.rank
        return enum_account


    def create_by_answers_predicate(self, validated_data):
        question = generics.get_object_or_404(
            get_question_model().objects.all(), path=validated_data.get('path'))
        measured = validated_data.get('measured')
        with transaction.atomic():
            last_rank = EditableFilterEnumeratedAccounts.objects.filter(
                editable_filter=self.editable_filter).aggregate(
                models.Max('rank')).get('rank__max')
            if not last_rank:
                last_rank = 0

            unit = question.default_unit
            if unit.system == Unit.SYSTEM_ENUMERATED:
                try:
                    measured = Choice.objects.get(question__isnull=True,
                        unit=unit, text=measured).pk
                except Choice.DoesNotExist:
                    choices = Choice.objects.filter(question__isnull=True,
                        unit=unit)
                    raise ValidationError("'%s' is not a valid choice."\
                        " Expected one of %s." % (measured,
                        [choice.get('text', "")
                         for choice in six.itervalues(choices)]))

            enum_account = EditableFilterEnumeratedAccounts.objects.create(
                question=question,
                measured=measured,
                editable_filter=self.editable_filter,
                rank=last_rank + 1)
        return enum_account


    def destroy(self, request, *args, **kwargs):
        instance = self.editable_filter
        self.perform_destroy(instance)
        return http.Response(status=status.HTTP_204_NO_CONTENT)


class AccountsFilterEnumeratedAPIView(EditableFilterMixin,
                                      generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieves a selector in a group

    Returns the nominative profile or select-profiles-by-answer filter
    at index `{rank}` in the group `{editable_filter}`.

    `{profile}` must be the owner of the `{editable_filter}`.

    **Tags**: cohorts

    **Examples**

    .. code-block:: http

         GET /api/energy-utility/filters/accounts/suppliers/1 HTTP/1.1

    responds

    .. code-block:: json

         {
           "slug": "main-factory",
           "full_name": "Main factory"
         }
    """
    lookup_field = 'rank'
    serializer_class = CohortSerializer

    @extend_schema(operation_id='filters_accounts_retrieve_item')
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)


    def get_queryset(self):
        queryset = EditableFilterEnumeratedAccounts.objects.filter(
            editable_filter__account=self.account,
            editable_filter__slug=self.kwargs.get(
                self.editable_filter_url_kwarg))
        return queryset

    def perform_update(self, serializer):
        if 'account' in serializer.validated_data:
            full_name = serializer.validated_data.get(
                'account').get('full_name')
            # XXX We shouldn't be able to update a supplier name
            #     unless we have a role for that supplier.
            serializer.instance.account.full_name = full_name
            serializer.instance.account.save()


    @extend_schema(operation_id='filters_accounts_update_item')
    def put(self, request, *args, **kwargs):
        """
        Updates a selector in a group

        Updates the selector at `{rank}` in the group `{editable_filter}`,
        and returns the updated nominative profile or select-profiles-by-answer
        filter.

        `{profile}` must be the owner of the `{editable_filter}`.

        **Tags**: cohorts

        **Examples**

        .. code-block:: http

             PUT /api/energy-utility/filters/accounts/suppliers/1 HTTP/1.1

        .. code-block:: json

            {
                "full_name": "Main factory"
            }

        responds

        .. code-block:: json

            {
                "slug": "main-factory",
                "full_name": "Main factory"
            }
        """
        return self.update(request, *args, **kwargs)


    @extend_schema(operation_id='filters_accounts_partial_update_item')
    def patch(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)


    @extend_schema(operation_id='filters_accounts_remove_item')
    def delete(self, request, *args, **kwargs):
        """
        Removes a selector from a group

        Upon successful completion, the nomminative profile, or
        select-profiles-by-answer filter, at index `{rank}` will
        no longer be present in the group `{editable_filter}`.

        `{profile}` must be the owner of the `{editable_filter}`.

        **Tags**: cohorts

        **Examples**

        .. code-block:: http

             DELETE /api/energy-utility/filters/accounts/suppliers/1 HTTP/1.1
        """
        return self.destroy(request, *args, **kwargs)


class EditableFilterObjectsAPIView(AccountMixin, generics.ListCreateAPIView):
    """
    Base class to filter accounts and questions
    """
    serializer_class = None # override in subclasses
    lookup_field = 'slug'
    lookup_url_kwarg = 'editable_filter'
    filter_backends = (SearchFilter, OrderingFilter)

    search_fields = (
        'slug',
        'title'
    )

    ordering = ('title',)

    def get_queryset(self):
        return self.get_serializer_class().Meta.model.objects.all()


    def post(self, request, *args, **kwargs):
        """
        Creates a fitler

        **Tags**: reporting

        **Examples**

        .. code-block:: http

             POST /api/energy-utility/filters HTTP/1.1

        .. code-block:: json

            {
                "slug": "construction",
                "title": "Construction",
                "tags": "cohort",
                "likely_metric": null
            }

        responds

        .. code-block:: json

            {
                "slug": "construction",
                "title": "Construction",
                "tags": "cohort",
                "likely_metric": null
            }
        """
        return self.create(request, *args, **kwargs)

    def perform_create(self, serializer):
        try:
            serializer.save(account=self.account)
        except IntegrityError as err:
            handle_uniq_error(err)


class AccountsFilterListAPIView(EditableFilterObjectsAPIView):
    """
    Lists defined group of profiles

    Returns a list of {{PAGE_SIZE}} groups that belong to `{profile}`.

    The queryset can be further refined to match a search filter (``q``)
    and sorted on specific fields (``o``).

    **Tags**: cohorts

    **Examples**:

    .. code-block:: http

        GET /api/energy-utility/filters/accounts HTTP/1.1

    responds

    .. code-block:: json

        {
            "count": 1,
            "previous": null,
            "next": null,
            "results": [
            {
               "slug": "supplier-1",
               "title": "Supplier 1",
               "extra": null
           }]
        }
    """
    serializer_class = EditableFilterSerializer

    def get_serializer_class(self):
        if self.request.method.lower() == 'post':
            return EditableFilterCreateSerializer
        return super(AccountsFilterListAPIView, self).get_serializer_class()

    def get_queryset(self):
        queryset = super(AccountsFilterListAPIView, self).get_queryset()
        if self.account:
            queryset = queryset.filter(account=self.account)
        return queryset.order_by('title')

    def post(self, request, *args, **kwargs):
        """
        Creates a group of profiles

        After the group is created, nomminative profiles or
        select-profiles-by-answer filters can be added to it
        through :ref:`Adds a profile to a group <#filters_accounts_add_item>`
        endpoint.

        **Tags**: cohorts

        **Examples**

        .. code-block:: http

             POST /api/energy-utility/filters/accounts HTTP/1.1

        .. code-block:: json

            {
              "title": "Supplier 1"
            }

        responds

        .. code-block:: json

            {
               "slug": "supplier-1",
               "title": "Supplier 1"
            }
        """
        return self.create(request, *args, **kwargs)


# XXX Question fitlers currently have a shaky definition and should not be used.

class QuestionsFilterListAPIView(EditableFilterObjectsAPIView):
    """
    Lists questions filters

    **Tags**: reporting

    **Examples**:

    .. code-block:: http

        GET /api/supplier-1/filters/questions HTTP/1.1

    responds

    .. code-block:: json

        {
            "count": 1,
            "previous": null,
            "next": null,
            "results": [{
              "path": "/construction/product-design",
              "title": "Product Design",
              "default_unit": "assessment",
              "ui_hint": "radio"
            }]
        }
    """
    serializer_class = get_question_serializer()
    ordering = ('path',)

    def post(self, request, *args, **kwargs):
        """
        Creates a questions fitler

        **Tags**: reporting

        **Examples**

        .. code-block:: http

             POST /api/energy-utility/filters/questions HTTP/1.1

        .. code-block:: json

            {
                "title": "Construction",
                "default_unit": "assessment",
                "path": "/construction/product-design"
            }

        responds

        .. code-block:: json

            {
                "title": "Construction",
                "default_unit": "assessment",
                "path": "/construction/product-design"
            }
        """
        #pylint:disable=useless-super-delegation
        return super(QuestionsFilterListAPIView, self).post(
            request, *args, **kwargs)


class EditableFilterDetailAPIView(EditableFilterQuerysetMixin,
                                  DestroyModelMixin,
                                  UpdateModelMixin,
                                  generics.ListCreateAPIView):

    serializer_class = None


class QuestionsFilterDetailAPIView(EditableFilterDetailAPIView):
    """
    Retrieves a questions fitler

    **Tags**: reporting

    **Examples**

    .. code-block:: http

         GET /api/energy-utility/filters/questions/governance HTTP/1.1

    responds

    .. code-block:: json

        {
            "slug": "governance",
            "title": "Governance questions"
        }
    """
    serializer_class = EditableFilterSerializer

    def put(self, request, *args, **kwargs):
        """
        Updates a questions fitler

        **Tags**: reporting

        **Examples**

        .. code-block:: http

             PUT /api/energy-utility/filters/questions/governance HTTP/1.1

        .. code-block:: json

            {
                "slug": "governance",
                "title": "Governance questions"
            }

        responds

        .. code-block:: json

            {
                "slug": "governance",
                "title": "Governance questions"
            }
        """
        #pylint:disable=useless-super-delegation
        return self.update(request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        """
        Deletes a questions fitler

        **Tags**: reporting

        **Examples**

        .. code-block:: http

             DELETE /api/energy-utility/filters/questions/governance HTTP/1.1
        """
        #pylint:disable=useless-super-delegation
        return self.destroy(request, *args, **kwargs)
