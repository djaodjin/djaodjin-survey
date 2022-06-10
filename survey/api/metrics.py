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
#pylint:disable=too-many-lines

import decimal, json, logging
from collections import OrderedDict

from django.db import transaction
from django.db.models import F, Sum
from rest_framework import status
from rest_framework.generics import (get_object_or_404, RetrieveAPIView,
    ListAPIView)
from rest_framework.response import Response as HttpResponse
from rest_framework.exceptions import ValidationError

from ..compat import six
from ..filters import DateRangeFilter
from ..helpers import get_extra
from ..mixins import AccountMixin, EditableFilterMixin, QuestionMixin
from ..models import Answer, Sample
from .serializers import (AnswerSerializer, DatapointSerializer,
    EditableFilterValuesCreateSerializer)
from ..utils import get_question_model

LOGGER = logging.getLogger(__name__)


class AggregateMetricsAPIView(AccountMixin, QuestionMixin, RetrieveAPIView):
    """
    Retrieve a aggregated metric over a time period

    **Tags**: assessments

    **Examples**

    .. code-block:: http

         GET /api/xia/metrics/ghg-emissions/ HTTP/1.1

    responds

    .. code-block:: json

        {
            "created_at": "2020-01-01T00:00:00Z",
            "measured": 12,
            "unit": "liters"
        }
    """
    serializer_class = AnswerSerializer
    filter_backends = (DateRangeFilter,)

    @property
    def unit(self):
        if not hasattr(self, '_unit'):
            self._unit = self.question.default_unit
        return self._unit

    def get_queryset(self):
        return Answer.objects.filter(
            question__path=self.db_path,
            unit=self.unit,
            sample__account__filters__editable_filter__account=self.account)

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
    Lists values in an account

    **Tags**: assessments

    **Examples**

    .. code-block:: http

         GET /api/xia/filters/accounts/values HTTP/1.1

    responds

    .. code-block:: json

        {
            "created_at": "2020-01-01T00:00:00Z",
            "measured": 12,
            "unit": "liters"
        }
    """
    serializer_class = DatapointSerializer
    filter_backends = (DateRangeFilter,)

    def get_queryset(self):
        return Answer.objects.filter(
            sample__account__filters__editable_filter__account=self.account
        ).order_by('-created_at').select_related('sample__account').annotate(
            account=F('sample__account'))


class AccountsFilterValuesAPIView(EditableFilterMixin, ListAPIView):
    """
    Lists values in a filter

    **Tags**: assessments

    **Examples**

    .. code-block:: http

         GET /api/xia/filters/accounts/ghg-emissions/values HTTP/1.1

    responds

    .. code-block:: json

        {
            "created_at": "2020-01-01T00:00:00Z",
            "measured": 12,
            "unit": "liters"
        }
    """
    serializer_class = AnswerSerializer
    filter_backends = (DateRangeFilter,)

    def get_serializer_class(self):
        if self.request.method.lower() == 'post':
            return EditableFilterValuesCreateSerializer
        return super(AccountsFilterValuesAPIView, self).get_serializer_class()

    def post(self, request, *args, **kwargs):
        """
        Appends values in a filter

        **Tags**: assessments

        **Examples**

        .. code-block:: http

             POST /api/xia/filters/accounts/ghg-emissions/values HTTP/1.1

        responds

        .. code-block:: json

            {
                "created_at": "2020-01-01T00:00:00Z",
                "measured": 12,
                "unit": "liters"
            }
        """
        return self.create(request, *args, **kwargs)


    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        baseline_at = serializer.validated_data['baseline_at']
        created_at = serializer.validated_data['created_at']

        by_accounts = {}
        path = get_extra(self.editable_filter, 'path', "")
        if not path:
            raise ValidationError()
        question = get_object_or_404(
            get_question_model().objects.all(), path=path)

        for item in serializer.validated_data['items']:
            measured = item.get('measured')
            if not measured:
                continue
            account = item.get('slug')
            if account not in by_accounts:
                by_accounts[account] = {
                    'sample': Sample(account=account, is_frozen=True),
                    'answers': []
                }
            by_accounts[account]['answers'] += [Answer(
                question=question,
                created_at=created_at,
                collected_by=self.request.user,
                unit=item.get('unit'),
                measured=measured
            )]

        with transaction.atomic():
            samples_by_accounts = {}
            for item in six.itervalues(by_accounts):
                sample = item['sample']
                answers = item['answers']
                sample.save()
                for answer in answers:
                    answer.sample_id = sample.pk
                if baseline_at:
                    baseline_answers = []
                    for answer in answers:
                        baseline_answers += [
                            Answer(
                                question=answer.question,
                                created_at=baseline_at,
                                collected_by=answer.collected_by,
                                unit=answer.unit,
                                measured=0)]
                    Answer.objects.bulk_create(baseline_answers)
                Answer.objects.bulk_create(answers)

        return HttpResponse(serializer.data, status=status.HTTP_201_CREATED)
