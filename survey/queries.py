# Copyright (c) 2025, DjaoDjin inc.
# see LICENSE.
"""
This file contains SQL statements as building blocks for benchmarking
results in APIs, downloads, etc.
"""
from django.apps import apps as django_apps
from django.core.exceptions import ImproperlyConfigured
from django.db import connections
from django.db.utils import DEFAULT_DB_ALIAS
from django.db.models.query import RawQuerySet

from . import settings
from .helpers import MONTHLY, YEARLY


UNIT_SYSTEM_STANDARD = 0
UNIT_SYSTEM_IMPERIAL = 1
UNIT_SYSTEM_RANK = 2
UNIT_SYSTEM_ENUMERATED = 3
UNIT_SYSTEM_FREETEXT = 4
UNIT_SYSTEM_DATETIME = 5


def as_sql_date_trunc(field_name, db_key=None, period_type=YEARLY):
    if period_type == MONTHLY:
        return as_sql_date_trunc_month(field_name, db_key=db_key)
    return as_sql_date_trunc_year(field_name, db_key=db_key)


def as_sql_date_trunc_month(field_name, db_key=None):
    if is_sqlite3(db_key):
        # We have to return a value that can be converted to a `datetime`
        # by Django `convert_datetimefield_value` function
        return "strftime('%%Y-%%M-01T00:00:00Z', %s)" % field_name
    return "date_trunc('month', %s)" % field_name


def as_sql_date_trunc_year(field_name, db_key=None):
    if is_sqlite3(db_key):
        # We have to return a value that can be converted to a `datetime`
        # by Django `convert_datetimefield_value` function
        return "strftime('%%Y-01-01T00:00:00Z', %s)" % field_name
    return "date_trunc('year', %s)" % field_name


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


def get_content_model():
    """
    Returns the ``Content`` model that is active in this project.
    """
    try:
        return django_apps.get_model(settings.CONTENT_MODEL)
    except ValueError:
        raise ImproperlyConfigured(
            "CONTENT_MODEL must be of the form 'app_label.model_name'")
    except LookupError:
        raise ImproperlyConfigured("CONTENT_MODEL refers to model '%s'"\
" that has not been installed" % settings.CONTENT_MODEL)


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


def sql_has_different_answers(left, right):
    """
    Returns SQL statement to check if there are answers in the `left` sample
    that are not in the `right` sample.
    """
    sql_query = """SELECT second.id FROM survey_answer AS first
LEFT OUTER JOIN survey_answer AS second
ON (first.question_id = second.question_id AND
    first.unit_id = second.unit_id AND
    first.measured = second.measured)
WHERE first.sample_id = %(left_sample_id)d AND
    second.sample_id = %(right_sample_id)d AND
    first.id IS NULL LIMIT 1
""" % {
    'left_sample_id': left.pk,
    'right_sample_id': right.pk
    }
    return sql_query


