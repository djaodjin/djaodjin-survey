# Copyright (c) 2023, DjaoDjin inc.
# see LICENSE.
"""
This file contains SQL statements as building blocks for benchmarking
results in APIs, downloads, etc.
"""
import datetime

from django.apps import apps as django_apps
from django.core.exceptions import ImproperlyConfigured
from django.db import connections
from django.db.utils import DEFAULT_DB_ALIAS
from django.db.models.query import QuerySet, RawQuerySet
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.timezone import utc

from . import settings
from .compat import six

def as_sql_date_trunc(field_name, db_key=None, period='yearly'):
    if period == 'monthly':
        return as_sql_date_trunc_month(field_name, db_key=db_key)
    return as_sql_date_trunc_year(field_name, db_key=db_key)


def as_sql_date_trunc_month(field_name, db_key=None):
    if is_sqlite3(db_key):
        return "strftime('%%Y-%%M', %s)" % field_name
    return "date_trunc('month', %s)" % field_name


def as_sql_date_trunc_year(field_name, db_key=None):
    if is_sqlite3(db_key):
        return "strftime('%%Y', %s)" % field_name
    return "date_trunc('year', %s)" % field_name


def datetime_or_now(dtime_at=None):
    as_datetime = dtime_at
    if isinstance(dtime_at, six.string_types):
        as_datetime = parse_datetime(dtime_at)
        if not as_datetime:
            as_date = parse_date(dtime_at)
            if as_date:
                as_datetime = datetime.datetime.combine(
                    as_date, datetime.time.min)
    if not as_datetime:
        as_datetime = datetime.datetime.utcnow().replace(tzinfo=utc)
    if as_datetime.tzinfo is None:
        as_datetime = as_datetime.replace(tzinfo=utc)
    return as_datetime


def is_sqlite3(db_key=None):
    if db_key is None:
        db_key = DEFAULT_DB_ALIAS
    return connections.databases[db_key]['ENGINE'].endswith('sqlite3')


def get_account_model():
    """
    Returns the ``Account`` model that is active in this project.
    """
    try:
        return django_apps.get_model(settings.ACCOUNT_MODEL)
    except ValueError:
        raise ImproperlyConfigured(
            "ACCOUNT_MODEL must be of the form 'app_label.model_name'")
    except LookupError:
        raise ImproperlyConfigured("ACCOUNT_MODEL refers to model '%s'"\
" that has not been installed" % settings.ACCOUNT_MODEL)


def get_question_model():
    """
    Returns the ``Question`` model that is active in this project.
    """
    try:
        return django_apps.get_model(settings.QUESTION_MODEL)
    except ValueError:
        raise ImproperlyConfigured(
            "QUESTION_MODEL must be of the form 'app_label.model_name'")
    except LookupError:
        raise ImproperlyConfigured("QUESTION_MODEL refers to model '%s'"\
" that has not been installed" % settings.QUESTION_MODEL)


