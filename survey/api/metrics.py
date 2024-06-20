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
#pylint:disable=too-many-lines

import logging

from django.db import transaction
from django.db.models import F, Sum
from rest_framework import status
from rest_framework.generics import (get_object_or_404, RetrieveAPIView,
    ListAPIView)
from rest_framework.response import Response as HttpResponse
from rest_framework.exceptions import ValidationError

from ..compat import gettext_lazy as _, six
from ..docs import extend_schema
from ..filters import AggregateByPeriodFilter, DateRangeFilter
from ..helpers import datetime_or_now, get_extra
from ..mixins import AccountMixin, EditableFilterMixin, QuestionMixin
from ..models import Answer, Sample, Unit
from .serializers import (AnswerSerializer, DatapointSerializer,
    EditableFilterValuesCreateSerializer, UnitQueryParamSerializer)
from ..utils import get_question_model

LOGGER = logging.getLogger(__name__)


class AggregateMetricsAPIView(AccountMixin, QuestionMixin, RetrieveAPIView):
    """
    Retrieves aggregated quantitative measurements over a time period

    Returns the aggregate of quantitative data for question `{path}`.

    **Tags**: reporting

    **Examples**

    .. code-block:: http

         GET /api/supplier-1/metrics/aggregate/ghg-emissions HTTP/1.1

    responds

    .. code-block:: json

        {
            "created_at": "2020-01-01T00:00:00Z",
            "measured": 12,
            "unit": "t"
        }
    """
    serializer_class = AnswerSerializer
    filter_backends = (AggregateByPeriodFilter,)

    @property
    def unit(self):
        #pylint:disable=attribute-defined-outside-init
        if not hasattr(self, '_unit'):
            unit_slug = self.get_query_param('unit')
            if unit_slug:
                self._unit = get_object_or_404(
                    Unit.objects.all(), slug=unit_slug)
            if not self._unit:
                self._unit = self.question.default_unit
        return self._unit

    def get_query_param(self, key):
        try:
            return self.request.query_params.get(key, None)
        except AttributeError:
            pass
        return self.request.GET.get(key, None)

    def get_queryset(self):
        queryset = Answer.objects.filter(
            question__path=self.db_path,
            unit=self.unit,
            sample__account__filters__editable_filter__account=self.account)
        return queryset

    @extend_schema(parameters=[UnitQueryParamSerializer])
    def get(self, request, *args, **kwargs):
        #pylint:disable=useless-super-delegation
        queryset = self.filter_queryset(self.get_queryset())
        agg = queryset.aggregate(Sum('measured')).get('measured__sum')
        if agg is None:
            agg = 0
        serializer_class = self.get_serializer_class()
        return HttpResponse(serializer_class().to_representation({
            'measured': agg, 'unit': self.unit}))


class AccountsValuesAPIView(AccountMixin, ListAPIView):
    """
    Lists quantitative measurements

    Returns a list of {{page_size}} records.
    XXX What was entered in the system?

    **Tags**: assessments

    **Examples**

    .. code-block:: http

         GET /api/supplier-1/filters/accounts/values HTTP/1.1

    responds

    .. code-block:: json

        {
          "count": 0,
          "next": null,
          "previous": null,
          "results": [{
            "created_at": "2020-01-01T00:00:00Z",
            "measured": 12,
            "unit": "t"
          }]
        }
    """
    serializer_class = DatapointSerializer
    filter_backends = (DateRangeFilter,)

    def get_queryset(self):
        queryset = Answer.objects.filter(
            sample__account__filters__editable_filter__account=self.account
        ).order_by('-created_at').select_related('sample__account').annotate(
            account=F('sample__account'))
        return queryset