def get_sample_by_accounts_context(campaign=None,
                                   start_at=None, ends_at=None,
                                   segment_prefix=None, segment_title="",
                                   accounts=None, grantees=None, tags=None):
    #pylint:disable=too-many-arguments,too-many-locals
    primary_filters_clause = ""
    secondary_filters_clause = ""
    prefix_fields = ""
    prefix_join = ""
    if campaign:
        primary_filters_clause = (
            " AND survey_sample.campaign_id = %(campaign_id)d" % {
                'campaign_id': campaign.pk})
    if segment_prefix:
        prefix_fields = """,
    '%(segment_prefix)s'%(convert_to_text)s AS segment_path,
    '%(segment_title)s'%(convert_to_text)s AS segment_title""" % {
        'segment_prefix': segment_prefix,
        'segment_title': segment_title,
        'convert_to_text': ("" if is_sqlite3() else "::text")
    }
        prefix_join = (
"""INNER JOIN survey_answer ON survey_answer.sample_id = survey_sample.id
INNER JOIN survey_question ON survey_answer.question_id = survey_question.id""")
        secondary_filters_clause += (
            " AND survey_question.path LIKE '%(segment_prefix)s%%%%'" % {
                'segment_prefix': str(segment_prefix)})

    if start_at:
        secondary_filters_clause += (
            " AND survey_sample.created_at >= '%(start_at)s'" % {
                'start_at': start_at.isoformat()})
    if ends_at:
        secondary_filters_clause += (
            " AND survey_sample.created_at < '%(ends_at)s'" % {
            'ends_at': ends_at.isoformat()})

    grantees_join = ""
    if grantees:
        grantees_join = """
   INNER JOIN survey_portfolio
     ON survey_portfolio.account_id = survey_sample.account_id"""
        if isinstance(grantees, RawQuerySet):
            # XXX Is comment for account_ids not true here?
            grantee_ids = "%s" % grantees.query.sql
        else:
            grantee_ids = []
            for grantee in grantees:
                try:
                    grantee_ids += [str(grantee.pk)]
                except AttributeError:
                    grantee_ids += [str(grantee)]
            grantee_ids = ','.join(grantee_ids)
        secondary_filters_clause += ("""
   AND survey_sample.created_at < survey_portfolio.ends_at
   AND survey_portfolio.grantee_id IN (%(grantee_ids)s)""" % {
            'grantee_ids': grantee_ids})
        if campaign:
            secondary_filters_clause += ("""
   AND (survey_portfolio.campaign_id = %(campaign_id)s OR
        survey_portfolio.campaign_id IS NULL)""" % {
            'campaign_id': campaign.pk})

    if accounts:
        # In case we have a QuerySet or RawQuerySet, we still
        # cannot use `accounts.query.sql` because `params` are
        # not quoted. don't ask.
        # https://code.djangoproject.com/ticket/25416
        account_ids = []
        for account in accounts:
            try:
                account_ids += [str(account.pk)]
            except AttributeError:
                account_ids += [str(account)]
        account_ids = ','.join(account_ids)
        secondary_filters_clause += (
            " AND survey_sample.account_id IN (%(account_ids)s)" % {
            'account_ids': account_ids})

    if tags is not None:
        if tags:
            primary_filters_clause += "".join([
                " AND LOWER(survey_sample.extra) LIKE '%%%%%s%%%%'" %
                tag.lower() for tag in tags])
        else:
            primary_filters_clause += " AND survey_sample.extra IS NULL"

    return {
       'prefix_fields': prefix_fields,
       'prefix_join': prefix_join,
       'grantees_join': grantees_join,
       'sample_primary_filters_clause': primary_filters_clause,
       'sample_secondary_filters_clause': secondary_filters_clause
    }