def sql_latest_frozen_by_accounts(campaign=None,
                                  start_at=None, ends_at=None,
                                  tags=None, pks_only=False):
    """
    Returns the most recent frozen sample in an optionally specified
    date range, indexed by account.

    The returned queryset can be further filtered by a campaign and
    a set of tags.
    """
    #pylint:disable=too-many-arguments
    campaign_clause = ""
    if campaign:
        campaign_clause = (
            "AND survey_sample.campaign_id = %(campaign_id)d" % {
                'campaign_id': campaign.pk})
    date_range_clause = ""
    if start_at:
        date_range_clause = (" AND survey_sample.created_at >= '%s'" %
            start_at.isoformat())
    if ends_at:
        date_range_clause += (" AND survey_sample.created_at < '%s'" %
            ends_at.isoformat())
    extra_clause = ""
    if tags is not None:
        if tags:
            extra_clause = "".join([
                "AND LOWER(survey_sample.extra) LIKE '%%%s%%'" %
                tag.lower() for tag in tags])
        else:
            extra_clause = "AND survey_sample.extra IS NULL"
    if pks_only:
        values = 'survey_sample.id'
    else:
        values = 'survey_sample.*'

    sql_query = """SELECT
    %(values)s
FROM survey_sample
INNER JOIN (
    SELECT
        account_id,
        campaign_id,
        MAX(created_at) AS last_updated_at
    FROM survey_sample
    WHERE survey_sample.is_frozen
          %(campaign_clause)s
          %(date_range_clause)s
          %(extra_clause)s
    GROUP BY account_id, campaign_id) AS last_updates
ON survey_sample.account_id = last_updates.account_id AND
   survey_sample.campaign_id = last_updates.campaign_id AND
   survey_sample.created_at = last_updates.last_updated_at
WHERE survey_sample.is_frozen
      %(campaign_clause)s
ORDER BY survey_sample.created_at DESC
""" % {'values': values,
       'campaign_clause': campaign_clause,
       'date_range_clause': date_range_clause,
       'extra_clause': extra_clause}
    return sql_query


def sql_completed_at_by(campaign, start_at=None, ends_at=None,
                        prefix=None, title="",
                        accounts=None, exclude_accounts=None,
                        extra=None):
    """
    Returns the most recent frozen assessment before an optionally specified
    date, indexed by account. Furthermore the query can be restricted to answers
    on a specific segment using `prefix` and matching text in the `extra` field.

    All accounts in ``excludes`` are not added to the index. This is
    typically used to filter out 'testing' accounts
    """
    #pylint:disable=too-many-arguments,too-many-locals
    sep = " AND "
    additional_filters = ""
    campaign_clause = ""
    if campaign:
        campaign_clause = (
            "AND survey_sample.campaign_id = %(campaign_id)d" % {
                'campaign_id': campaign.pk})
    if accounts:
        if isinstance(accounts, list):
            account_ids = "(%s)" % ','.join([
                str(account_id) for account_id in accounts])
        elif isinstance(accounts, QuerySet):
            account_ids = "(%s)" % ','.join([
                str(account.pk) for account in accounts])
        elif isinstance(accounts, RawQuerySet):
            account_ids = "(%s)" % accounts.query.sql
        additional_filters += (
            "%(sep)ssurvey_sample.account_id IN %(account_ids)s" % {
                'sep': sep, 'account_ids': account_ids})
        sep = " AND "
    if exclude_accounts:
        if isinstance(exclude_accounts, list):
            account_ids = "(%s)" % ','.join([
                str(account_id) for account_id in exclude_accounts])
        additional_filters += (
            "%(sep)ssurvey_sample.account_id NOT IN %(account_ids)s" % {
                'sep': sep, 'account_ids': account_ids})
        sep = " AND "

    if start_at:
        additional_filters += "%ssurvey_sample.created_at >= '%s'" % (
            sep, start_at.isoformat())
        sep = " AND "
    if ends_at:
        additional_filters += "%ssurvey_sample.created_at < '%s'" % (
            sep, ends_at.isoformat())
        sep = " AND "

    if prefix:
        prefix_fields = """,
    '%(segment_prefix)s'%(convert_to_text)s AS segment_path,
    '%(segment_title)s'%(convert_to_text)s AS segment_title""" % {
        'segment_prefix': prefix,
        'segment_title': title,
        'convert_to_text': ("" if is_sqlite3() else "::text")
    }
        prefix_join = (
"""INNER JOIN survey_answer ON survey_answer.sample_id = survey_sample.id
INNER JOIN survey_question ON survey_answer.question_id = survey_question.id""")
        additional_filters += "%ssurvey_question.path LIKE '%s%%%%'" % (
            sep, prefix)
        sep = " AND "
    else:
        prefix_fields = ""
        prefix_join = ""

    extra_clause = sep + ("survey_sample.extra IS NULL" if not extra
        else "survey_sample.extra like '%%%%%s%%%%'" % extra)

    sql_query = """SELECT
    survey_sample.id AS id,
    survey_sample.slug AS slug,
    survey_sample.created_at AS created_at,
    survey_sample.campaign_id AS campaign_id,
    survey_sample.account_id AS account_id,
    survey_sample.updated_at AS updated_at,
    survey_sample.is_frozen AS is_frozen,
    survey_sample.extra AS extra%(prefix_fields)s
FROM survey_sample
INNER JOIN (
    SELECT
        account_id,
        MAX(survey_sample.created_at) AS last_updated_at
    FROM survey_sample
    %(prefix_join)s
    WHERE survey_sample.is_frozen
          %(campaign_clause)s
          %(extra_clause)s
          %(additional_filters)s
    GROUP BY account_id) AS last_updates
ON survey_sample.account_id = last_updates.account_id AND
   survey_sample.created_at = last_updates.last_updated_at
WHERE survey_sample.is_frozen
      %(extra_clause)s
""" % {'campaign_clause': campaign_clause,
       'extra_clause': extra_clause,
       'prefix_fields': prefix_fields,
       'prefix_join': prefix_join,
       'additional_filters': additional_filters}
    return sql_query


