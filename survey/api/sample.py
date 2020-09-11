# Copyright (c) 2020, DjaoDjin inc.
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

import decimal, logging

from django.db import transaction
from django.db.models import Max
from django.db.utils import DataError
from rest_framework import generics, mixins
from rest_framework import response as http
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.status import HTTP_200_OK, HTTP_201_CREATED

from ..compat import six, is_authenticated
from ..mixins import AccountMixin, SampleMixin
from ..models import Answer, Choice, Sample, Unit
from .serializers import (AnswerSerializer, SampleAnswerSerializer,
    SampleSerializer)
from ..utils import datetime_or_now, get_question_model


LOGGER = logging.getLogger(__name__)


def update_or_create_answer(datapoint, question, sample, created_at,
                            collected_by=None):
    answer = None
    created = False
    measured = datapoint.get('measured', None)
    metric = datapoint.get('metric', question.default_metric)
    unit = datapoint.get('unit', metric.unit)
    try:
        with transaction.atomic():
            if unit.system in Unit.NUMERICAL_SYSTEMS:
                try:
                    try:
                        measured = str(int(measured))
                    except ValueError:
                        measured = '{:.0f}'.format(decimal.Decimal(measured))
                    answer, created = Answer.objects.update_or_create(
                        sample=sample, question=question,
                        metric=metric, defaults={
                            'measured': int(measured),
                            'unit': unit,
                            'created_at': created_at,
                            'collected_by': collected_by})
                except (ValueError, decimal.InvalidOperation, DataError) as err:
                    # We cannot convert to integer (ex: "12.8kW/h")
                    # or the value exceeds 32-bit representation.
                    # XXX We store as a text value so it is not lost.
                    LOGGER.warning(
                        "\"%(measured)s\": %(err)s for '%(metric)s'",
                        measured=measured.replace('"', '\\"'),
                        err=str(err).strip(),
                        metric=metric.title)
                    unit = Unit.objects.get(slug='freetext')

            if unit.system not in Unit.NUMERICAL_SYSTEMS:
                if unit.system == Unit.SYSTEM_ENUMERATED:
                    try:
                        measured = Choice.objects.get(
                            unit=unit, text=measured).pk
                    except Choice.DoesNotExist:
                        choices = Choice.objects.filter(unit=unit)
                        raise ValidationError("'%s' is not a valid choice."\
                            " Expected one of %s." % (measured,
                            [choice.get('text', "")
                             for choice in six.itervalues(choices)]))
                else:
                    choice_rank = Choice.objects.filter(
                        unit=unit).aggregate(Max('rank')).get(
                            'rank__max', 0)
                    choice_rank = choice_rank + 1 if choice_rank else 1
                    choice = Choice.objects.create(
                        text=measured,
                        unit=unit,
                        rank=choice_rank)
                    measured = choice.pk
                answer, created = Answer.objects.update_or_create(
                    sample=sample, question=question,
                    metric=metric, defaults={
                        'measured': measured,
                        'unit': unit,
                        'created_at': created_at,
                        'collected_by': collected_by})
    except DataError as err:
        LOGGER.exception(err)
        raise ValidationError(
            "\"%(measured)s\": %(err)s for '%(metric)s'" % {
                'measured': measured.replace('"', '\\"'),
                'err': str(err).strip(),
                'metric': metric.title})

    return answer, created


