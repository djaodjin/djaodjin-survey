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

from ..compat import six
from ..mixins import SampleMixin, IntervieweeMixin
from ..models import Answer, Choice, EnumeratedQuestions, Sample, Unit
from .serializers import (AnswerSerializer, SampleAnswerSerializer,
    SampleSerializer)
from ..utils import datetime_or_now, get_question_model


LOGGER = logging.getLogger(__name__)


class AnswerAPIView(SampleMixin, mixins.CreateModelMixin,
                    generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve a survey datapoint

    Providing {sample} is a set of datapoints for {interviewee}, returns
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
    lookup_field = 'rank'

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
                    enumeratedquestions__campaign=self.sample.survey,
                    enumeratedquestions__rank=self.kwargs.get(
                        self.lookup_rank_kwarg))
            else:
                self._question = None  # API docs get here.
        return self._question

    @property
    def rank(self):
        return int(self.kwargs.get(self.lookup_rank_kwarg))

    def put(self, request, *args, **kwargs):
        """
        Update a survey datapoint

        Providing {sample} is a set of datapoints for {interviewee}, updates
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
        return super(AnswerAPIView, self).put(request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        """
        Delete  a survey datapoint

        Providing {sample} is a set of datapoints for {interviewee}, deletes
        the datapoint in {sample} for question ranked {rank} in the campaign
        {sample} is part of.

        **Tags**: survey

        **Examples**

        .. code-block:: http

             DELETE /api/xia/sample/0123456789abcdef/1/ HTTP/1.1
        """
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
        datapoint = serializer.validated_data
        measured = datapoint.get('measured', None)
        if not measured:
            return
        created_at = datetime_or_now()
        rank = EnumeratedQuestions.objects.get(
            campaign=self.sample.survey,
            question=self.question).rank
        errors = []
        try:
            with transaction.atomic():
                metric = datapoint.get('metric', self.question.default_metric)
                unit = datapoint.get('unit', metric.unit)
                if unit.system in Unit.NUMERICAL_SYSTEMS:
                    try:
                        try:
                            measured = str(int(measured))
                        except ValueError:
                            measured = '{:.0f}'.format(
                                decimal.Decimal(measured))
                        Answer.objects.update_or_create(
                            sample=self.sample, question=self.question,
                            metric=metric, defaults={
                                'measured': int(measured),
                                'unit': unit,
                                'created_at': created_at,
                                'collected_by': self.request.user,
                                'rank': rank})
                    except (ValueError, decimal.InvalidOperation,
                            DataError) as err:
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
                                " Expected one of %s." % (measured, [
                                    choice.get('text', "")
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
                    Answer.objects.update_or_create(
                        sample=self.sample, question=self.question,
                        metric=metric, defaults={
                            'measured': measured,
                            'unit': unit,
                            'created_at': created_at,
                            'collected_by': self.request.user,
                            'rank': rank})
        except DataError as err:
            LOGGER.exception(err)
            errors += [
                "\"%(measured)s\": %(err)s for '%(metric)s'" % {
                    'measured': measured.replace('"', '\\"'),
                    'err': str(err).strip(),
                    'metric': metric.title}
            ]
        if errors:
            raise ValidationError(errors)

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
    lookup_path_kwarg = 'path'
    serializer_class = SampleAnswerSerializer

    @property
    def question(self):
        if not hasattr(self, '_question'):
            self._question = get_object_or_404(
                get_question_model().objects.all(),
                path=self.kwargs.get(self.lookup_path_kwarg))
        return self._question

    def get_queryset(self):
        kwargs = {}
        prefix = self.kwargs.get(self.lookup_path_kwarg)
        if not prefix:
            prefix = ""
        if self.sample.is_frozen:
            return Answer.objects.filter(sample=self.sample,
                question__path__startswith=prefix).select_related(
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
    answers.rank AS rank
FROM survey_question
LEFT OUTER JOIN (SELECT * FROM survey_answer WHERE sample_id=%(sample)d)
  AS answers ON survey_question.id = answers.question_id
WHERE survey_question.path LIKE '%(path)s%%%%';
""" % {'sample': self.sample.pk, 'path': prefix}).prefetch_related(
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
        return super(SampleAnswersAPIView, self).post(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        created_at = datetime_or_now()
        results = []
        at_least_one_created = False
        rank = EnumeratedQuestions.objects.get(
            campaign=self.sample.survey,
            question=self.question).rank
        errors = []
        validated_data = serializer.validated_data
        if not isinstance(serializer.validated_data, list):
            validated_data = [serializer.validated_data]
        for datapoint in validated_data:
            measured = datapoint.get('measured', None)
            try:
                with transaction.atomic():
                    metric = datapoint.get(
                        'metric', self.question.default_metric)
                    unit = datapoint.get('unit', metric.unit)
                    if unit.system in Unit.NUMERICAL_SYSTEMS:
                        try:
                            try:
                                measured = str(int(measured))
                            except ValueError:
                                measured = '{:.0f}'.format(
                                    decimal.Decimal(measured))
                            answer, created = Answer.objects.update_or_create(
                                sample=self.sample, question=self.question,
                                metric=metric, defaults={
                                    'measured': int(measured),
                                    'unit': unit,
                                    'created_at': created_at,
                                    'collected_by': self.request.user,
                                    'rank': rank})
                            results += [answer]
                            if created:
                                at_least_one_created = True
                        except (ValueError,
                            decimal.InvalidOperation, DataError) as err:
                            # We cannot convert to integer (ex: "12.8kW/h")
                            # or the value exceeds 32-bit representation.
                            # XXX We store as a text value so it is not lost.
                            LOGGER.warning(
                                "\"%(measured)s\": %(err)s for '%(metric)s'" % {
                                'measured': measured.replace('"', '\\"'),
                                'err': str(err).strip(),
                                'metric': metric.title})
                            unit = Unit.objects.get(slug='freetext')

                    if unit.system not in Unit.NUMERICAL_SYSTEMS:
                        if unit.system == Unit.SYSTEM_ENUMERATED:
                            try:
                                measured = Choice.objects.get(
                                    unit=unit, text=measured).pk
                            except Choice.DoesNotExist:
                                choices = Choice.objects.filter(unit=unit)
                                raise ValidationError(
                                    "'%s' is not a valid choice."\
                                    " Expected one of %s." % (
                                    measured, [choice.get('text', "")
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
                            sample=self.sample, question=self.question,
                            metric=metric, defaults={
                                'measured': measured,
                                'unit': unit,
                                'created_at': created_at,
                                'collected_by': self.request.user,
                                'rank': rank})
                        results += [answer]
                        if created:
                            at_least_one_created = True
            except DataError as err:
                LOGGER.exception(err)
                errors += [
                    "\"%(measured)s\": %(err)s for '%(metric)s'" % {
                        'measured': measured.replace('"', '\\"'),
                        'err': str(err).strip(),
                        'metric': metric.title}
                ]
        if errors:
            raise ValidationError(errors)

        first_answer = False #XXX
        headers = self.get_success_headers(serializer.data)
        return self.get_http_response(results,
            status=HTTP_201_CREATED if at_least_one_created else HTTP_200_OK,
            headers=headers, first_answer=first_answer)

    def _expand_choices(self, results):
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


class SampleRecentCreateAPIView(IntervieweeMixin, mixins.RetrieveModelMixin,
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
        return super(SampleRecentCreateAPIView, self).post(
            request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(account=self.interviewee)
