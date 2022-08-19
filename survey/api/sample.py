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
from django.db.models import Max
from django.db.utils import DataError
from rest_framework import generics, mixins
from rest_framework import response as http
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.status import HTTP_200_OK, HTTP_201_CREATED

from ..compat import six, is_authenticated
from ..docs import OpenAPIResponse, swagger_auto_schema
from ..mixins import AccountMixin, SampleMixin
from ..models import Answer, Choice, Sample, Unit, UnitEquivalences
from .serializers import (AnswerSerializer, SampleAnswerSerializer,
    SampleCreateSerializer, SampleSerializer)
from ..utils import datetime_or_now, get_question_model, is_sqlite3


LOGGER = logging.getLogger(__name__)


def update_or_create_answer(datapoint, question, sample, created_at,
                            collected_by=None):
    answer = None
    created = False
    measured = datapoint.get('measured', None)
    unit = datapoint.get('unit', question.default_unit)
    try:
        with transaction.atomic():
            if unit.system in Unit.NUMERICAL_SYSTEMS:
                try:
                    try:
                        measured = str(int(measured))
                    except ValueError:
                        measured = '{:.0f}'.format(decimal.Decimal(measured))
                    Answer.objects.filter(sample=sample, question=question,
                        unit__in=UnitEquivalences.objects.filter(
                            source=unit).values('target')).delete()
                    answer, created = Answer.objects.update_or_create(
                        sample=sample, question=question, unit=unit,
                        defaults={
                            'measured': int(measured),
                            'created_at': created_at,
                            'collected_by': collected_by})
                    if sample and sample.updated_at != created_at:
                        sample.updated_at = created_at
                        sample.save()
                except (ValueError, decimal.InvalidOperation, DataError) as err:
                    # We cannot convert to integer (ex: "12.8kW/h")
                    # or the value exceeds 32-bit representation.
                    # XXX We store as a text value so it is not lost.
                    LOGGER.warning(
                        "\"%(measured)s\": %(err)s for '%(unit)s'" % {
                        'measured': measured.replace('"', '\\"'),
                        'err': str(err).strip(),
                        'unit': unit.title})
                    unit = Unit.objects.get(slug='freetext')

            if unit.system not in Unit.NUMERICAL_SYSTEMS:
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
                    sample=sample, question=question, unit=unit,
                    defaults={
                        'measured': measured,
                        'created_at': created_at,
                        'collected_by': collected_by})
                if sample and sample.updated_at != created_at:
                    sample.updated_at = created_at
                    sample.save()
    except DataError as err:
        LOGGER.exception(err)
        raise ValidationError(
            "\"%(measured)s\": %(err)s for '%(unit)s'" % {
                'measured': measured.replace('"', '\\"'),
                'err': str(err).strip(),
                'unit': unit.title})

    return answer, created


