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

import copy, decimal, logging
from collections import OrderedDict

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F, Q, Max
from django.db.utils import DataError
from rest_framework import generics, mixins
from rest_framework import response as http
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.status import HTTP_200_OK, HTTP_201_CREATED

from .. import settings
from ..compat import six, is_authenticated, gettext_lazy as _
from ..docs import OpenApiResponse, extend_schema
from ..filters import DateRangeFilter, OrderingFilter, SampleStateFilter
from ..helpers import datetime_or_now, extra_as_internal
from ..mixins import AccountMixin, SampleMixin
from ..models import (Answer, AnswerCollected, Choice, Portfolio, Sample, Unit,
    UnitEquivalences)
from ..queries import is_sqlite3
from ..utils import get_question_model, get_user_serializer
from .base import QuestionListAPIView
from .serializers import (AnswerSerializer, NoModelSerializer,
    QueryParamForceSerializer, SampleAnswerSerializer, SampleCreateSerializer,
    SampleSerializer)


LOGGER = logging.getLogger(__name__)


def attach_answers(units, questions_by_key, queryset,
                   extra_fields=None, key='answers'):
    """
    Populates `units` and `questions_by_key` from a `queryset` of answers.
    """
    #pylint:disable=too-many-locals
    if extra_fields is None:
        extra_fields = []
    enum_units = {}
    for resp in queryset:
        # First we gather all information required
        # to display the question properly.
        question = resp.question
        path = question.path
        question_pk = question.pk
        value = questions_by_key.get(question_pk)
        if not value:
            default_unit = question.default_unit
            units.update({default_unit.slug: default_unit})
            if default_unit.system == Unit.SYSTEM_ENUMERATED:
                # Enum units might have a per-question choice description.
                # We try to reduce the number of database queries by
                # loading the unit choices here and the per-question choices
                # in a single pass later on.
                default_unit_dict = enum_units.get(default_unit.pk)
                if not default_unit_dict:
                    default_unit_dict = {
                        'slug': default_unit.slug,
                        'title': default_unit.title,
                    'system': default_unit.system,
                        'choices':[{
                            'pk': choice.pk,
                            'text': choice.text,
                    'descr': choice.descr if choice.descr else choice.text
                        } for choice in default_unit.choices]}
                    enum_units[default_unit.pk] = default_unit_dict
                default_unit = copy.deepcopy(default_unit_dict)
            value = {
                'path': path,
                'rank': resp.rank,
                'frozen': bool(getattr(resp, 'frozen', False)),
                'required': (
                    resp.required if hasattr(resp, 'required') else True),
                'default_unit': default_unit,
                'ui_hint': question.ui_hint,
            }
            for field_name in extra_fields:
                value.update({field_name: getattr(question, field_name)})
            questions_by_key.update({question_pk: value})
        if resp.pk:
            # We have an actual answer to the question,
            # so let's populate it.
            answers = value.get(key, [])
            answers += [{
                'measured': resp.measured_text,
                'unit': resp.unit,
                'created_at': resp.created_at,
                'collected_by': resp.collected_by,
            }]
            units.update({resp.unit.slug: resp.unit})
            if key not in value:
                value.update({key: answers})
    # We re-order the answers so the default_unit (i.e. primary)
    # is first.
    for question in six.itervalues(questions_by_key):
        default_unit = question.get('default_unit')
        if isinstance(default_unit, Unit):
            default_units = [default_unit.slug]
            if default_unit.system in Unit.NUMERICAL_SYSTEMS:
                equiv_qs = UnitEquivalences.objects.filter(
                    source__slug=default_unit.slug).values_list(
                    'target__slug', flat=True)
                default_units += list(equiv_qs)
        else:
            default_units = [default_unit.get('slug')]
        primary = []
        remainders = []
        for answer in question.get(key, []):
            if str(answer.get('unit')) in default_units:
                primary = [answer]
            else:
                remainders += [answer]
        question.update({key: primary + remainders})

    # Let's populate the per-question choices as necessary.
    # This is done in a single pass to reduce the number of db queries.
    for choice in Choice.objects.filter(
            question__in=questions_by_key,
            unit=F('question__default_unit')).order_by(
                'question', 'unit', 'rank'):
        default_unit = questions_by_key[choice.question_id].get(
            'default_unit')
        for default_unit_choice in default_unit.get('choices'):
            if choice.text == default_unit_choice.get('text'):
                default_unit_choice.update({'descr': choice.descr})
                break


