# Copyright (c) 2019, DjaoDjin inc.
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

import logging

from django.db import transaction
from django.db.models import Max
from django.db.utils import DataError
from rest_framework import generics, mixins
from rest_framework import response as http
from rest_framework.exceptions import ValidationError
from rest_framework.status import HTTP_200_OK, HTTP_201_CREATED

from .serializers import AnswerSerializer, SampleSerializer
from ..mixins import SampleMixin, IntervieweeMixin
from ..models import Answer, Choice, EnumeratedQuestions, Unit
from ..utils import datetime_or_now, get_question_model


LOGGER = logging.getLogger(__name__)


class AnswerAPIView(SampleMixin, mixins.CreateModelMixin,
                    generics.RetrieveUpdateDestroyAPIView):

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
            self._question = get_question_model().objects.get(
                enumeratedquestions__campaign=self.sample.survey,
                enumeratedquestions__rank=self.kwargs.get(
                    self.lookup_rank_kwarg))
        return self._question

    @property
    def rank(self):
        return int(self.kwargs.get(self.lookup_rank_kwarg))

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
        errors = []
        try:
            with transaction.atomic():
                metric = self.question.default_metric
                try:
                    measured = int(serializer.validated_data['measured'])
                except ValueError:
                    if metric.unit.system != Unit.SYSTEM_FREETEXT:
                        raise DataError("\"%s\" is invalid" %
                            serializer.validated_data['measured'].replace(
                                '"', '\\"'))
                    measured = serializer.instance.measured
                    Choice.objects.filter(pk=measured).update(
                        text=serializer.validated_data['measured'])
                serializer.instance.created_at = created_at
                serializer.instance.measured = measured
                serializer.instance.collected_by = self.request.user
                serializer.instance.save()
        except DataError as err:
            LOGGER.exception(err)
            errors += [
                "\"%(measured)s\": %(err)s for question of type '%(metric)s'" %
                {
                    'measured': serializer.validated_data['measured'].replace(
                        '"', '\\"'),
                    'err': str(err),
                    'metric': metric.title}
            ]
        if errors:
            raise ValidationError(errors)

    def perform_create(self, serializer):
        created_at = datetime_or_now()
        errors = []
        if not serializer.validated_data['measured']:
            return
        try:
            with transaction.atomic():
                metric = self.question.default_metric
                try:
                    measured = int(serializer.validated_data['measured'])
                except ValueError:
                    if metric.unit.system != Unit.SYSTEM_FREETEXT:
                        raise DataError("\"%s\" is invalid" %
                            serializer.validated_data['measured'].replace(
                                '"', '\\"'))
                    choice_rank = Choice.objects.filter(
                        unit=metric.unit).aggregate(Max('rank')).get(
                            'rank__max', 0)
                    choice_rank = choice_rank + 1 if choice_rank else 1
                    choice = Choice.objects.create(
                        text=serializer.validated_data['measured'],
                        unit=metric.unit,
                        rank=choice_rank)
                    measured = choice.id
                Answer.objects.update_or_create(
                    sample=self.sample,
                    question=self.question,
                    metric=metric,
                    defaults={
                        'created_at': created_at,
                        'measured': measured,
                        'collected_by': self.request.user,
                        'rank': EnumeratedQuestions.objects.filter(
                            campaign=self.sample.survey,
                            question=self.question).first().rank})
        except DataError as err:
            LOGGER.exception(err)
            errors += [
                "\"%(measured)s\": %(err)s for question of type '%(metric)s'" %
                {
                    'measured': serializer.validated_data['measured'].replace(
                        '"', '\\"'),
                    'err': str(err),
                    'metric': metric.title}
            ]
        if errors:
            raise ValidationError(errors)


class SampleAPIView(SampleMixin, generics.RetrieveUpdateDestroyAPIView):
    """
    ``GET`` returns the state of a ``Sample`` and the list of associated
    ``Answer``.

    **Example request**:

    .. sourcecode:: http

        GET /api/sample/46f66f70f5ad41b29c4df08f683a9a7a/

    **Example response**:

    .. sourcecode:: http

    {
        "slug": "46f66f70f5ad41b29c4df08f683a9a7a",
        "created_at": "2018-01-24T17:03:34.926193Z",
        "time_spent": "00:00:00",
        "is_frozen": false,
        "answers": [
            {
                "question": "the-assessment-process-is-rigorous",
                "measured": "1"
            },
            {
                "question": "a-policy-is-in-place",
                "measured": "2"
            },
            {
                "question": "product-design",
                "measured": "2"
            },
            {
                "question": "packaging-design",
                "measured": "3"
            },
            {
                "question": "reduce-combustion-air-flow-to-optimum",
                "measured": "2"
            },
            {
                "question": "adjust-air-fuel-ratio",
                "measured": "2"
            },
            {
                "question": "recover-heat-from-hot-waste-water",
                "measured": "4"
            },
            {
                "question": "educe-hot-water-temperature-to-minimum-required",
                "measured": "4"
            }
        ]
    }

    ``PUT`` updates a ``Sample``. For example, mark the Sample as read-only.

    .. sourcecode:: http

        PUT /api/sample/46f66f70f5ad41b29c4df08f683a9a7a/

    **Example response**:

    .. sourcecode:: http

        {
            "is_frozen": false
        }

    ``DELETE`` removes a ``Sample`` and all associated ``Answer``
    from the database.

    .. sourcecode:: http

        DELETE /api/sample/46f66f70f5ad41b29c4df08f683a9a7a/
    """

    serializer_class = SampleSerializer

    def get_object(self):
        return self.sample


class SampleResetAPIView(SampleMixin, generics.CreateAPIView):
    """
    ``POST`` resets all answers in the ``Sample``.

    .. sourcecode:: http

        POST /api/sample/46f66f70f5ad41b29c4df08f683a9a7a/reset/

    **Example response**:

    .. sourcecode:: http

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


class SampleCreateAPIView(IntervieweeMixin, generics.CreateAPIView):
    """
    ``POST`` creates a ``Sample`` from the ``Campaign``.

    .. sourcecode:: http

        POST /api/sample/
        {
            "campaign": "best-practices"
        }

    **Example response**:

    .. sourcecode:: http

        {
            "slug": "46f66f70f5ad41b29c4df08f683a9a7a",
            "created_at": "2018-01-24T17:03:34.926193Z",
            "campaign": "best-practices"
        }
    """
    serializer_class = SampleSerializer

    def perform_create(self, serializer):
        serializer.save(account=self.interviewee)