def sql_latest_frozen_by_accounts(campaign=None,
                                  start_at=None, ends_at=None,
                                  segment_prefix=None, segment_title="",
                                  accounts=None, grantees=None, tags=None):
    """
    Returns the most recent frozen sample per account

    When `campaign` is specified, it will return the most recent frozen sample
    responding to `campaign` per account. When both `campaign` and
    `segment_prefix` are specified, it will return the most recent frozen
    sample responding to `campaign` which as an answer to question prefixed
    by `segment_prefix` per account.

    When `start_at` and `ends_at` are defined, it will return the most recent
    frozen sample that is also within the [`start_at`, `ends_at`[ date range.

    By default, when `accounts` is not specified, it will return one sample
    per account for all accounts in the database if such sample exists,
    otherwise it will return only samples for specified `accounts`.

    When grantees is specified, it will return the most recent frozen sample
    visible to all `grantees`.

    When `tags` is `None`, the returned queryset will be filtered by sample
    where `extra IS NULL`, otherwise the returned queryset will be samples
    where the extra field contains at least on tag in tags.

    The full template for the SQL query is:

    .. code-block:: sql

    SELECT
        survey_sample.*
        -- prefix_fields
        %(segment_prefix)s AS segment_path,
        %(segment_title)s AS segment_title
    FROM survey_sample
    INNER JOIN (
        SELECT
            survey_sample.account_id,
            survey_sample.campaign_id,
            MAX(survey_sample.created_at) AS last_updated_at
        FROM survey_sample
        -- prefix_join
        INNER JOIN survey_answer
            ON survey_answer.sample_id = survey_sample.id
        INNER JOIN survey_question
            ON survey_answer.question_id = survey_question.id
        -- grantees_join
        INNER JOIN survey_portfolio
            ON survey_portfolio.account_id = survey_sample.account_id
        WHERE survey_sample.is_frozen
              -- primary_filters_clause
              AND survey_sample.campaign_id = %(campaign_id)d
              AND survey_sample.extra IS NULL
              -- secondary_filters_clause
              AND survey_question.path LIKE '%(segment_prefix)s%%%%'
              AND survey_sample.created_at >= '%(start_at)s'
              AND survey_sample.created_at < '%(ends_at)s'
              AND survey_sample.created_at < survey_portfolio.ends_at
              AND survey_portfolio.grantee_id IN (%(grantee_ids)s)
              AND (survey_portfolio.campaign_id = %(campaign_id)s OR
                   survey_portfolio.campaign_id IS NULL)
              AND survey_sample.account_id IN (%(account_ids)s)
        GROUP BY survey_sample.account_id, survey_sample.campaign_id
    ) AS last_updates
    ON survey_sample.account_id = last_updates.account_id AND
       survey_sample.campaign_id = last_updates.campaign_id AND
       survey_sample.created_at = last_updates.last_updated_at
    WHERE survey_sample.is_frozen
        -- primary_filters_clause
        AND survey_sample.campaign_id = %(campaign_id)d
        AND survey_sample.extra IS NULL
    """
    #pylint:disable=too-many-arguments,too-many-locals
    context = get_sample_by_accounts_context(
        campaign=campaign, start_at=start_at, ends_at=ends_at,
        segment_prefix=segment_prefix, segment_title=segment_title,
        accounts=accounts, grantees=grantees, tags=tags)

    sql_query = """SELECT
    survey_sample.*%(prefix_fields)s
FROM survey_sample
INNER JOIN (
    SELECT
        survey_sample.account_id,
        survey_sample.campaign_id,
        MAX(survey_sample.created_at) AS last_updated_at
    FROM survey_sample
    %(prefix_join)s
    %(grantees_join)s
    WHERE survey_sample.is_frozen
          %(sample_primary_filters_clause)s
          %(sample_secondary_filters_clause)s
    GROUP BY survey_sample.account_id, survey_sample.campaign_id
) AS last_updates
ON survey_sample.account_id = last_updates.account_id AND
   survey_sample.campaign_id = last_updates.campaign_id AND
   survey_sample.created_at = last_updates.last_updated_at
WHERE survey_sample.is_frozen
    %(sample_primary_filters_clause)s
""" % context
    # We cannot add an `ORDER BY` clause in the above statement otherwise
    # the query cannot be combined in an `UNION` statement by SQLite3 later on.
    return sql_query


def sql_latest_frozen_by_accounts_by_period(period='yearly', campaign=None,
                                     start_at=None, ends_at=None,
                                     segment_prefix=None, segment_title="",
                                     accounts=None, grantees=None, tags=None):
    #pylint:disable=too-many-arguments,too-many-locals
    context = get_sample_by_accounts_context(
        campaign=campaign, start_at=start_at, ends_at=ends_at,
        segment_prefix=segment_prefix, segment_title=segment_title,
        accounts=accounts, grantees=grantees, tags=tags)
    context.update({
        'as_period': as_sql_date_trunc(
           'survey_sample.created_at', period_type=period)})

    sql_query = """SELECT
    survey_sample.*,
    last_updates.period%(prefix_fields)s
FROM survey_sample
INNER JOIN (
    SELECT
        survey_sample.account_id,
        survey_sample.campaign_id,
        %(as_period)s AS period,
        MAX(survey_sample.created_at) AS last_updated_at
    FROM survey_sample
    %(prefix_join)s
    %(grantees_join)s
    WHERE survey_sample.is_frozen
          %(sample_primary_filters_clause)s
          %(sample_secondary_filters_clause)s
    GROUP BY survey_sample.account_id, survey_sample.campaign_id, period
) AS last_updates
ON survey_sample.account_id = last_updates.account_id AND
   survey_sample.campaign_id = last_updates.campaign_id AND
   survey_sample.created_at = last_updates.last_updated_at
WHERE survey_sample.is_frozen
    %(sample_primary_filters_clause)s
""" % context
    # We cannot add an `ORDER BY` clause in the above statement otherwise
    # the query cannot be combined in an `UNION` statement by SQLite3 later on.
    return sql_query