def update_or_create_answer(datapoint, question, sample, created_at,
                            collected_by=None):
    """
    Encodes and persists a `datapoint` for an account (i.e. `sample.account`)
    to `question`, collected at date/time `created_at`, in the database.

    `collected_by`, the ``User`` that updates or creates the record
    in the database is optional.

    A datapoint is a dictionnary. Example:
    {
      "measured": 12,
      "unit": "kg"
    }

    `question` and `sample` are models, i.e. ``Question`` and ``Sample``
    respectively.

    When storing a datapoint in a numerical system unit (SI, customary, and
    rank), there can be overflow, or the unit might not match
    the `question.default_unit`.
    """
    answer = None
    created = False
    measured = datapoint.get('measured', None)
    unit = datapoint.get('unit', question.default_unit)
    LOGGER.debug("%s %s [%s]", measured, unit, measured.__class__)
    measured_collected = None
    unit_collected = None
    try:
        with transaction.atomic():
            if unit.system in Unit.NUMERICAL_SYSTEMS:
                # 1. We make sure the collected measure is a number
                try:
                    try:
                        # In Python 3, the plain `int` type is unbounded.
                        measured = int(measured)
                    except ValueError:
                        measured = decimal.Decimal(measured)
                except (ValueError, decimal.InvalidOperation, DataError):
                    raise ValidationError(
                        _("'%(measured)s' is not a number.") % {
                        'measured': measured})

                # 2. We start tracking collected measure and converted measure
                # separately when the collected unit does not match the question
                # unit.
                if (settings.CONVERT_TO_QUESTION_SYSTEM and
                    unit != question.default_unit):
                    measured_collected = measured
                    unit_collected = unit
                    try:
                        equiv = UnitEquivalences.objects.get(
                            source=unit, target=question.default_unit)
                        measured = equiv.as_target_unit(measured)
                        unit = equiv.target
                    except (UnitEquivalences.DoesNotExist, NotImplementedError):
                        if settings.FORCE_ONLY_QUESTION_UNIT:
                            raise ValidationError(
                            _("'%(measured)s' cannot be converted"\
                              " from %(source_unit)s to %(target_unit)s") % {
                            'measured': measured, 'source_unit': unit_collected,
                            'target_unit': question.default_unit})

                LOGGER.debug("%s %s [%s]", measured, unit, measured.__class__)

                # 2a. If we can store the collected measure without
                # lose of precision in the question unit, let's do that.
                # (ex: 8,000g to kg)
                # XXX 2a.i. If we would loose precision, store in collected
                # unit?
                if (not settings.FORCE_ONLY_QUESTION_UNIT and
                    settings.DENORMALIZE_FOR_PRECISION and
                    round(measured) != measured):
                    for equiv in UnitEquivalences.objects.filter(
                        source=question.default_unit, factor=1,
                        scale__gt=1).order_by('scale'):
                        measured_target = round(equiv.as_target_unit(measured))
                        measured_source = equiv.as_source_unit(measured_target)
                        LOGGER.debug("%s %s [%s] *", measured_target,
                            equiv.target, measured_target.__class__)
                        if float(measured) == measured_source:
                            # No loss of precision
                            measured_scaled = measured
                            unit_scaled = unit
                            measured = measured_target
                            unit = equiv.target
                            break

                LOGGER.debug("%s %s [%s]", measured, unit, measured.__class__)

                # 3. When the converted measure rounded to the closest
                # integer fits the database number of bits for an integer,
                # there is nothing to do.
                # In Python 3, the plain `int` type is unbounded.
                # In case of an overflow, we might be able to use
                # a unit that only differs by the scale, and not loose
                # any precision (ex: 1000kg to 1t) so we start tracking
                # the scaled-up version.
                if (not settings.FORCE_ONLY_QUESTION_UNIT and
                    settings.DENORMALIZE_FOR_PRECISION and
                    measured >= Answer.MEASURED_MAX_VALUE):
                    for equiv in UnitEquivalences.objects.filter(
                            source=unit, factor=1,
                            scale__lt=1).order_by('-scale'):
                        measured_target = equiv.as_target_unit(measured)
                        LOGGER.debug("%s %s [%s] *", measured_target,
                            equiv.target, measured_target.__class__)
                        if measured_target < Answer.MEASURED_MAX_VALUE:
                            measured_scaled = measured
                            unit_scaled = unit
                            measured = measured_target
                            unit = equiv.target
                            break

                LOGGER.debug("%s %s [%s]", measured, unit, measured.__class__)

                # We are only storing integers in the database
                # Implementation Note: In Python 3, the plain `int` type is
                # unbounded therefore there will be no overflow when rounded
                # up. If we move this statement after the check for overflow,
                # we might pass the check and round up afterwards, creating
                # an overflow.
                measured = round(measured)

                LOGGER.debug("%s %s [%s]", measured, unit, measured.__class__)

                if measured >= Answer.MEASURED_MAX_VALUE:
                    if measured_collected and unit_collected:
                        raise ValidationError(
                        _("overflow encoding '%(measured)s%(unit)s'.") % {
                        'measured': measured_collected,
                        'unit': unit_collected})
                    raise ValidationError(
                        _("overflow encoding '%(measured)s' in %(unit)s.") % {
                        'measured': measured, 'unit': unit})

                # Stores only one Answer with equivalent unit per Sample.
                Answer.objects.filter(Q(unit=unit) |
                    Q(unit__in=UnitEquivalences.objects.filter(
                        target=unit).values('source')),
                    sample=sample, question=question).delete()

            if unit.system not in Unit.NUMERICAL_SYSTEMS:
                if unit.system == Unit.SYSTEM_ENUMERATED:
                    try:
                        measured = Choice.objects.get(question__isnull=True,
                            unit=unit, text=measured).pk
                    except Choice.DoesNotExist:
                        choices = Choice.objects.filter(question__isnull=True,
                            unit=unit)
                        raise ValidationError(_("'%s' is not a valid choice."\
                            " Expected one of %s.") % (measured,
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

            # Create or update the answer
            answer, created = Answer.objects.update_or_create(
                sample=sample, question=question, unit=unit,
                defaults={
                    'measured': measured,
                    'created_at': created_at,
                    'collected_by': collected_by})
            if sample and sample.updated_at != created_at:
                sample.updated_at = created_at
                sample.save()

            if measured_collected:
                # We have converted the datapoint collected from the user
                # into one with a unit whose system is identical to the
                # question.default_unit.
                # We store the collected datapoint for reference.
                AnswerCollected.objects.update_or_create(
                        collected=measured_collected,
                        answer=answer,
                        unit=unit_collected)

    except DataError as err:
        LOGGER.exception(err)
        raise ValidationError(
            _("\"%(measured)s\": %(err)s for '%(unit)s'") % {
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
            "unit": "t"
        }
    """
    serializer_class = AnswerSerializer
    lookup_rank_kwarg = 'rank'

    @property
    def unit(self):
        #pylint:disable=attribute-defined-outside-init
        if not hasattr(self, '_unit'):
            self._unit = self.question.default_unit
        return self._unit

    @property
    def question(self):
        #pylint:disable=attribute-defined-outside-init
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

    Returns top level information about a sample.

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
        "campaign": {
            "slug": "sustainability",
            "title": "ESG/Environmental practices"
        }
    }
    """
    serializer_class = SampleSerializer

    def get_object(self):
        return self.sample


class SampleAnswersMixin(SampleMixin):

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
        survey_answer.measured%(convert_to_text)s) AS _measured_text
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
    answers._measured_text AS _measured_text,
    1 AS frozen
FROM questions
LEFT OUTER JOIN answers
  ON questions.id = answers.question_id
ORDER BY answers.created_at, answers.id""" % {
      'campaign': sample.campaign.pk,
      'convert_to_text': ("" if is_sqlite3() else "::text"),
      'extra_question_clause': extra_question_clause,
      'prefix': prefix,
      'sample': sample.pk
  }
        else: # `not sample.is_frozen`
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
        survey_answer.measured%(convert_to_text)s) AS _measured_text
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
    answers._measured_text AS _measured_text,
    0 AS frozen
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

    def get_questions_by_key(self, prefix=None, initial=None):
        """
        Returns a dictionnary of questions indexed by `pk` populated
        with an 'answers' field.
        """
        extra_fields = getattr(self.serializer_class.Meta, 'extra_fields', [])
        units = {}
        questions_by_key = initial if isinstance(initial, dict) else {}
        attach_answers(
            units,
            questions_by_key,
            self.get_answers(prefix=prefix, sample=self.sample),
            extra_fields=extra_fields)

        return questions_by_key


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
              content_answers.measured%(convert_to_text)s) AS _measured_text
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
          candidate_answers._measured_text AS _measured_text
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


    def get_questions_by_key(self, prefix=None, initial=None):
        """
        Returns a dictionnary of questions indexed by `pk` populated
        with an 'answers' field (and optionally a 'candidates' field).
        """
        extra_fields = getattr(self.serializer_class.Meta, 'extra_fields', [])
        units = {}
        questions_by_key = initial if isinstance(initial, dict) else {}
        attach_answers(
            units,
            questions_by_key,
            self.get_candidates(prefix=prefix),
            extra_fields=extra_fields,
            key='candidates')

        return questions_by_key


class SampleAnswersAPIView(SampleAnswersMixin, mixins.CreateModelMixin,
                           QuestionListAPIView):
    """
    Lists answers for a subset of questions

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
        "results": [{
            "path": "/construction/governance/the-assessment\
-process-is-rigorous",
            "title": "The assessment process is rigorous",
            "default_unit": {
                "slug": "assessment",
                "title": "assessments",
                "system": "enum",
                "choices": [{
                    "rank": 1,
                    "text": "mostly-yes",
                    "descr": "Mostly yes"
                }, {
                    "rank": 2,
                    "text": "yes",
                    "descr": "Yes"
                }, {
                    "rank": 3,
                    "text": "no",
                    "descr": "No"
                }, {
                    "rank": 4,
                    "text": "mostly-no",
                    "descr": "Mostly no"
                }]
            },
            "ui_hint": "radio",
            "required": true,
            "answers": [{
                "measured": "yes",
                "unit": "assessment",
                "created_at": "2020-09-28T00:00:00.000000Z",
                "collected_by": "steve"
            }]
        }, {
            "path": "/construction/governance/the-assessment\
-process-is-rigorous",
            "title": "The assessment process is rigorous",
            "default_unit": {
                "slug": "assessment",
                "title": "assessments",
                "system": "enum",
                "choices": [{
                    "rank": 1,
                    "text": "mostly-yes",
                    "descr": "Mostly yes"
                }, {
                    "rank": 2,
                    "text": "yes",
                    "descr": "Yes"
                }, {
                    "rank": 3,
                    "text": "no",
                    "descr": "No"
                }, {
                    "rank": 4,
                    "text": "mostly-no",
                    "descr": "Mostly no"
                }]
            },
            "ui_hint": "radio",
            "required": true,
            "answers": [{
                "measured": "Policy document on the public website",
                "unit": "freetext",
                "created_at": "2020-09-28T00:00:00.000000Z",
                "collected_by": "steve"
            }]
        }, {
            "path": "/construction/production/adjust-air-fuel-ratio",
            "title": "Adjust Air fuel ratio",
            "default_unit": {
                "slug": "assessment",
                "title": "assessments",
                "system": "enum",
                "choices": [{
                    "rank": 1,
                    "text": "mostly-yes",
                    "descr": "Mostly yes"
                }, {
                    "rank": 2,
                    "text": "yes",
                    "descr": "Yes"
                }, {
                    "rank": 3,
                    "text": "no",
                    "descr": "No"
                }, {
                    "rank": 4,
                    "text": "mostly-no",
                    "descr": "Mostly no"
                }]
            },
            "ui_hint": "radio",
            "required": true,
            "answers": []
         }]
    }
    """
    serializer_class = SampleAnswerSerializer

    # Used to POST and create an answer.
    @property
    def question(self):
        #pylint:disable=attribute-defined-outside-init
        if not hasattr(self, '_question'):
            self._question = get_object_or_404(
                get_question_model().objects.all(), path=self.path)
        return self._question


    def get_serializer_class(self):
        if self.request.method.lower() == 'post':
            return AnswerSerializer
        return super(SampleAnswersAPIView, self).get_serializer_class()


    def get_serializer(self, *args, **kwargs):
        try:
            if isinstance(self.request.data, list):
                kwargs.update({'many': True})
        except AttributeError:
            pass
        return super(SampleAnswersAPIView, self).get_serializer(
            *args, **kwargs)


    def post(self, request, *args, **kwargs):
        """
        Updates an answer

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

            POST /api/supplier-1/sample/4c6675a5d5af46c796b8033a7731a86e/\
answers/code-of-conduct HTTP/1.1

        .. code-block:: json

            {
               "measured": "Yes"
            }

        responds

        .. code-block:: json

            {
                "created_at": "2020-09-28T00:00:00.000000Z",
                "collected_by": "steve",
                "measured": "Yes",
                "unit": "yes-no"
            }
        """
        return self.create(request, *args, **kwargs)

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
            raise ValidationError({
                'detail': _("cannot update answers in a frozen sample")})

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
                errors += err.detail
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


class SampleAnswersIndexAPIView(SampleAnswersAPIView):
    """
    Lists answers

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

         GET /api/supplier-1/sample/46f66f70f5ad41b29c4df08f683a9a7a/answers HTTP/1.1

    responds

    .. code-block:: json

    {
        "count": 3,
        "previous": null,
        "next": null,
        "results": [{
            "path": "/construction/governance/the-assessment\
-process-is-rigorous",
            "title": "The assessment process is rigorous",
            "default_unit": {
                "slug": "assessment",
                "title": "assessments",
                "system": "enum",
                "choices": [{
                    "rank": 1,
                    "text": "mostly-yes",
                    "descr": "Mostly yes"
                }, {
                    "rank": 2,
                    "text": "yes",
                    "descr": "Yes"
                }, {
                    "rank": 3,
                    "text": "no",
                    "descr": "No"
                }, {
                    "rank": 4,
                    "text": "mostly-no",
                    "descr": "Mostly no"
                }]
            },
            "ui_hint": "radio",
            "required": true,
            "answers": [{
                "measured": "yes",
                "unit": "assessment",
                "created_at": "2020-09-28T00:00:00.000000Z",
                "collected_by": "steve"
            }]
        }, {
            "path": "/construction/governance/the-assessment\
-process-is-rigorous",
            "title": "The assessment process is rigorous",
            "default_unit": {
                "slug": "assessment",
                "title": "assessments",
                "system": "enum",
                "choices": [{
                    "rank": 1,
                    "text": "mostly-yes",
                    "descr": "Mostly yes"
                }, {
                    "rank": 2,
                    "text": "yes",
                    "descr": "Yes"
                }, {
                    "rank": 3,
                    "text": "no",
                    "descr": "No"
                }, {
                    "rank": 4,
                    "text": "mostly-no",
                    "descr": "Mostly no"
                }]
            },
            "ui_hint": "radio",
            "required": true,
            "answers": [{
                "measured": "Policy document on the public website",
                "unit": "freetext",
                "created_at": "2020-09-28T00:00:00.000000Z",
                "collected_by": "steve"
            }]
        }, {
            "path": "/construction/production/adjust-air-fuel-ratio",
            "title": "Adjust Air fuel ratio",
            "default_unit": {
                "slug": "assessment",
                "title": "assessments",
                "system": "enum",
                "choices": [{
                    "rank": 1,
                    "text": "mostly-yes",
                    "descr": "Mostly yes"
                }, {
                    "rank": 2,
                    "text": "yes",
                    "descr": "Yes"
                }, {
                    "rank": 3,
                    "text": "no",
                    "descr": "No"
                }, {
                    "rank": 4,
                    "text": "mostly-no",
                    "descr": "Mostly no"
                }]
            },
            "ui_hint": "radio",
            "required": true,
            "answers": []
         }]
    }
    """
    http_method_names = ['get', 'head', 'options']

    @extend_schema(operation_id='sample_answers_retrieve_index')
    def get(self, request, *args, **kwargs):
        return super(SampleAnswersIndexAPIView, self).get(
            request, *args, **kwargs)


class SampleCandidatesAPIView(SampleCandidatesMixin, SampleAnswersMixin,
                              mixins.CreateModelMixin, QuestionListAPIView):
    """
    Lists candidate answers for a subset of questions

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
        "count": 2,
        "previous": null,
        "next": null,
        "results": [{
            "path": "/construction/governance/the-assessment\
-process-is-rigorous",
            "title": "The assessment process is rigorous",
            "default_unit": {
                "slug": "assessment",
                "title": "assessments",
                "system": "enum",
                "choices": [{
                    "rank": 1,
                    "text": "mostly-yes",
                    "descr": "Mostly yes"
                }, {
                    "rank": 2,
                    "text": "yes",
                    "descr": "Yes"
                }, {
                    "rank": 3,
                    "text": "no",
                    "descr": "No"
                }, {
                    "rank": 4,
                    "text": "mostly-no",
                    "descr": "Mostly no"
                }]
            },
            "ui_hint": "radio",
            "required": true,
            "candidates": [{
                "measured": "yes",
                "unit": "assessment",
                "created_at": "2020-09-28T00:00:00.000000Z",
                "collected_by": "steve"
            }]
        }, {
            "path": "/construction/production/adjust-air-fuel-ratio",
            "title": "Adjust Air fuel ratio",
            "default_unit": {
                "slug": "assessment",
                "title": "assessments",
                "system": "enum",
                "choices": [{
                    "rank": 1,
                    "text": "mostly-yes",
                    "descr": "Mostly yes"
                }, {
                    "rank": 2,
                    "text": "yes",
                    "descr": "Yes"
                }, {
                    "rank": 3,
                    "text": "no",
                    "descr": "No"
                }, {
                    "rank": 4,
                    "text": "mostly-no",
                    "descr": "Mostly no"
                }]
            },
            "ui_hint": "radio",
            "candidates": []
        }]
    }
    """
    serializer_class = SampleAnswerSerializer

    def get_serializer_class(self):
        if self.request.method.lower() == 'post':
            return NoModelSerializer
        return super(SampleCandidatesAPIView, self).get_serializer_class()

    def create(self, request, *args, **kwargs):
        #pylint:disable=too-many-locals
        if self.sample.is_frozen:
            raise ValidationError({
                'detail': "cannot update answers in a frozen sample"})

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
                    'extra': extra_as_internal(question.content),
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


    @extend_schema(responses={
        201: OpenApiResponse(SampleAnswerSerializer(many=True))})
    def post(self, request, *args, **kwargs):
        """
        Uses candidate answers

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
        return self.create(request, *args, **kwargs)