class AccountsFilterValuesAPIView(EditableFilterMixin, ListAPIView):
    """
    Lists quantitative measurements for a group

    Returns a list of {{page_size}} records.
    XXX What was entered in the system?

    **Tags**: assessments

    **Examples**

    .. code-block:: http

         GET /api/supplier-1/filters/accounts/ghg-emissions/values HTTP/1.1

    responds

    .. code-block:: json

        {
          "count": 0,
          "next": null,
          "previous": null,
          "results": [{
            "created_at": "2020-01-01T00:00:00Z",
            "measured": 12,
            "unit": "t"
          }]
        }
    """
    serializer_class = AnswerSerializer
    filter_backends = (DateRangeFilter,)

    def get_serializer_class(self):
        if self.request.method.lower() == 'post':
            return EditableFilterValuesCreateSerializer
        return super(AccountsFilterValuesAPIView, self).get_serializer_class()

    @property
    def editable_filter_question(self):
        #pylint:disable=attribute-defined-outside-init
        if not hasattr(self, '_editable_filter_question'):
            path = get_extra(self.editable_filter, 'path', "")
            if not path:
                raise ValidationError(
                    _("No question specified is the editablefilter.extra"))
            self._editable_filter_question = get_object_or_404(
                get_question_model().objects.all(), path=path)
        return self._editable_filter_question

    @extend_schema(operation_id='filters_accounts_values_by_subset')
    def get(self, request, *args, **kwargs):
        return super(AccountsFilterValuesAPIView, self).get(
            request, *args, **kwargs)

    def get_queryset(self):
        queryset = Answer.objects.filter(
            question=self.editable_filter_question,
            sample__account__filters__editable_filter=self.editable_filter
        ).order_by('created_at')
        return queryset

    def post(self, request, *args, **kwargs):
        """
        Records quantitative measurements

        Records numeric measurements towards a specific
        metric.

        When `baseline_at` is specified, the measurement refers to
        a relative value since `baseline_at`. When `baseline_at` is not
        specified, the intent is to record an absolute measurement at time
        `created_at`.

        **Tags**: assessments

        **Examples**

        .. code-block:: http

             POST /api/supplier-1/filters/accounts/ghg-emissions/values HTTP/1.1

        .. code-block:: json

            {
              "created_at": "2020-01-01T00:00:00Z",
              "items": [{
                "slug": "main-factory",
                "measured": 12,
                "unit": "t"
              }]
            }

        responds

        .. code-block:: json

            {
              "created_at": "2020-01-01T00:00:00Z",
              "items": [{
                "slug": "main-factory",
                "measured": 12,
                "unit": "t"
              }]
            }
        """
        return self.create(request, *args, **kwargs)


    def create(self, request, *args, **kwargs):
        #pylint:disable=unused-argument,too-many-locals
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        created_at = datetime_or_now(serializer.validated_data['created_at'])
        baseline_at = serializer.validated_data.get('baseline_at')
        if baseline_at:
            baseline_at = datetime_or_now(baseline_at)

        at_time = datetime_or_now()
        measures_by_accounts = {}
        question = self.editable_filter_question
        for item in serializer.validated_data['items']:
            measured = item.get('measured')
            if measured is None:
                continue
            try:
                measured = int(measured)
            except ValueError:
                try:
                    measured = round(float(measured))
                except ValueError:
                    raise ValidationError({"measured": "must be a number"})
            account = item.get('slug') # `account` will be an `Account` model.
            if account not in measures_by_accounts:
                measures_by_accounts[account] = []
            measures_by_accounts[account] += [{
                'measured': measured,
                'unit': item.get('unit') # `unit` will be a `Unit` model.
            }]
        with transaction.atomic():
            for account, measures in six.iteritems(measures_by_accounts):
                create_answers = []
                sample = Sample(
                    account=account,
                    created_at=at_time,
                    updated_at=at_time,
                    is_frozen=True)
                for measure in measures:
                    # If we already have a data point for that account
                    # and metric at the end of the period, we update it.
                    # the start date of the period.
                    measured = measure['measured']
                    try:
                        answer = Answer.objects.get(
                            created_at=created_at,
                            sample__account=account,
                            question=question,
                            unit=measure['unit'])
                        answer.measured = measured
                        answer.save()
                    except Answer.DoesNotExist:
                        if not sample.pk:
                            sample.save()
                        create_answers += [Answer(
                            sample=sample,
                            question=question,
                            created_at=created_at,
                            collected_by=self.request.user,
                            unit=measure['unit'],
                            measured=measured)]
                if baseline_at:
                    create_baseline_answers = []
                    baseline_sample = Sample(
                        account=account,
                        created_at=at_time,
                        updated_at=at_time,
                        is_frozen=True)
                    for measure in measures:
                        # If we already have a data point for that account
                        # and metric at ``baseline_at``, we don't create
                        # a dummy (i.e. measured == 0) data point to store
                        # the start date of the period.
                        if not Answer.objects.filter(
                            created_at=baseline_at,
                            sample__account=account,
                            question=question,
                            unit=measure['unit']).exists():
                            if not baseline_sample.pk:
                                baseline_sample.save()
                            create_baseline_answers += [
                                Answer(
                                    sample=baseline_sample,
                                    question=question,
                                    created_at=baseline_at,
                                    collected_by=self.request.user,
                                    unit=measure['unit'],
                                    measured=0)]
                    Answer.objects.bulk_create(create_baseline_answers)
                Answer.objects.bulk_create(create_answers)

        return HttpResponse(serializer.data, status=status.HTTP_201_CREATED)