def sql_latest_frozen_by_portfolios(campaign=None,
                                    start_at=None, ends_at=None,
                                    segment_prefix=None, segment_title="",
                                    accounts=None, grantees=None, tags=None,
                                    reporting_completed_not_shared=10,
                                    reporting_completed=12):
    """
    Returns the most recent frozen sample per account,
    decorated with accessibility status
    """
    #pylint:disable=too-many-arguments,too-many-locals
    accessible_samples_sql_query = sql_latest_frozen_by_accounts(
        campaign=campaign,
        start_at=start_at, ends_at=ends_at,
        segment_prefix=segment_prefix, segment_title=segment_title,
        accounts=accounts, grantees=grantees, tags=tags)

    samples_sql_query = sql_latest_frozen_by_accounts(
        campaign=campaign,
        start_at=start_at, ends_at=ends_at,
        segment_prefix=segment_prefix, segment_title=segment_title,
        accounts=accounts, grantees=None, tags=tags)

    portfolio_grantees_clause = ""
    if grantees:
        grantee_ids = []
        for grantee in grantees:
            try:
                grantee_ids += [str(grantee.pk)]
            except AttributeError:
                grantee_ids += [str(grantee)]
        grantee_ids = ','.join(grantee_ids)
        portfolio_grantees_clause += (
            " AND survey_portfolio.grantee_id IN (%(grantee_ids)s)" % {
                'grantee_ids': grantee_ids})

    context = {}
    context.update({
        'accessible_samples_sql_query': accessible_samples_sql_query,
        'samples_sql_query': samples_sql_query,
        'portfolio_grantees_clause': portfolio_grantees_clause,
        'REPORTING_COMPLETED': reporting_completed,
        'REPORTING_COMPLETED_NOTSHARED': reporting_completed_not_shared
    })

    sql_query = """
WITH accessible_samples AS (
%(accessible_samples_sql_query)s
),
last_completed_by_accounts AS (
%(samples_sql_query)s
)
SELECT DISTINCT
  COALESCE(accessible_samples.id, last_completed_by_accounts.id) AS id,
  COALESCE(accessible_samples.slug, null) AS slug,
  COALESCE(accessible_samples.created_at,
    last_completed_by_accounts.created_at) AS created_at,
  COALESCE(accessible_samples.campaign_id,
    last_completed_by_accounts.campaign_id) AS campaign_id,
  COALESCE(accessible_samples.account_id,
    last_completed_by_accounts.account_id) AS account_id,
  COALESCE(accessible_samples.is_frozen,
    last_completed_by_accounts.is_frozen) AS is_frozen,
  COALESCE(accessible_samples.time_spent, null) AS time_spent,
  COALESCE(accessible_samples.extra, null) AS extra,
  COALESCE(accessible_samples.updated_at,
    last_completed_by_accounts.updated_at) AS updated_at,
  CASE WHEN (accessible_samples.created_at IS NULL OR
    accessible_samples.created_at < last_completed_by_accounts.created_at)
    THEN %(REPORTING_COMPLETED_NOTSHARED)s
    ELSE %(REPORTING_COMPLETED)s END AS state
FROM last_completed_by_accounts
LEFT OUTER JOIN accessible_samples
  ON last_completed_by_accounts.account_id = accessible_samples.account_id
  AND last_completed_by_accounts.campaign_id = accessible_samples.campaign_id
INNER JOIN survey_portfolio
  ON last_completed_by_accounts.account_id = survey_portfolio.account_id
WHERE (survey_portfolio.campaign_id IS NULL OR
  survey_portfolio.campaign_id = last_completed_by_accounts.campaign_id)
  %(portfolio_grantees_clause)s
ORDER BY
  account_id,
  created_at
""" % context
    return sql_query