class AnswerAPIView(SampleMixin, mixins.CreateModelMixin,
                    generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve a sample datapoint

    Providing {sample} is a set of datapoints for {account}, returns
    the datapoint in {sample} for question ranked {rank} in the campaign
    {sample} is part of.

    **Tags**: survey

    **Examples**

    .. code-block:: http

         GET /api/xia/sample/0123456789abcdef/1/ HTTP/1.1

    responds

    .. code-block:: json

        {
            "created_at": "2020-01-01T00:00:00Z",
            "measured": 12,
            "unit": "liters"
        }
    """
    serializer_class = AnswerSerializer
    lookup_rank_kwarg = 'rank'

    @property
    def metric(self):
        if not hasattr(self, '_metric'):
            self._metric = self.question.default_metric
        return self._metric

    @property
    def question(self):
        if not hasattr(self, '_question'):
            if self.sample:
                self._question = get_object_or_404(
                    get_question_model().objects.all(),
                    enumeratedquestions__campaign=self.sample.campaign,
                    enumeratedquestions__rank=self.rank)
            else:
                self._question = None  # API docs get here.
        return self._question

    @property
    def rank(self):
        return int(self.kwargs.get(self.lookup_rank_kwarg))

    def put(self, request, *args, **kwargs):
        """
        Update a sample datapoint

        Providing {sample} is a set of datapoints for {account}, updates
        the datapoint in {sample} for question ranked {rank} in the campaign
        {sample} is part of.

        **Tags**: survey

        **Examples**

        .. code-block:: http

             PUT /api/xia/sample/0123456789abcdef/1/ HTTP/1.1

        .. code-block:: json

            {
                "measured": 12
            }

        responds

        .. code-block:: json

            {
                "created_at": "2020-01-01T00:00:00Z",
                "measured": 12
            }
        """
        #pylint:disable=useless-super-delegation
        return super(AnswerAPIView, self).put(request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        """
        Delete a sample datapoint

        Providing {sample} is a set of datapoints for {account}, deletes
        the datapoint in {sample} for question ranked {rank} in the campaign
        {sample} is part of.

        **Tags**: survey

        **Examples**

        .. code-block:: http

             DELETE /api/xia/sample/0123456789abcdef/1/ HTTP/1.1
        """
        #pylint:disable=useless-super-delegation
        return super(AnswerAPIView, self).delete(request, *args, **kwargs)

    def get_queryset(self):
        return Answer.objects.filter(sample=self.sample)

    def get_serializer_context(self):
        context = super(AnswerAPIView, self).get_serializer_context()
        context.update({'question': self.question})
        return context

    @staticmethod
    def get_http_response(serializer, status=HTTP_200_OK, headers=None,
                          first_answer=False):#pylint:disable=unused-argument
        return http.Response(serializer.data, status=status, headers=headers)

    def update(self, request, *args, **kwargs):
        #pylint:disable=unused-argument
        partial = kwargs.pop('partial', False)
        serializer = self.get_serializer(data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        status = HTTP_200_OK
        headers = None
        first_answer = not(Answer.objects.filter(
            collected_by=self.request.user).exists())
        try:
            serializer.instance = self.get_queryset().filter(
                question=self.question).get()
            self.perform_update(serializer)
        except Answer.DoesNotExist:
            self.perform_create(serializer)
            status = HTTP_201_CREATED
            headers = self.get_success_headers(serializer.data)
        return self.get_http_response(serializer,
            status=status, headers=headers, first_answer=first_answer)

    def perform_update(self, serializer):
        created_at = datetime_or_now()
        datapoint = serializer.validated_data

        measured = datapoint.get('measured', None)
        if not measured:
            return

        user = self.request.user if is_authenticated(self.request) else None
        update_or_create_answer(
            datapoint,
            question=self.question,
            sample=self.sample,
            created_at=created_at,
            collected_by=user)

    def perform_create(self, serializer):
        return self.perform_update(serializer)


class SampleAPIView(SampleMixin, generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieves a sample

    Returns the state of a ``Sample`` and the list of associated
    ``Answer``.

    **Tags**: survey

    **Examples**

    .. code-block:: http

         GET /api/supplier-1/sample/46f66f70f5ad41b29c4df08f683a9a7a/ HTTP/1.1

    responds

    .. code-block:: json

    {
        "slug": "46f66f70f5ad41b29c4df08f683a9a7a",
        "created_at": "2018-01-24T17:03:34.926193Z",
        "time_spent": "00:00:00",
        "is_frozen": false,
        "account": "steve=shop",
        "campaign": "assessment"
    }
    """
    serializer_class = SampleSerializer

    def get_object(self):
        return self.sample

    def put(self, request, *args, **kwargs):
        """
        Updates a sample

        For example, mark the Sample as read-only.

        **Tags**: survey

        **Examples**

        .. code-block:: http

            PUT /api/sample/46f66f70f5ad41b29c4df08f683a9a7a/ HTTP/1.1

        .. code-block:: json

            {
                "is_frozen": false
            }

        responds

        .. code-block:: json

    .. code-block:: json

        {
            "slug": "46f66f70f5ad41b29c4df08f683a9a7a",
            "created_at": "2018-01-24T17:03:34.926193Z",
            "time_spent": "00:00:00",
            "is_frozen": false,
         """
        #pylint:disable=useless-super-delegation
        return super(SampleAPIView, self).put(request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        """
        Deletes a sample

        Removes a ``Sample`` and all associated ``Answer``
        from the database.

        **Tags**: survey

        **Examples**

        .. code-block:: http

            DELETE /api/sample/46f66f70f5ad41b29c4df08f683a9a7a/ HTTP/1.1
        """
        #pylint:disable=useless-super-delegation
        return super(SampleAPIView, self).delete(request, *args, **kwargs)


class SampleAnswersAPIView(SampleMixin, generics.ListCreateAPIView):
    """
    Retrieves answers from a sample

    **Tags**: survey

    **Examples**

    .. code-block:: http

         GET /api/supplier-1/sample/46f66f70f5ad41b29c4df08f683a9a7a/answers\
 HTTP/1.1

    responds

    .. code-block:: json

    {
        "count": 4,
        "results": [
            {
                "question": {
                    "path": "the-assessment-process-is-rigorous",
                    "default_metric": "weight",
                    "title": "The assessment process is rigorous"
                },
                "metric": "weight",
                "measured": "1",
                "unit": "kilograms"
            },
            {
                "question": {
                    "path": "a-policy-is-in-place",
                    "default_metric": "weight",
                    "title": "A policy is in place"
                },
                "metric": "weight",
                "measured": "2"
                "unit": "kilograms"
            },
            {
                "question": {
                    "path": "product-design",
                    "default_metric": "weight",
                    "title": "Product design"
                },
                "metric": "weight",
                "measured": "2"
                "unit": "kilograms"
            },
            {
                "question": {
                    "path": "packaging-design",
                    "default_metric": "weight",
                    "title": "Packaging design"
                },
                "metric": "weight",
                "measured": "3"
                "unit": "kilograms"
            }
        ]
    }
    """
    serializer_class = SampleAnswerSerializer

    # Used to POST and create an answer.
    @property
    def question(self):
        if not hasattr(self, '_question'):
            self._question = get_object_or_404(
                get_question_model().objects.all(), path=self.path)
        return self._question

    def get_queryset(self):
        if self.sample.is_frozen:
            return Answer.objects.filter(sample=self.sample,
                question__path__startswith=self.path).select_related(
                    'question', 'metric', 'unit', 'collected_by')

        queryset = Answer.objects.raw("""SELECT
    answers.id AS id,
    answers.created_at AS created_at,
    survey_question.id AS question_id,
    answers.metric_id AS metric_id,
    answers.unit_id AS unit_id,
    answers.measured AS measured,
    answers.denominator AS denominator,
    answers.collected_by_id AS collected_by_id,
    answers.sample_id AS sample_id,
    survey_enumeratedquestions.rank AS rank,
    survey_enumeratedquestions.required AS required
FROM survey_question
INNER JOIN survey_enumeratedquestions
  ON survey_question.id = survey_enumeratedquestions.question_id
LEFT OUTER JOIN (SELECT * FROM survey_answer WHERE sample_id=%(sample)d)
  AS answers ON survey_question.id = answers.question_id
WHERE survey_enumeratedquestions.campaign_id = %(campaign)d
  AND survey_question.path LIKE '%(prefix)s%%%%';""" % {
      'sample': self.sample.pk,
      'campaign': self.sample.campaign.pk,
      'prefix': self.path
  }).prefetch_related(
      'question', 'question__default_metric', 'metric', 'unit', 'collected_by')
        return queryset

    def get_serializer_class(self):
        if self.request.method.lower() == 'post':
            return AnswerSerializer
        return super(SampleAnswersAPIView, self).get_serializer_class()

    def get_serializer(self, *args, **kwargs):
        if isinstance(self.request.data, list):
            kwargs.update({'many': True})
        return super(SampleAnswersAPIView, self).get_serializer(
            *args, **kwargs)

    def post(self, request, *args, **kwargs):
        """
        Updates an answer in a sample

        **Tags**: survey

        **Examples**

        .. code-block:: http

            POST /api/sample/46f66f70f5ad41b29c4df08f683a9a7a/answers/water-use\
 HTTP/1.1

        .. code-block:: json

            {
                "metric": "weight",
                "measured": "1",
                "unit": "kilograms"
            },

        responds

        .. code-block:: json

    .. code-block:: json

            {
                "metric": "weight",
                "measured": "1",
                "unit": "kilograms"
            },
        """
        #pylint:disable=useless-super-delegation
        return super(SampleAnswersAPIView, self).post(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        #pylint:disable=unused-argument,too-many-locals,too-many-statements
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data
        if not isinstance(serializer.validated_data, list):
            validated_data = [serializer.validated_data]

        user = self.request.user if is_authenticated(self.request) else None
        created_at = datetime_or_now()
        at_least_one_created = False
        results = []
        errors = []

        for datapoint in validated_data:
            try:
                answer, created = update_or_create_answer(
                    datapoint, question=self.question,
                    sample=self.sample, created_at=created_at,
                    collected_by=user)
                results += [answer]
                if created:
                    at_least_one_created = True
            except ValidationError as err:
                errors += [err]
        if errors:
            raise ValidationError(errors)

        first_answer = False #XXX
        headers = self.get_success_headers(serializer.data)
        return self.get_http_response(results,
            status=HTTP_201_CREATED if at_least_one_created else HTTP_200_OK,
            headers=headers, first_answer=first_answer)

    @staticmethod
    def _expand_choices(results):
        choices = []
        for answer in results:
            metric = (answer.metric if answer.metric
                else answer.question.default_metric)
            unit = answer.unit if answer.unit else metric.unit
            if unit.system not in Unit.NUMERICAL_SYSTEMS:
                choices += [int(answer.measured)]
        choices = dict(Choice.objects.filter(
            pk__in=choices).values_list('pk', 'text'))
        for answer in results:
            if unit.system not in Unit.NUMERICAL_SYSTEMS:
                answer.measured = choices.get(int(answer.measured))
        return results

    def get_http_response(self, results, status=HTTP_200_OK, headers=None,
                          first_answer=False):#pylint:disable=unused-argument
        self._expand_choices(results)
        return http.Response(results, status=status, headers=headers)


class SampleFreezeAPIView(SampleMixin, generics.CreateAPIView):
    """
    Freezes all answers in the ``Sample``.

    **Tags**: survey

    **Examples**

    .. code-block:: http

        POST /api/sample/46f66f70f5ad41b29c4df08f683a9a7a/freeze/ HTTP/1.1

    responds

    .. code-block:: json

        {
            "slug": "46f66f70f5ad41b29c4df08f683a9a7a",
            "created_at": "2018-01-24T17:03:34.926193Z",
            "campaign": "best-practices",
            "is_frozen": true
        }
    """
    serializer_class = SampleSerializer

    def create(self, request, *args, **kwargs):
        self.sample.is_frozen = True
        self.sample.save()
        serializer = self.get_serializer(self.sample)
        return http.Response(serializer.data)


class SampleResetAPIView(SampleMixin, generics.CreateAPIView):
    """
    Resets all answers in the ``Sample``.

    **Tags**: survey

    **Examples**

    .. code-block:: http

        POST /api/sample/46f66f70f5ad41b29c4df08f683a9a7a/reset/ HTTP/1.1

    responds

    .. code-block:: json

        {
            "slug": "46f66f70f5ad41b29c4df08f683a9a7a",
            "created_at": "2018-01-24T17:03:34.926193Z",
            "campaign": "best-practices"
        }
    """
    serializer_class = SampleSerializer

    def create(self, request, *args, **kwargs):
        self.sample.answers.all().delete()
        serializer = self.get_serializer(instance=self.sample)
        headers = self.get_success_headers(serializer.data)
        return http.Response(serializer.data, status=HTTP_201_CREATED,
            headers=headers)


class SampleRecentCreateAPIView(AccountMixin, mixins.RetrieveModelMixin,
                                generics.CreateAPIView):
    """
    Retrieves latest ``Sample`` for a profile.

    **Tags**: survey

    **Examples**

    .. code-block:: http

        GET /api/supplier-1/sample/ HTTP/1.1

    responds

    .. code-block:: json

        {
            "slug": "46f66f70f5ad41b29c4df08f683a9a7a",
            "created_at": "2018-01-24T17:03:34.926193Z",
            "campaign": "best-practices"
        }
    """
    serializer_class = SampleSerializer

    def get_object(self):
        return Sample.objects.filter(
            account=self.account).order_by('-created_at').first()

    def get(self, request, *args, **kwargs):
        #pylint:disable=useless-super-delegation
        return self.retrieve(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        """
        Creates a ``Sample`` from the ``Campaign``.

        **Tags**: survey

        **Examples**

        .. code-block:: http

            POST /api/supplier-1/sample/ HTTP/1.1

        .. code-block:: json

            {
                "campaign": "best-practices"
            }

        responds

        .. code-block:: json

            {
                "slug": "46f66f70f5ad41b29c4df08f683a9a7a",
                "created_at": "2018-01-24T17:03:34.926193Z",
                "campaign": "best-practices"
            }
        """
        #pylint:disable=useless-super-delegation
        return super(SampleRecentCreateAPIView, self).post(
            request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(account=self.account)