def sql_frozen_answers(campaign, samples, prefix=None, excludes=None):
    """
    Returns answers on a set of frozen samples.

    The answers can be filtered such that only questions with a path
    starting by `prefix` are included. Questions included whose
    extra field does not contain `excludes` can be further removed
    from the results.
    """
    sep = ""
    extra_question_clause = ""
    if prefix:
        extra_question_clause += (
            "%(sep)ssurvey_question.path LIKE '%(prefix)s%%%%'\n" % {
                'sep': sep, 'prefix': prefix})
        sep = " AND "
    if excludes:
        extra_question_clause += (
            "%(sep)ssurvey_question.id NOT IN (SELECT id FROM survey_question"\
            " WHERE extra LIKE '%%%%%(extra)s%%%%')\n" % {
                'sep': sep, 'extra': excludes})

    sample_clause = ""
    if samples:
        if isinstance(samples, list):
            sample_sql = ','.join([
                str(sample_id) for sample_id in samples])
        elif isinstance(samples, RawQuerySet):
            sample_sql = "SELECT id FROM (%s) AS frzsmps" % samples.query.sql
        sample_clause += (
            "sample_id IN (%s)" % sample_sql)

    sep = ""
    campaign_questions_filters = ""
    if campaign:
        campaign_questions_filters += (
            "%(sep)ssurvey_enumeratedquestions.campaign_id = %(campaign_id)d" %
            {'sep': sep, 'campaign_id': campaign.pk})
        sep = " AND "
    if extra_question_clause:
        campaign_questions_filters += sep + extra_question_clause
        sep = " AND "
    if campaign_questions_filters:
        campaign_questions_filters = "WHERE " + campaign_questions_filters

    sep = ""
    additional_filters = ""
    if sample_clause:
        additional_filters += sep + sample_clause
        sep = " AND "
    if extra_question_clause:
        additional_filters += sep + extra_question_clause
        sep = " AND "
    if additional_filters:
        additional_filters  = "WHERE " + additional_filters

    sql_query = """
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
    %(additional_filters)s
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
    %(campaign_questions_filters)s
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
    answers._measured_text AS _measured_text
FROM questions
LEFT OUTER JOIN answers
  ON questions.id = answers.question_id
INNER JOIN survey_sample
  ON answers.sample_id = survey_sample.id
INNER JOIN %(accounts_table)s
  ON survey_sample.account_id = %(accounts_table)s.id
ORDER BY questions.id, %(accounts_table)s.full_name""" % {
      'convert_to_text': ("" if is_sqlite3() else "::text"),
      'campaign_questions_filters': campaign_questions_filters,
      'additional_filters': additional_filters,
      'accounts_table': get_account_model()._meta.db_table,
  }
    return sql_query