def sql_latest_frozen_by_portfolios_by_period(period='yearly',
                                    campaign=None, start_at=None, ends_at=None,
                                    segment_prefix=None, segment_title="",
                                    accounts=None, grantees=None, tags=None,
                                    reporting_completed_not_shared=10,
                                    reporting_completed=12):
    """
    Returns the most recent frozen sample per account per period,
    decorated with accessibility status
    """
    #pylint:disable=too-many-arguments,too-many-locals
    accessible_samples_sql_query = sql_latest_frozen_by_accounts_by_period(
        period=period, campaign=campaign,
        start_at=start_at, ends_at=ends_at,
        segment_prefix=segment_prefix, segment_title=segment_title,
        accounts=accounts, grantees=grantees, tags=tags)

    samples_sql_query = sql_latest_frozen_by_accounts_by_period(
        period=period, campaign=campaign,
        start_at=start_at, ends_at=ends_at,
        segment_prefix=segment_prefix, segment_title=segment_title,
        accounts=accounts, grantees=None, tags=tags)

    portfolio_grantees_clause = ""
    if grantees:
        grantee_ids = []
        for grantee in grantees:
            try:
                grantee_ids += [str(grantee.pk)]
            except AttributeError:
                grantee_ids += [str(grantee)]
        grantee_ids = ','.join(grantee_ids)
        portfolio_grantees_clause += (
            " AND survey_portfolio.grantee_id IN (%(grantee_ids)s)" % {
                'grantee_ids': grantee_ids})

    context = {}
    context.update({
        'accessible_samples_sql_query': accessible_samples_sql_query,
        'samples_sql_query': samples_sql_query,
        'portfolio_grantees_clause': portfolio_grantees_clause,
        'REPORTING_COMPLETED': reporting_completed,
        'REPORTING_COMPLETED_NOTSHARED': reporting_completed_not_shared
    })

    sql_query = """
WITH accessible_samples AS (
%(accessible_samples_sql_query)s
),
last_completed_by_accounts AS (
%(samples_sql_query)s
)
SELECT DISTINCT
  COALESCE(accessible_samples.id, last_completed_by_accounts.id) AS id,
  COALESCE(accessible_samples.slug, null) AS slug,
  COALESCE(accessible_samples.created_at,
    last_completed_by_accounts.created_at) AS created_at,
  COALESCE(accessible_samples.campaign_id,
    last_completed_by_accounts.campaign_id) AS campaign_id,
  COALESCE(accessible_samples.account_id,
    last_completed_by_accounts.account_id) AS account_id,
  COALESCE(accessible_samples.is_frozen,
    last_completed_by_accounts.is_frozen) AS is_frozen,
  COALESCE(accessible_samples.time_spent, null) AS time_spent,
  COALESCE(accessible_samples.extra, null) AS extra,
  COALESCE(accessible_samples.updated_at,
    last_completed_by_accounts.updated_at) AS updated_at,
  COALESCE(accessible_samples.period,
    last_completed_by_accounts.period) AS period,
  CASE WHEN (accessible_samples.created_at IS NULL OR
    accessible_samples.created_at < last_completed_by_accounts.created_at)
    THEN %(REPORTING_COMPLETED_NOTSHARED)s
    ELSE %(REPORTING_COMPLETED)s END AS state
FROM last_completed_by_accounts
LEFT OUTER JOIN accessible_samples
  ON last_completed_by_accounts.account_id = accessible_samples.account_id
  AND last_completed_by_accounts.campaign_id = accessible_samples.campaign_id
  AND last_completed_by_accounts.period = accessible_samples.period
INNER JOIN survey_portfolio
  ON last_completed_by_accounts.account_id = survey_portfolio.account_id
WHERE (survey_portfolio.campaign_id IS NULL OR
  survey_portfolio.campaign_id = last_completed_by_accounts.campaign_id)
  %(portfolio_grantees_clause)s
ORDER BY
  account_id,
  created_at
""" % context
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
      survey_enumeratedquestions.required AS required,
      survey_enumeratedquestions.ref_num AS ref_num
    FROM survey_question
      INNER JOIN survey_enumeratedquestions
      ON survey_question.id = survey_enumeratedquestions.question_id
    %(campaign_questions_filters)s
),
-- The following returns all answered questions only.
questions AS (
    SELECT DISTINCT(answers.question_id) AS id,
      COALESCE(campaign_questions.rank, 0) AS rank,
      COALESCE(campaign_questions.required, 'f') AS required,
      COALESCE(campaign_questions.ref_num, '') AS ref_num
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
    questions.ref_num AS ref_num,
    answers._measured_text AS _measured_text
FROM questions
LEFT OUTER JOIN answers
  ON questions.id = answers.question_id
INNER JOIN survey_sample
  ON answers.sample_id = survey_sample.id
INNER JOIN %(accounts_table)s
  ON survey_sample.account_id = %(accounts_table)s.id
ORDER BY questions.id, answers.unit_id, %(accounts_table)s.full_name""" % {
      'convert_to_text': ("" if is_sqlite3() else "::text"),
      'campaign_questions_filters': campaign_questions_filters,
      'additional_filters': additional_filters,
      'accounts_table': get_account_model()._meta.db_table,
  }
    return sql_query


def get_benchmarks_counts(samples, prefix="/", period_type=None,
                          extra_fields=None):
    """
    Returns a SQL statement that aggregates enumerated choices, optionally
    per period ('yearly' or 'monthly'), over a set of `samples`
    for each question that starts with `prefix`.
    """
    samples_sql = ""
    if samples:
        if isinstance(samples, list):
            samples_sql = ','.join([
                str(sample_id) for sample_id in samples])
        elif isinstance(samples, RawQuerySet):
            samples_sql = "SELECT id FROM (%s) AS samples" % samples.query.sql

    group_by_period = ""
    if period_type:
        group_by_period = as_sql_date_trunc('survey_sample.created_at',
            period_type=period_type)

    extra_fields_select = ""
    extra_fields_propagate = ""
    content_table = get_content_model()._meta.db_table
    if extra_fields:
        for field in extra_fields:
            extra_fields_select += (
                "%(content_table)s.%(field)s AS question_%(field)s," % {
                    'content_table': content_table, 'field': field})
            extra_fields_propagate += (
                "question_%(field)s," % {'field': field})

    sql_query = """
WITH answers_by_question_choice AS (
SELECT
  survey_answer.sample_id AS sample_id,
  survey_answer.question_id AS question_id,
  survey_question.path AS question_path,
  %(extra_fields_select)s
  survey_unit.id AS question_default_unit_id,
  survey_unit.slug AS question_default_unit_slug,
  survey_unit.title AS question_default_unit_title,
  survey_unit.system AS question_default_unit_system,
  CASE WHEN survey_unit.system IN (%(enum_systems)s) THEN survey_choice.text
  ELSE 'present' END AS choice
FROM survey_answer
INNER JOIN survey_question
  ON survey_answer.question_id = survey_question.id
INNER JOIN survey_unit
  ON survey_question.default_unit_id = survey_unit.id
INNER JOIN %(content_table)s
  ON survey_question.content_id = %(content_table)s.id
LEFT OUTER JOIN survey_choice
  ON (survey_unit.id = survey_choice.unit_id AND
  survey_choice.id = survey_answer.measured)
WHERE
  survey_question.default_unit_id = survey_answer.unit_id AND
  survey_question.path LIKE '%(prefix)s%%%%' AND
  survey_answer.sample_id IN (%(samples)s)
)
SELECT
  question_id AS id,
  question_path,
  %(extra_fields_propagate)s
  question_default_unit_id,
  question_default_unit_slug,
  question_default_unit_title,
  question_default_unit_system,
  choice,
  %(select_period)s
  COUNT(answers_by_question_choice.sample_id) AS nb_samples
FROM answers_by_question_choice
INNER JOIN survey_sample
  ON answers_by_question_choice.sample_id = survey_sample.id
GROUP BY
 %(group_by_period)s
  question_id,
  question_path,
  %(extra_fields_propagate)s
  question_default_unit_id,
  question_default_unit_slug,
  question_default_unit_title,
  question_default_unit_system,
  choice
ORDER BY question_id ASC,%(group_by_period)s choice ASC;""" % {
    'enum_systems': ",".join([str(system) for system in [
        UNIT_SYSTEM_ENUMERATED, UNIT_SYSTEM_DATETIME]]),
                        # XXX target year are stored as choices
    'prefix': prefix,
    'samples': samples_sql,
    'select_period': (
        "%s AS period," % group_by_period if group_by_period else ""),
    'group_by_period': (
        " %s," % group_by_period if group_by_period else ""),
    'content_table': content_table,
    'extra_fields_select': extra_fields_select,
    'extra_fields_propagate': extra_fields_propagate
    }
    return sql_query