class SampleCandidatesIndexAPIView(SampleCandidatesAPIView):
    """
    Lists candidate answers

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

         GET /api/supplier-1/sample/46f66f70f5ad41b29c4df08f683a9a7a/candidates HTTP/1.1

    responds

    .. code-block:: json

    {
        "count": 2,
        "previous": null,
        "next": null,
        "results": [{
            "path": "/construction/governance/the-assessment\
-process-is-rigorous",
            "title": "The assessment process is rigorous",
            "default_unit": {
                "slug": "assessment",
                "title": "assessments",
                "system": "enum",
                "choices": [{
                    "rank": 1,
                    "text": "mostly-yes",
                    "descr": "Mostly yes"
                }, {
                    "rank": 2,
                    "text": "yes",
                    "descr": "Yes"
                }, {
                    "rank": 3,
                    "text": "no",
                    "descr": "No"
                }, {
                    "rank": 4,
                    "text": "mostly-no",
                    "descr": "Mostly no"
                }]
            },
            "ui_hint": "radio",
            "required": true,
            "candidates": [{
                "measured": "yes",
                "unit": "assessment",
                "created_at": "2020-09-28T00:00:00.000000Z",
                "collected_by": "steve"
            }]
        }, {
            "path": "/construction/production/adjust-air-fuel-ratio",
            "title": "Adjust Air fuel ratio",
            "default_unit": {
                "slug": "assessment",
                "title": "assessments",
                "system": "enum",
                "choices": [{
                    "rank": 1,
                    "text": "mostly-yes",
                    "descr": "Mostly yes"
                }, {
                    "rank": 2,
                    "text": "yes",
                    "descr": "Yes"
                }, {
                    "rank": 3,
                    "text": "no",
                    "descr": "No"
                }, {
                    "rank": 4,
                    "text": "mostly-no",
                    "descr": "Mostly no"
                }]
            },
            "ui_hint": "radio",
            "candidates": []
        }]
    }
    """
    @extend_schema(operation_id='sample_candidates_index')
    def get(self, request, *args, **kwargs):
        return super(SampleCandidatesIndexAPIView, self).get(
            request, *args, **kwargs)

    @extend_schema(operation_id='sample_candidates_create_index', responses={
        201: OpenApiResponse(SampleAnswerSerializer(many=True))})
    def post(self, request, *args, **kwargs):
        """
        Uses candidate answers for a subset of questions

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
/candidates HTTP/1.1

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
        return super(SampleCandidatesIndexAPIView, self).post(
            request, *args, **kwargs)


class SampleFreezeAPIView(SampleMixin, generics.CreateAPIView):

    serializer_class = SampleSerializer

    @property
    def force(self):
        if not hasattr(self, '_force'):
            query_serializer = QueryParamForceSerializer(
                data=self.request.query_params)
            query_serializer.is_valid(raise_exception=True)
            #pylint:disable=attribute-defined-outside-init
            self._force = query_serializer.validated_data.get('force', False)
        return self._force

    def get_required_unanswered_questions(self, prefixes=None):
        """
        Returns a queryset of questions with a required answer which
        have no answer.
        """
        if not prefixes:
            prefixes = self.get_prefixes()
        filtered_in = None
        #pylint:disable=superfluous-parens
        for prefix in prefixes:
            filtered_q = Q(path__startswith=prefix)
            if filtered_in:
                filtered_in |= filtered_q
            else:
                filtered_in = filtered_q

        answered_questions = get_question_model().objects.filter(
          Q(default_unit_id=F('answer__unit_id')) |
          Q(default_unit__source_equivalences__target_id=F('answer__unit_id')),
            enumeratedquestions__campaign=self.sample.campaign,
            answer__sample=self.sample).distinct()

        if filtered_in:
            queryset = get_question_model().objects.filter(
                filtered_in,
                enumeratedquestions__campaign=self.sample.campaign,
                enumeratedquestions__required=True)
        else:
            queryset = get_question_model().objects.filter(
                enumeratedquestions__campaign=self.sample.campaign,
                enumeratedquestions__required=True)

        return queryset.exclude(pk__in=answered_questions)


    def get_prefixes(self):
        return [self.db_path] if self.db_path else []


    def create(self, request, *args, **kwargs):
        # Basic sanity checks:
        # 1. The sample is not yet frozen.
        # 2. All questions with a required answer have been answered.
        # 3. Unless forced, answers are different from previous frozen sample.
        if self.sample.is_frozen:
            raise ValidationError({'detail': _("sample is already frozen")})

        prefixes = self.get_prefixes()
        if not prefixes:
            raise ValidationError({'detail':
                _("You cannot freeze a sample with no answers")})

        required_unanswered_questions = \
            self.get_required_unanswered_questions(prefixes=prefixes)
        if required_unanswered_questions.exists():
            raise ValidationError({'detail': _("%d questions with a required"\
" answer have yet to be answered.") % required_unanswered_questions.count(),
                'results': list(required_unanswered_questions)})

        if not self.force:
            latest_completed = Sample.objects.filter(
                is_frozen=True,
                campaign=self.sample.campaign,
                extra=self.sample.extra).order_by('created_at').first()
            if latest_completed:
                if self.sample.has_identical_answers(latest_completed):
                    raise ValidationError({'detail': _("This sample contains"\
                    "the same answers has the previously frozen sample.")})

        self.sample.is_frozen = True
        self.sample.save()
        serializer = self.get_serializer(self.sample)
        return http.Response(serializer.data)


    @extend_schema(parameters=[QueryParamForceSerializer], request=None)
    def post(self, request, *args, **kwargs):
        """
        Freezes answers

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
                "campaign": "sustainability",
                "is_frozen": true
            }
        """
        return self.create(request, *args, **kwargs)


class SampleResetAPIView(SampleMixin, generics.CreateAPIView):
    """
    Clears answers for a subset of questions

    Clears answers for ``{sample}`` for which ``{path}`` is a prefix
    of the question's path.

    ``{sample}`` must belong to ``{profile}`` otherwise no action
    is taken and an error is returned.

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
            "campaign": "sustainability"
        }
    """
    serializer_class = SampleSerializer

    @extend_schema(request=None)
    def post(self, request, *args, **kwargs):
        return self.create(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        if self.sample.is_frozen:
            raise ValidationError({
                'detail': "cannot update answers in a frozen sample"})
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


class SampleResetIndexAPIView(SampleResetAPIView):
    """
    Clears answers

    Clears all answers for ``{sample}``.

    ``{sample}`` must belong to ``{profile}`` otherwise no action
    is taken and an error is returned.

    **Tags**: assessments

    **Examples**

    .. code-block:: http

        POST /api/supplier-1/sample/46f66f70f5ad41b29c4df08f683a9a7a/reset\
 HTTP/1.1

    .. code-block:: json

        {}

    responds

    .. code-block:: json

        {
            "slug": "46f66f70f5ad41b29c4df08f683a9a7a",
            "created_at": "2018-01-24T17:03:34.926193Z",
            "campaign": "sustainability"
        }
    """

    @extend_schema(operation_id='sample_reset_create_index', request=None)
    def post(self, request, *args, **kwargs):
        return self.create(request, *args, **kwargs)


class SampleRecentCreateAPIView(AccountMixin, generics.ListCreateAPIView):
    """
    Lists samples

    Returns all samples for a profile

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
                "campaign": "sustainability",
                "is_frozen": false,
                "extra": null
            }
            ]
        }
    """
    search_fields = (
        'is_frozen',
        'campaign',
    )
    alternate_fields = {
        'campaign': 'campaign__slug',
    }
    ordering_fields = (
        ('created_at', 'created_at'),
        ('campaign__title', 'campaign__title'),
        ('is_frozen', 'is_frozen'),
    )

    ordering = ('-created_at',)

    filter_backends = (DateRangeFilter, SampleStateFilter, OrderingFilter)

    serializer_class = SampleSerializer

    def decorate_queryset(self, queryset):
        frozen_by_campaigns = {}
        for sample in queryset:
            if sample.is_frozen:
                if sample.campaign not in frozen_by_campaigns:
                    frozen_by_campaigns[sample.campaign] = [sample]
                else:
                    frozen_by_campaigns[sample.campaign] += [sample]
        for campaign, samples in six.iteritems(frozen_by_campaigns):
            next_level = Portfolio.objects.filter(
                account=self.account, campaign=campaign).values(
                    'ends_at', 'grantee__slug').order_by('-ends_at')
            for sample in sorted(samples,
                        key=lambda smp: smp.created_at, reverse=True):
                sample.grantees = []
                level = next_level
                next_level = []
                for accessible in level:
                    ends_at = accessible.get('ends_at')
                    grantee = accessible.get('grantee__slug')
                    if sample.created_at <= ends_at:
                        sample.grantees += [grantee]
                    else:
                        next_level += [accessible]
        return queryset


    def get_queryset(self):
        return Sample.objects.filter(
            account=self.account,
            extra__isnull=True         # XXX convinience
        ).select_related('campaign')

    def paginate_queryset(self, queryset):
        page = super(
            SampleRecentCreateAPIView, self).paginate_queryset(queryset)
        return self.decorate_queryset(page if page else queryset)

    @extend_schema(request=SampleCreateSerializer)
    def post(self, request, *args, **kwargs):
        """
        Creates a sample

        Creates a new sample to record qualitative and/or quantitative data.

        **Tags**: assessments

        **Examples**

        .. code-block:: http

            POST /api/supplier-1/sample HTTP/1.1

        .. code-block:: json

            {
            }

        responds

        .. code-block:: json

            {
                "slug": "46f66f70f5ad41b29c4df08f683a9a7a",
                "created_at": "2018-01-24T17:03:34.926193Z",
                "campaign": "sustainability"
            }
        """
        #pylint:disable=useless-super-delegation
        return super(SampleRecentCreateAPIView, self).post(
            request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(account=self.account)


class SampleRespondentsAPIView(SampleMixin, generics.ListAPIView):
    """
    Lists respondents for a subset of questions

    The list returned contains the information about the users who answered
    at least one question.

    The {sample} must belong to {organization}.

    {path} can be used to filter the tree of questions by a prefix.

    **Tags**: assessments

    **Examples**

    .. code-block:: http

         GET /api/supplier-1/sample/46f66f70f5ad41b29c4df08f683a9a7a\