class AnswerAPIView(SampleMixin, mixins.CreateModelMixin,
                    generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve a sample datapoint

    Providing {sample} is a set of datapoints for {account}, returns
    the datapoint in {sample} for question ranked {rank} in the campaign
    {sample} is part of.

    **Tags**: assessments

    **Examples**

    .. code-block:: http

         GET /api/xia/sample/0123456789abcdef/1/ HTTP/1.1

    responds

    .. code-block:: json

        {
            "created_at": "2020-01-01T00:00:00Z",
            "measured": 12,
            "unit": "tons"
        }
    """
    serializer_class = AnswerSerializer
    lookup_rank_kwarg = 'rank'

    @property
    def unit(self):
        if not hasattr(self, '_unit'):
            self._unit = self.question.default_unit
        return self._unit

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

        **Tags**: assessments

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

        **Tags**: assessments

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


class SampleAPIView(SampleMixin, generics.RetrieveAPIView):
    """
    Retrieves a sample

    Returns the state of a ``Sample`` (frozen or not) and other meta data.

    **Tags**: assessments

    **Examples**

    .. code-block:: http

         GET /api/supplier-1/sample/46f66f70f5ad41b29c4df08f683a9a7a HTTP/1.1

    responds

    .. code-block:: json

    {
        "slug": "46f66f70f5ad41b29c4df08f683a9a7a",
        "created_at": "2018-01-24T17:03:34.926193Z",
        "updated_at": "2018-01-24T17:03:34.926193Z",
        "is_frozen": false,
        "account": "supplier-1",
        "campaign": "best-practices"
    }
    """
    serializer_class = SampleSerializer

    def get_object(self):
        return self.sample


class SampleAnswersMixin(SampleMixin):

    @staticmethod
    def _as_extra_dict(extra):
        try:
            extra = json.loads(extra)
        except (TypeError, ValueError):
            extra = {}
        return extra

    def get_answers(self, prefix=None, sample=None, excludes=None):
        """
        Returns answers on a sample. In case the sample is still active,
        also returns questions on the associated campaign with no answer.

        The answers can be filtered such that only questions with a path
        starting by `prefix` are included. Questions included whose
        extra field does not contain `excludes` can be further removed
        from the results.
        """
        if not prefix:
            prefix = self.path
        if not sample:
            sample = self.sample
        extra_question_clause = (
            "AND survey_question.id NOT IN (SELECT id FROM survey_question"\
            " WHERE extra LIKE '%%%%%(extra)s%%%%')" % {
            'extra': excludes} if excludes else "")
        if sample.is_frozen:
            query_text = """
WITH answers AS (
    SELECT
      survey_answer.id AS id,
      survey_answer.created_at AS created_at,
      survey_answer.question_id AS question_id,
      survey_answer.unit_id AS unit_id,
      survey_answer.measured AS measured,
      survey_answer.denominator AS denominator,
      survey_answer.collected_by_id AS collected_by_id,
      survey_answer.sample_id AS sample_id,
      COALESCE(survey_choice.text,
        survey_answer.measured%(convert_to_text)s) AS measured_text
    FROM survey_answer
    INNER JOIN survey_question
      ON survey_answer.question_id = survey_question.id
    LEFT OUTER JOIN survey_choice
      ON survey_choice.id = survey_answer.measured
      AND survey_choice.unit_id = survey_answer.unit_id
    WHERE sample_id=%(sample)d
      AND survey_question.path LIKE '%(prefix)s%%%%'
      %(extra_question_clause)s
),
-- The following brings all current questions in the campaign
-- in an attempt to present a consistent display (i.e. order by rank).
campaign_questions AS (
    SELECT
      survey_question.id AS id,
      survey_enumeratedquestions.rank AS rank,
      survey_enumeratedquestions.required AS required
    FROM survey_question
      INNER JOIN survey_enumeratedquestions
      ON survey_question.id = survey_enumeratedquestions.question_id
    WHERE survey_enumeratedquestions.campaign_id = %(campaign)d
      AND survey_question.path LIKE '%(prefix)s%%%%'
      %(extra_question_clause)s
),
-- The following returns all answered and current questions.
--questions AS (
--    SELECT * FROM campaign_questions
--    UNION (
--    SELECT
--      answers.question_id AS id,
--      0 AS rank,
--      'f' AS required
--    FROM answers
--    INNER JOIN survey_question
--      ON answers.question_id = survey_question.id
--    LEFT OUTER JOIN campaign_questions
--      ON answers.question_id = campaign_questions.id
--    WHERE campaign_questions.id IS NULL
--      AND survey_question.path LIKE '%(prefix)s%%%%'
--      %(extra_question_clause)s
--    )
--)
-- The following returns all answered questions only.
questions AS (
    SELECT DISTINCT(answers.question_id) AS id,
      COALESCE(campaign_questions.rank, 0) AS rank,
      COALESCE(campaign_questions.required, 'f') AS required
    FROM answers
    LEFT OUTER JOIN campaign_questions
      ON answers.question_id = campaign_questions.id
)
SELECT
    answers.id AS id,
    answers.created_at AS created_at,
    questions.id AS question_id,
    answers.unit_id AS unit_id,
    answers.measured AS measured,
    answers.denominator AS denominator,
    answers.collected_by_id AS collected_by_id,
    answers.sample_id AS sample_id,
    questions.rank AS _rank,
    questions.required AS required,
    answers.measured_text AS measured_text
FROM questions
LEFT OUTER JOIN answers
  ON questions.id = answers.question_id""" % {
      'campaign': sample.campaign.pk,
      'convert_to_text': ("" if is_sqlite3() else "::text"),
      'extra_question_clause': extra_question_clause,
      'prefix': prefix,
      'sample': sample.pk,
  }
        else:
            query_text = """
WITH answers AS (
    SELECT
      survey_answer.id AS id,
      survey_answer.created_at AS created_at,
      survey_answer.question_id AS question_id,
      survey_answer.unit_id AS unit_id,
      survey_answer.measured AS measured,
      survey_answer.denominator AS denominator,
      survey_answer.collected_by_id AS collected_by_id,
      survey_answer.sample_id AS sample_id,
      COALESCE(survey_choice.text,
        survey_answer.measured%(convert_to_text)s) AS measured_text
    FROM survey_answer
    LEFT OUTER JOIN survey_choice
      ON survey_choice.id = survey_answer.measured
      AND survey_choice.unit_id = survey_answer.unit_id
    WHERE sample_id=%(sample)d
),
campaign_questions AS (
    SELECT
      survey_question.id AS id,
      survey_enumeratedquestions.rank AS rank,
      survey_enumeratedquestions.required AS required
    FROM survey_question
      INNER JOIN survey_enumeratedquestions
      ON survey_question.id = survey_enumeratedquestions.question_id
    WHERE survey_enumeratedquestions.campaign_id = %(campaign)d
      AND survey_question.path LIKE '%(prefix)s%%%%'
      %(extra_question_clause)s
)
SELECT
    answers.id AS id,
    answers.created_at AS created_at,
    campaign_questions.id AS question_id,
    answers.unit_id AS unit_id,
    answers.measured AS measured,
    answers.denominator AS denominator,
    answers.collected_by_id AS collected_by_id,
    answers.sample_id AS sample_id,
    campaign_questions.rank AS _rank,
    campaign_questions.required AS required,
    answers.measured_text AS measured_text
FROM campaign_questions
LEFT OUTER JOIN answers
  ON campaign_questions.id = answers.question_id""" % {
      'campaign': sample.campaign.pk,
      'convert_to_text': ("" if is_sqlite3() else "::text"),
      'extra_question_clause': extra_question_clause,
      'prefix': prefix,
      'sample': sample.pk,
  }
        return Answer.objects.raw(query_text).prefetch_related(
      'unit', 'collected_by', 'question', 'question__content',
      'question__default_unit')



class SampleAnswersAPIView(SampleAnswersMixin, generics.ListCreateAPIView):
    """
    Lists measurements from a sample

    The list returned contains at least one measurement for each question
    in the campaign. If there are no measurement yet on a question, ``measured``
    will be null.

    There might be more than one measurement per question as long as there are
    no duplicated ``unit`` per question. For example, to the question
    ``adjust-air-fuel-ratio``, there could be a measurement with unit
    ``assessment`` (Mostly Yes/ Yes / No / Mostly No) and a measurement with
    unit ``freetext`` (i.e. a comment).

    The {sample} must belong to {organization}.

    {path} can be used to filter the tree of questions by a prefix.

    **Tags**: assessments

    **Examples**

    .. code-block:: http

         GET /api/supplier-1/sample/46f66f70f5ad41b29c4df08f683a9a7a/answers\
/construction HTTP/1.1

    responds

    .. code-block:: json

    {
        "count": 3,
        "previous": null,
        "next": null,
        "results": [
            {
                "question": {
                    "path": "/construction/governance/the-assessment\
-process-is-rigorous",
                    "title": "The assessment process is rigorous",
                    "default_unit": {
                        "slug": "assessment",
                        "title": "assessments",
                        "system": "enum",
                        "choices": [
                        {
                            "rank": 1,
                            "text": "mostly-yes",
                            "descr": "Mostly yes"
                        },
                        {
                            "rank": 2,
                            "text": "yes",
                            "descr": "Yes"
                        },
                        {
                            "rank": 3,
                            "text": "no",
                            "descr": "No"
                        },
                        {
                            "rank": 4,
                            "text": "mostly-no",
                            "descr": "Mostly no"
                        }
                        ]
                    },
                    "ui_hint": "radio"
                },
                "required": true,
                "measured": "yes",
                "unit": "assessment",
                "created_at": "2020-09-28T00:00:00.000000Z",
                "collected_by": "steve"
            },
            {
                "question": {
                    "path": "/construction/governance/the-assessment\
-process-is-rigorous",
                    "title": "The assessment process is rigorous",
                    "default_unit": {
                        "slug": "assessment",
                        "title": "assessments",
                        "system": "enum",
                        "choices": [
                        {
                            "rank": 1,
                            "text": "mostly-yes",
                            "descr": "Mostly yes"
                        },
                        {
                            "rank": 2,
                            "text": "yes",
                            "descr": "Yes"
                        },
                        {
                            "rank": 3,
                            "text": "no",
                            "descr": "No"
                        },
                        {
                            "rank": 4,
                            "text": "mostly-no",
                            "descr": "Mostly no"
                        }
                        ]
                    },
                    "ui_hint": "radio"
                },
                "measured": "Policy document on the public website",
                "unit": "freetext",
                "created_at": "2020-09-28T00:00:00.000000Z",
                "collected_by": "steve"
            },
            {
                "question": {
                    "path": "/construction/production/adjust-air-fuel\
-ratio",
                    "title": "Adjust Air fuel ratio",
                    "default_unit": {
                        "slug": "assessment",
                        "title": "assessments",
                        "system": "enum",
                        "choices": [
                        {
                            "rank": 1,
                            "text": "mostly-yes",
                            "descr": "Mostly yes"
                        },
                        {
                            "rank": 2,
                            "text": "yes",
                            "descr": "Yes"
                        },
                        {
                            "rank": 3,
                            "text": "no",
                            "descr": "No"
                        },
                        {
                            "rank": 4,
                            "text": "mostly-no",
                            "descr": "Mostly no"
                        }
                        ]
                    },
                    "ui_hint": "radio"
                },
                "required": true,
                "measured": null,
                "unit": null
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
        return self.get_answers()

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
        Updates a measurement in a sample

        This API end-point attaches a measurement (``measured`` field)
        in ``unit`` (meters, kilograms, etc.) to a question (also called metric)
        named {path} as part of a {sample}.

        If a measurement with that ``unit`` already exists for the couple
        ({path}, {sample}), the previous measurement is replaced, otherwise it
        is added.

        If ``unit`` is not specified, the default unit for the question is used.

        The {sample} must belong to {organization} and be updatable.

        **Tags**: assessments

        **Examples**

        .. code-block:: http

            POST /api/supplier-1/sample/724bf9648af6420ba79c8a37f962e97e/\
answers/construction/packaging-design HTTP/1.1

        .. code-block:: json

            {
               "measured": "mostly-no",
               "unit": "assessment"
            }

        responds

        .. code-block:: json

            {
                "question": {
                    "path": "/construction/packaging-design",
                    "default_unit": {
                        "slug": "assessment",
                        "title": "assessments",
                        "system": "enum",
                        "choices": [
                        {
                            "rank": 1,
                            "text": "mostly-yes",
                            "descr": "Mostly yes"
                        },
                        {
                            "rank": 2,
                            "text": "yes",
                            "descr": "Yes"
                        },
                        {
                            "rank": 3,
                            "text": "no",
                            "descr": "No"
                        },
                        {
                            "rank": 4,
                            "text": "mostly-no",
                            "descr": "Mostly no"
                        }
                        ]
                    },
                    "title": "Packaging design"
                },
                "created_at": "2020-09-28T00:00:00.000000Z",
                "collected_by": "steve",
                "measured": "mostly-no",
                "unit": "assessment"
            }
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

        if self.sample.is_frozen:
            raise ValidationError("sample is frozen")

        for datapoint in validated_data:
            measured = datapoint.get('measured', None)
            if not measured:
                continue
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
            unit = (answer.unit if answer.unit
                else answer.question.default_unit)
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
        serializer = self.get_serializer(results, many=True)
        return http.Response(serializer.data, status=status, headers=headers)


class SampleCandidatesMixin(SampleMixin):

    def get_candidates(self, prefix=None, extra=None, excludes=None):
        """
        Returns candidate answers on a sample. In case the sample is still
        active, also returns questions on the associated campaign with
        no answer.

        The candidates can be filtered such that only questions with a path
        starting by `prefix` are included. Questions included whose
        extra field does not contain `excludes` can be further removed
        from the results.
        """
        if not prefix:
            prefix = self.path
        if extra:
            extra_clause = "AND survey_sample.extra LIKE '%%%(extra)s%%'" % {
                'extra':extra }
        else:
            extra_clause = "AND survey_sample.extra IS NULL"
        extra_question_clause = (
            "AND survey_question.id NOT IN (SELECT id FROM survey_question"\
            " WHERE extra LIKE '%%%%%(extra)s%%%%')" % {
            'extra': excludes} if excludes else "")
        candidates_sql = """
        WITH
        latest_answers AS (
          SELECT
            survey_question.content_id AS content_id,
            survey_answer.unit_id AS unit_id,
            MAX(survey_answer.created_at) AS created_at
          FROM survey_answer INNER JOIN survey_question
            ON survey_answer.question_id = survey_question.id
          INNER JOIN survey_sample
            ON survey_answer.sample_id = survey_sample.id
          WHERE survey_sample.is_frozen
            AND survey_sample.account_id = %(account_id)d
            %(extra_clause)s
          GROUP BY content_id, unit_id
        ),

        content_answers AS (
          SELECT
            survey_answer.id AS id,
            survey_answer.created_at AS created_at,
            survey_question.content_id AS content_id,
            survey_answer.unit_id AS unit_id,
            survey_answer.measured AS measured,
            survey_answer.denominator AS denominator,
            survey_answer.collected_by_id AS collected_by_id,
            survey_answer.sample_id AS sample_id
          FROM survey_answer INNER JOIN survey_question
            ON survey_answer.question_id = survey_question.id
          INNER JOIN survey_sample
            ON survey_answer.sample_id = survey_sample.id
          WHERE survey_sample.account_id = %(account_id)d
        ),

        candidate_answers AS (
          SELECT
            content_answers.id AS id,
            content_answers.created_at AS created_at,
            content_answers.content_id AS content_id,
            content_answers.unit_id AS unit_id,
            content_answers.measured AS measured,
            content_answers.denominator AS denominator,
            content_answers.collected_by_id AS collected_by_id,
            content_answers.sample_id AS sample_id,
            COALESCE(survey_choice.text,
              content_answers.measured%(convert_to_text)s) AS measured_text
          FROM content_answers INNER JOIN latest_answers
            ON (content_answers.content_id = latest_answers.content_id
            AND content_answers.unit_id = latest_answers.unit_id
            AND content_answers.created_at = latest_answers.created_at)
          LEFT OUTER JOIN survey_choice
            ON survey_choice.id = content_answers.measured
            AND survey_choice.unit_id = content_answers.unit_id
        )

        SELECT
          candidate_answers.id AS id,
          candidate_answers.created_at AS created_at,
          survey_question.id AS question_id,
          candidate_answers.unit_id AS unit_id,
          candidate_answers.measured AS measured,
          candidate_answers.denominator AS denominator,
          candidate_answers.collected_by_id AS collected_by_id,
          candidate_answers.sample_id AS sample_id,
          survey_enumeratedquestions.rank AS _rank,
          survey_enumeratedquestions.required AS required,
          candidate_answers.measured_text AS measured_text
        FROM survey_question
        INNER JOIN survey_enumeratedquestions
          ON survey_enumeratedquestions.question_id = survey_question.id
        LEFT OUTER JOIN candidate_answers
          ON survey_question.content_id = candidate_answers.content_id
        WHERE survey_enumeratedquestions.campaign_id = %(campaign_id)d
          AND survey_question.path LIKE '%(prefix)s%%%%'
          %(extra_question_clause)s
        """ % {
            'account_id': self.sample.account.pk,
            'campaign_id': self.sample.campaign.pk,
            'convert_to_text': ("" if is_sqlite3() else "::text"),
            'extra_clause': extra_clause,
            'extra_question_clause': extra_question_clause,
            'prefix': prefix,
        }
        return Answer.objects.raw(candidates_sql).prefetch_related(
            'question', 'question__default_unit', 'unit', 'collected_by')


class SampleCandidatesAPIView(SampleCandidatesMixin, SampleAnswersMixin,
                              generics.ListCreateAPIView):
    """
    Retrieves candidate measurements for a sample

    The list returned contains at least one answer for each question
    in the campaign. If there are no answer yet on a question, ``measured``
    will be null.

    There might be more than one answer per question as long as there are
    no duplicated ``unit`` per question. For example, to the question
    ``adjust-air-fuel-ratio``, there could be an answer with unit
    ``assessment`` (Mostly Yes/ Yes / No / Mostly No) and an answer with
    unit ``freetext`` (i.e. a comment).

    The ``sample`` must belong to ``organization``.

    ``path`` can be used to filter the tree of questions by a prefix.

    **Tags**: assessments

    **Examples**

    .. code-block:: http

         GET /api/supplier-1/sample/46f66f70f5ad41b29c4df08f683a9a7a/candidates\
/construction HTTP/1.1

    responds

    .. code-block:: json

    {
        "count": 3,
        "previous": null,
        "next": null,
        "results": [
            {
                "question": {
                    "path": "/construction/governance/the-assessment\
-process-is-rigorous",
                    "title": "The assessment process is rigorous",
                    "default_unit": {
                        "slug": "assessment",
                        "title": "assessments",
                        "system": "enum",
                        "choices": [
                        {
                            "rank": 1,
                            "text": "mostly-yes",
                            "descr": "Mostly yes"
                        },
                        {
                            "rank": 2,
                            "text": "yes",
                            "descr": "Yes"
                        },
                        {
                            "rank": 3,
                            "text": "no",
                            "descr": "No"
                        },
                        {
                            "rank": 4,
                            "text": "mostly-no",
                            "descr": "Mostly no"
                        }
                        ]
                    },
                    "ui_hint": "radio"
                },
                "required": true,
                "measured": "yes",
                "unit": "assessment",
                "created_at": "2020-09-28T00:00:00.000000Z",
                "collected_by": "steve"
            },
            {
                "question": {
                    "path": "/construction/governance/the-assessment\
-process-is-rigorous",
                    "title": "The assessment process is rigorous",
                    "default_unit": {
                        "slug": "assessment",
                        "title": "assessments",
                        "system": "enum",
                        "choices": [
                        {
                            "rank": 1,
                            "text": "mostly-yes",
                            "descr": "Mostly yes"
                        },
                        {
                            "rank": 2,
                            "text": "yes",
                            "descr": "Yes"
                        },
                        {
                            "rank": 3,
                            "text": "no",
                            "descr": "No"
                        },
                        {
                            "rank": 4,
                            "text": "mostly-no",
                            "descr": "Mostly no"
                        }
                        ]
                    },
                    "ui_hint": "radio"
                },
                "measured": "Policy document on the public website",
                "unit": "freetext",
                "created_at": "2020-09-28T00:00:00.000000Z",
                "collected_by": "steve"
            },
            {
                "question": {
                    "path": "/construction/production/adjust-air-fuel\
-ratio",
                    "title": "Adjust Air fuel ratio",
                    "default_unit": {
                        "slug": "assessment",
                        "title": "assessments",
                        "system": "enum",
                        "choices": [
                        {
                            "rank": 1,
                            "text": "mostly-yes",
                            "descr": "Mostly yes"
                        },
                        {
                            "rank": 2,
                            "text": "yes",
                            "descr": "Yes"
                        },
                        {
                            "rank": 3,
                            "text": "no",
                            "descr": "No"
                        },
                        {
                            "rank": 4,
                            "text": "mostly-no",
                            "descr": "Mostly no"
                        }
                        ]
                    },
                    "ui_hint": "radio"
                },
                "required": true,
                "measured": null,
                "unit": null
            }
         ]
    }
    """
    serializer_class = SampleAnswerSerializer

    def create(self, request, *args, **kwargs):
        #pylint:disable=too-many-locals
        if self.sample.is_frozen:
            raise ValidationError("sample is frozen")

        at_time = datetime_or_now()
        at_least_one_created = False
        first_answer = not(Answer.objects.filter(
            collected_by=self.request.user).exists())
        answered = Answer.objects.filter(
            sample=self.sample).values_list('question_id', flat=True)
        with transaction.atomic():
            answers = []
            for candidate in self.get_candidates():
                if (candidate.question_id not in answered and
                    candidate.pk and
                    candidate.unit_id == candidate.question.default_unit_id):
                    candidate.pk = None
                    candidate.sample = self.sample
                    candidate.created_at = at_time
                    candidate.collected_by = request.user
                    answers += [candidate]
            Answer.objects.bulk_create(answers)
            at_least_one_created = bool(answers)
        results = []

        # XXX manual serializer to deliver to production Monday.
        choices = {}
        for choice in Choice.objects.filter(
                question__isnull=True,
                unit__slug=self.sample.campaign.slug).order_by('rank'):
            choices[choice.pk] = choice.text

        by_question = OrderedDict()
        for answer in self.get_answers():
            if answer.question_id not in by_question:
                question = answer.question
                by_question[answer.question_id] = {
                    'path': question.path,
                    'rank': answer.rank,
                    'title': question.content.title,
                    'picture': question.content.picture,
                    'extra': self._as_extra_dict(question.content.extra),
                    'environmental_value': question.environmental_value,
                    'business_value': question.business_value,
                    'implementation_ease': question.implementation_ease,
                    'profitability': question.profitability,
                    'avg_value': question.avg_value,
                    'default_unit': {
                        'slug': question.default_unit.slug,
                        'title': question.default_unit.title,
                        'system': question.default_unit.system
                    },
                    'ui_hint': question.ui_hint,
                    'rate': {choice: 0 for choice in six.itervalues(choices)}
                }
            question = by_question[answer.question_id]
            if 'answers' not in question:
                question.update({'answers': []})
            if answer.pk:
                answers = question['answers']
                answers += [{
                    'measured': answer.measured_text,
                    'unit': answer.unit.slug,
                    'created_at': answer.created_at,
                    'collected_by': (answer.collected_by.username
                        if answer.collected_by else ""),
                    # question fields
                    'ui_hint': answer.question.ui_hint,
                }]
        # XXX We re-order the answers so the default_unit (i.e. primary)
        # is first.
        for question in six.itervalues(by_question):
            default_unit = question.get('default_unit').get('slug')
            answers = question.get('answers')
            primary = None
            remainders = []
            for answer in answers:
                if answer.get('unit') == default_unit:
                    primary = answer
                else:
                    remainders += [answer]
            if not primary:
                primary = {
                    'measured': None,
                    'unit': default_unit,
                    # question fields
                    'ui_hint': question.get('ui_hint'),
                }
            question.update({'answers': [primary] + remainders})
        results = list(six.itervalues(by_question))

        return self.get_http_response({'results': results},
            status=HTTP_201_CREATED if at_least_one_created else HTTP_200_OK,
            first_answer=first_answer)

    @staticmethod
    def get_http_response(results, status=HTTP_200_OK, headers=None,
                          first_answer=False):#pylint:disable=unused-argument
        return http.Response(results, status=status, headers=headers)

    def get_queryset(self):
        return self.get_candidates()

    @swagger_auto_schema(responses={
        200: OpenAPIResponse("Create successful", SampleAnswerSerializer, many=True)})
    def post(self, request, *args, **kwargs):
        """
        Uses candidate measurements for a sample

        The list returned contains at least one answer for each question
        in the campaign. If there are no answer yet on a question, ``measured``
        will be null.

        There might be more than one answer per question as long as there are
        no duplicated ``unit`` per question. For example, to the question
        ``adjust-air-fuel-ratio``, there could be an answer with unit
        ``assessment`` (Mostly Yes/ Yes / No / Mostly No) and an answer with
        unit ``freetext`` (i.e. a comment).

        The ``sample`` must belong to ``organization``.

        ``path`` can be used to filter the tree of questions by a prefix.

        **Tags**: assessments

        **Examples**

        .. code-block:: http

             POST /api/supplier-1/sample/46f66f70f5ad41b29c4df08f683a9a7a\
/candidates/construction HTTP/1.1

        .. code-block:: json

        {}

        responds

        .. code-block:: json

        {
            "count": 3,
            "previous": null,
            "next": null,
            "results": [
                {
                    "question": {
                        "path": "/construction/governance/the-assessment\
-process-is-rigorous",
                        "title": "The assessment process is rigorous",
                        "default_unit": {
                            "slug": "assessment",
                            "title": "assessments",
                            "system": "enum",
                            "choices": [
                            {
                                "rank": 1,
                                "text": "mostly-yes",
                                "descr": "Mostly yes"
                            },
                            {
                                "rank": 2,
                                "text": "yes",
                                "descr": "Yes"
                            },
                            {
                                "rank": 3,
                                "text": "no",
                                "descr": "No"
                            },
                            {
                                "rank": 4,
                                "text": "mostly-no",
                                "descr": "Mostly no"
                            }
                            ]
                        },
                        "ui_hint": "radio"
                    },
                    "required": true,
                    "measured": "yes",
                    "unit": "assessment",
                    "created_at": "2020-09-28T00:00:00.000000Z",
                    "collected_by": "steve"
                },
                {
                    "question": {
                        "path": "/construction/governance/the-assessment\
-process-is-rigorous",
                        "title": "The assessment process is rigorous",
                        "default_unit": {
                            "slug": "assessment",
                            "title": "assessments",
                            "system": "enum",
                            "choices": [
                            {
                                "rank": 1,
                                "text": "mostly-yes",
                                "descr": "Mostly yes"
                            },
                            {
                                "rank": 2,
                                "text": "yes",
                                "descr": "Yes"
                            },
                            {
                                "rank": 3,
                                "text": "no",
                                "descr": "No"
                            },
                            {
                                "rank": 4,
                                "text": "mostly-no",
                                "descr": "Mostly no"
                            }
                            ]
                        },
                        "ui_hint": "radio"
                    },
                    "measured": "Policy document on the public website",
                    "unit": "freetext",
                    "created_at": "2020-09-28T00:00:00.000000Z",
                    "collected_by": "steve"
                },
                {
                    "question": {
                        "path": "/construction/production/adjust-air-fuel\
-ratio",
                        "title": "Adjust Air fuel ratio",
                        "default_unit": {
                            "slug": "assessment",
                            "title": "assessments",
                            "system": "enum",
                            "choices": [
                            {
                                "rank": 1,
                                "text": "mostly-yes",
                                "descr": "Mostly yes"
                            },
                            {
                                "rank": 2,
                                "text": "yes",
                                "descr": "Yes"
                            },
                            {
                                "rank": 3,
                                "text": "no",
                                "descr": "No"
                            },
                            {
                                "rank": 4,
                                "text": "mostly-no",
                                "descr": "Mostly no"
                            }
                            ]
                        },
                        "ui_hint": "radio"
                    },
                    "required": true,
                    "measured": null,
                    "unit": null
                }
             ]
        }
        """
        #pylint:disable=useless-super-delegation
        return super(SampleCandidatesAPIView, self).post(
            request, *args, **kwargs)


class SampleFreezeAPIView(SampleMixin, generics.CreateAPIView):
    """
    Freezes a sample of measurements

    The ``sample`` must belong to ``organization``.

    ``path`` can be used to filter the tree of questions by a prefix.

    **Tags**: assessments

    **Examples**

    .. code-block:: http

        POST /api/supplier-1/sample/46f66f70f5ad41b29c4df08f683a9a7a/freeze\
/construction HTTP/1.1

    .. code-block:: json

        {}

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
    Resets measurements in a sample

    The ``sample`` must belong to ``organization``.

    ``path`` can be used to filter the tree of questions by a prefix.

    **Tags**: assessments

    **Examples**

    .. code-block:: http

        POST /api/supplier-1/sample/46f66f70f5ad41b29c4df08f683a9a7a/reset\
/construction HTTP/1.1

    .. code-block:: json

        {}

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
        prefix = self.path
        if prefix:
            queryset = self.sample.answers.filter(
                question__path__startswith=prefix)
        else:
            queryset = self.sample.answers.all()
        unit_slug = request.query_params.get('unit')
        if unit_slug:
            queryset = queryset.filter(unit__slug=unit_slug)
        queryset.delete()
        serializer = self.get_serializer(instance=self.sample)
        headers = self.get_success_headers(serializer.data)
        return http.Response(serializer.data, status=HTTP_201_CREATED,
            headers=headers)


class SampleRecentCreateAPIView(AccountMixin, generics.ListCreateAPIView):
    """
    Lists updatable samples

    This API end-point returns all samples which have not been frozen
    for an account.

    **Tags**: assessments

    **Examples**

    .. code-block:: http

        GET /api/supplier-1/sample HTTP/1.1

    responds

    .. code-block:: json

        {
            "count": 1,
            "previous": null,
            "next": null,
            "results": [
            {
                "slug": "46f66f70f5ad41b29c4df08f683a9a7a",
                "created_at": "2018-01-24T17:03:34.926193Z",
                "campaign": "best-practices",
                "is_frozen": false,
                "extra": null
            }
            ]
        }
    """
    serializer_class = SampleSerializer

    def get_queryset(self):
        return Sample.objects.filter(
            account=self.account, is_frozen=False).order_by('-created_at')

    @swagger_auto_schema(request_body=SampleCreateSerializer)
    def post(self, request, *args, **kwargs):
        """
        Creates a new sample

        **Tags**: assessments

        **Examples**

        .. code-block:: http

            POST /api/supplier-1/sample HTTP/1.1

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
