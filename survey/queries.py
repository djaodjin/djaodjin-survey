# Copyright (c) 2023, DjaoDjin inc.
# see LICENSE.
"""
This file contains SQL statements as building blocks for benchmarking
results in APIs, downloads, etc.
"""
from django.contrib.auth import get_user_model
from django.db.models.query import RawQuerySet

from .models import Answer, Campaign
from .utils import is_sqlite3


def get_frozen_answers(campaign, samples, prefix=None, excludes=None):
    """
    Returns answers on a set of frozen samples.

    The answers can be filtered such that only questions with a path
    starting by `prefix` are included. Questions included whose
    extra field does not contain `excludes` can be further removed
    from the results.
    """
    extra_question_clause = ""
    if prefix:
        extra_question_clause += (
            "AND survey_question.path LIKE '%(prefix)s%%%%'\n" % {
                'prefix': prefix})
    if excludes:
        extra_question_clause += (
            "AND survey_question.id NOT IN (SELECT id FROM survey_question"\
            " WHERE extra LIKE '%%%%%(extra)s%%%%')\n" % {
            'extra': excludes})

    sample_clause = ""
    if samples:
        if isinstance(samples, list):
            sample_sql = ','.join([
                str(sample_id) for sample_id in samples])
        elif isinstance(samples, RawQuerySet):
            sample_sql = "SELECT id FROM (%s) AS frzsmps" % samples.query.sql
        sample_clause += (
            "sample_id IN (%s)" % sample_sql)

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
    WHERE %(sample_clause)s
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
      %(extra_question_clause)s
),
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
      'campaign': campaign.pk,
      'convert_to_text': ("" if is_sqlite3() else "::text"),
      'extra_question_clause': extra_question_clause,
      'sample_clause': sample_clause,
  }
    return Answer.objects.raw(query_text).prefetch_related(
        'unit', 'collected_by', 'question', 'question__content',
        'question__default_unit')


def get_collected_by(campaign, start_at=None, ends_at=None,
                     prefix=None, excludes=None):
    """
    Returns users that have actually responded to a campaign, i.e. updated
    at least one answer in a sample completed in the date range
    [created_at, ends_at[.
    """
    #pylint:disable=too-many-arguments
    kwargs = {}
    if campaign:
        if isinstance(campaign, Campaign):
            kwargs.update({'answer__sample__campaign': campaign})
        else:
            kwargs.update({'answer__sample__campaign__slug': campaign})
    if start_at:
        kwargs.update({
            'answer__created_at__gte': start_at,
            'last_login__gte': start_at,
        })
    if ends_at:
        kwargs.update({'answer__created_at__lt': ends_at})
    if prefix:
        kwargs.update({'answer__question__path__startswith': prefix})
    queryset = get_user_model().objects.filter(
        answer__sample__is_frozen=True,
        **kwargs)

    if excludes:
        queryset = queryset.exclude(answer__question__in=excludes)

    return queryset.distinct()