/respondents/construction HTTP/1.1

    responds

    .. code-block:: json

    {
        "count": 1,
        "previous": null,
        "next": null,
        "results": [{
            "slug": "steve",
            "full_name": "Steve"
         }]
    }
    """
    serializer_class = get_user_serializer()

    def get_queryset(self):
        kwargs = {}
        if self.path:
            kwargs = {'answer__question__path__startwith': self.path}
        queryset = get_user_model().objects.filter(
            answer__sample=self.sample, **kwargs).distinct()
        return queryset


class SampleRespondentsIndexAPIView(SampleRespondentsAPIView):
    """
    Lists respondents

    The list returned contains the information about the users who answered
    at least one question.

    The {sample} must belong to {organization}.

    {path} can be used to filter the tree of questions by a prefix.

    **Tags**: assessments

    **Examples**

    .. code-block:: http

         GET /api/supplier-1/sample/46f66f70f5ad41b29c4df08f683a9a7a\
/respondents HTTP/1.1

    responds

    .. code-block:: json

    {
        "count": 1,
        "previous": null,
        "next": null,
        "results": [{
            "slug": "steve",
            "full_name": "Steve"
         }]
    }
    """

    @extend_schema(operation_id='sample_respondents_index')
    def get(self, request, *args, **kwargs):
        return super(SampleRespondentsIndexAPIView, self).get(
            request, *args, **kwargs)
