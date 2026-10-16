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
"""
This file contains functions useful throughout the whole project which depend
on importing Django models.

See helpers.py for functions useful throughout the whole project which do
not require to import `django` modules.
"""
import logging, re
from importlib import import_module

from django.apps import apps as django_apps
from django.conf import settings as django_settings
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.db.models.functions import Cast
from django.http.request import split_domain_port, validate_host
from rest_framework.exceptions import ValidationError

from . import settings
from .compat import gettext_lazy as _, import_string, six, urlparse, urlunparse
from .models import Answer, PortfolioDoubleOptIn, Unit
#pylint:disable=unused-import
from .queries import (as_sql_jsonb_agg, get_account_model, get_content_model,
    get_question_model)

LOGGER = logging.getLogger(__name__)


def get_grantees_aggregate_set(grantees):
    """
    Returns an extended set of grantees that are selected by affinity
    with `grantees`.
    """
    if isinstance(settings.GRANTEES_AGGREGATE_SET, six.string_types):
        try:
            settings.GRANTEES_AGGREGATE_SET = import_string(
                settings.GRANTEES_AGGREGATE_SET)
        except ImportError:
            pass
    if callable(settings.GRANTEES_AGGREGATE_SET):
        return settings.GRANTEES_AGGREGATE_SET(grantees)

    return grantees


def get_available_accounts(search_fields=None, search_terms=None):
    """
    All available accounts that can be returned by `get_accessible_accounts`
    or `get_engaged_accounts`.
    """
    account_model = get_account_model()
    queryset = account_model.objects.all()

    if (hasattr(settings, 'AVAILABLE_ACCOUNTS') and
        settings.AVAILABLE_ACCOUNTS):
        if isinstance(settings.AVAILABLE_ACCOUNTS, six.string_types):
            try:
                settings.AVAILABLE_ACCOUNTS = import_string(
                    settings.AVAILABLE_ACCOUNTS)
            except ImportError:
                pass
        if callable(settings.AVAILABLE_ACCOUNTS):
            queryset = settings.AVAILABLE_ACCOUNTS(
                search_fields=search_fields, search_terms=search_terms)

    return queryset


def get_accessible_accounts(grantees, campaign=None,
                            start_at=None, ends_at=None,
                            search_fields=None, search_terms=None,
                            aggregate_set=False):
    """
    All accounts which have elected to share samples with at least one
    account in grantees.
    """
    #pylint:disable=too-many-arguments,too-many-positional-arguments
    if aggregate_set:
        search_terms = None

    try:
        iter(grantees)
    except TypeError:
        grantees = [grantees]

    if aggregate_set:
        grantees = get_grantees_aggregate_set(grantees)

    queryset = get_available_accounts(
        search_fields=search_fields, search_terms=search_terms)

    filter_params = {}
    if start_at:
        # XXX not sure anymore why we use double-optin here...
        filter_params.update({
            'portfolio_double_optin_accounts__created_at__gte': start_at})

    account_model = get_account_model()
    if campaign:
        queryset = account_model.objects.filter(
            models.Q(portfolios__campaign=campaign) |
            models.Q(portfolios__campaign__isnull=True),
            portfolios__grantee__in=grantees,
            **filter_params)
    else:
        queryset = account_model.objects.filter(
            portfolios__grantee__in=grantees,
            **filter_params)

    if search_fields and search_terms:
        annotations = {}
        filter_params = None
        for field_name in search_fields:
            annotations.update({
                field_name: Cast('_%s' % field_name, models.TextField())})
            for search_term in search_terms:
                search_clause = models.Q(**{
                    '%s__icontains' % field_name: search_term})
                if filter_params:
                    filter_params |= search_clause
                else:
                    filter_params = search_clause
        # `alias` was introduced in Django 3.2
        queryset = queryset.alias(
            _extra=Cast('portfolios__extra',
            output_field=models.JSONField()),
            **annotations).filter(filter_params)

    queryset = queryset.distinct().annotate(_extra=models.Aggregate(
            Cast('portfolios__extra', output_field=models.JSONField()),
            function=as_sql_jsonb_agg()))

    return queryset


def get_engaged_accounts(grantees, campaign=None,
                         start_at=None, ends_at=None,
                         search_fields=None, search_terms=None,
                         aggregate_set=False):
    """
    All accounts which grantee has requested a response from.
    """
    #pylint:disable=too-many-arguments,too-many-positional-arguments
    if aggregate_set:
        search_terms = None

    try:
        iter(grantees)
    except TypeError:
        grantees = [grantees]

    if aggregate_set:
        grantees = get_grantees_aggregate_set(grantees)

    queryset = get_available_accounts(
        search_fields=search_fields, search_terms=search_terms)

    filter_params = {}
    if start_at:
        filter_params.update({
            'portfolio_double_optin_accounts__created_at__gte': start_at})
    if ends_at:
        filter_params.update({
            'portfolio_double_optin_accounts__created_at__lt': ends_at})
    if campaign:
        filter_params.update({
            'portfolio_double_optin_accounts__campaign': campaign})
    queryset = get_account_model().objects.filter(
        portfolio_double_optin_accounts__grantee__in=grantees,
        portfolio_double_optin_accounts__state__in=(
            PortfolioDoubleOptIn.OPTIN_REQUEST_INITIATED,
            PortfolioDoubleOptIn.OPTIN_REQUEST_ACCEPTED,
            PortfolioDoubleOptIn.OPTIN_REQUEST_DENIED,
            PortfolioDoubleOptIn.OPTIN_REQUEST_EXPIRED),
            **filter_params).annotate(
            requested_at=models.Min(
                'portfolio_double_optin_accounts__created_at'),
            grant_key=models.Max(models.Case(
                models.When(
                    portfolio_double_optin_accounts__state=0, then=1),
                output_field=models.BooleanField())))

    if search_fields and search_terms:
        annotations = {}
        filter_params = None
        for field_name in search_fields:
            annotations.update({
                field_name: Cast('_%s' % field_name, models.TextField()),
                ('optin_%s' % field_name): Cast('_optin_%s' % field_name,
                    models.TextField()),
            })
            for search_term in search_terms:
                search_clause = models.Q(**{
                    '%s__icontains' % field_name: search_term})
                if filter_params:
                    filter_params |= search_clause
                else:
                    filter_params = search_clause
                search_clause = models.Q(**{
                    'optin_%s__icontains' % field_name: search_term})
                if filter_params:
                    filter_params |= search_clause
                else:
                    filter_params = search_clause
        # `alias` was introduced in Django 3.2
        queryset = queryset.alias(
            _extra=Cast('portfolios__extra',
            output_field=models.JSONField()),
            _optin_extra=Cast('portfolio_double_optin_accounts__extra',
            output_field=models.JSONField()),
            **annotations).filter(filter_params)

    queryset = queryset.distinct().annotate(
        _extra=models.Aggregate(
            Cast('portfolios__extra', output_field=models.JSONField()),
            function=as_sql_jsonb_agg(),
            output_field=models.JSONField()),
        _optin_extra=models.Aggregate(
            Cast('portfolio_double_optin_accounts__extra',
                 output_field=models.JSONField()),
            function=as_sql_jsonb_agg(),
            output_field=models.JSONField()))

    return queryset


def get_benchmarks_enumerated(samples, questions, questions_by_key=None):
    """
    Returns a dictionnary indexed by a question's primary key where
    each question in `questions` is associated a a dictionnary that contains:
      - the total number of samples in `samples` with an anwer to the question
      - a dictionnary of the number of samples in `samples` for each choice
        available when the question's unit is an enum.

    Example:

    {
        12: {
            "path": "/sustainability/governance/formalized-esg-strategy",
            "nb_respondents": 10,
            "rate": {
                "Yes": 5,
                "No": 5
            }
        }
    }
    """
    if not questions_by_key:
        questions_by_key = {}

    # total number of answers
    for row in Answer.objects.filter(
            question__in=questions,
            unit_id=models.F('question__default_unit_id'),
            sample_id__in=samples).values('question__id',
                'question__path').annotate(models.Count('sample_id')):
        question_pk = row['question__id']
        count = row['sample_id__count']
        path = row['question__path']
        value = questions_by_key.get(question_pk, {'path': path})
        value.update({'nb_respondents': count})
        if question_pk not in questions_by_key:
            questions_by_key.update({question_pk: value})

    # per-choice number of answers
    enum_answers = Answer.objects.filter(
            question__in=questions,
            unit_id=models.F('question__default_unit_id'),
            sample_id__in=samples,
            question__default_unit__system__in=[Unit.SYSTEM_ENUMERATED,
                Unit.SYSTEM_DATETIME], # XXX target year are stored as choices
            unit__enums__id=models.F('measured')).values('question__id',
                'unit__enums__text').annotate(models.Count('sample_id'))
    for row in enum_answers:
        question_pk = row['question__id']
        count = row['sample_id__count']
        measured = row['unit__enums__text']
        value = questions_by_key.get(question_pk)
        total = value.get('nb_respondents', None)

        counts = value.get('counts', {})
        counts.update({measured: count})
        if 'counts' not in value:
            value.update({'counts': counts})

        rate = value.get('rate', {})
        rate.update({
            measured: (int(count * 100 // total) if total else 0)})
        if 'rate' not in value:
            value.update({'rate': rate})

        if question_pk not in questions_by_key:
            questions_by_key.update({question_pk: value})

    return questions_by_key


def get_account_serializer():
    """
    Returns the ``AccountSerializer`` model that is active in this project.
    """
    path = settings.ACCOUNT_SERIALIZER
    dot_pos = path.rfind('.')
    module, attr = path[:dot_pos], path[dot_pos + 1:]
    try:
        mod = import_module(module)
    except (ImportError, ValueError) as err:
        raise ImproperlyConfigured(
            "Error importing class '%s' defined by ACCOUNT_SERIALIZER (%s)"
            % (path, err))
    try:
        cls = getattr(mod, attr)
    except AttributeError:
        raise ImproperlyConfigured('Module "%s" does not define a "%s"'\
' check the value of ACCOUNT_SERIALIZER' % (module, attr))
    return cls


def get_belongs_model():
    """
    Returns the ``Account`` model that owns campaigns and matrices.
    """
    try:
        return django_apps.get_model(settings.BELONGS_MODEL)
    except ValueError:
        raise ImproperlyConfigured(
            "BELONGS_MODEL must be of the form 'app_label.model_name'")
    except LookupError:
        raise ImproperlyConfigured("BELONGS_MODEL refers to model '%s'"\
" that has not been installed" % settings.BELONGS_MODEL)


def get_question_serializer():
    """
    Returns the ``QuestionDetailSerializer`` model that is active
    in this project.
    """
    path = settings.QUESTION_SERIALIZER
    dot_pos = path.rfind('.')
    module, attr = path[:dot_pos], path[dot_pos + 1:]
    try:
        mod = import_module(module)
    except (ImportError, ValueError) as err:
        raise ImproperlyConfigured(
            "Error importing class '%s' defined by QUESTION_SERIALIZER (%s)"
            % (path, err))
    try:
        cls = getattr(mod, attr)
    except AttributeError:
        raise ImproperlyConfigured('Module "%s" does not define a "%s"'\
' check the value of QUESTION_SERIALIZER' % (module, attr))
    return cls


def get_user_serializer():
    """
    Returns the user serializer model that is active in this project.
    """
    return import_string(settings.USER_SERIALIZER)


def get_user_detail_serializer():
    """
    Returns the user serializer model that is active in this project.
    """
    return import_string(settings.USER_DETAIL_SERIALIZER)


def handle_uniq_error(err, renames=None):
    """
    Will raise a ``ValidationError`` with the appropriate error message.
    """
    field_names = None
    err_msg = str(err).splitlines().pop()
    # PostgreSQL unique constraint.
    look = re.match(
        r'DETAIL:\s+Key \(([a-z_]+(, [a-z_]+)*)\)=\(.*\) already exists\.',
        err_msg)
    if look:
        # XXX Do we need to include '.' in pattern as done later on?
        field_names = look.group(1).split(',')
    else:
        look = re.match(
          r'DETAIL:\s+Key \(lower\(([a-z_]+)::text\)\)=\(.*\) already exists\.',
            err_msg)
        if look:
            field_names = [look.group(1)]
        else:
            # SQLite unique constraint.
            look = re.match(r'UNIQUE constraint failed: '\
                r'(?P<cols>[a-z_]+\.[a-z_]+(, [a-z_]+\.[a-z_]+)*)', err_msg)
            if not look:
                # On CentOS 7, installed sqlite 3.7.17
                # returns differently-formatted error message.
                look = re.match(
                    r'column(s)? (?P<cols>[a-z_]+(\.[a-z_]+)?'\
                    r'(, [a-z_]+(\.[a-z_]+)?)*) (is|are) not unique', err_msg)
            if look:
                field_names = [field_name.split('.')[-1]
                    for field_name in look.group('cols').split(',')]
    if field_names:
        renamed_fields = []
        for field_name in field_names:
            if renames and field_name in renames:
                field_name = renames[field_name]
            renamed_fields += [field_name]
        # XXX retrieves `saas_coupon.code` duplicates
        field_name = renamed_fields[-1]
        raise ValidationError({field_name:
            _("This %(field)s is already taken.") % {'field': field_name}})
    raise err


def is_portfolios_bypass(account, request=None):
    """
    Returns `True` if the account can access samples regardless
    of portfolio rules.

    This function is used for example as an escape mechanism for platform
    administrator to help with technical support.
    """
    if (isinstance(settings.BYPASS_SAMPLE_AVAILABLE, str) and
        '.' in settings.BYPASS_SAMPLE_AVAILABLE):
        return import_string(settings.BYPASS_SAMPLE_AVAILABLE)(account, request)
    return bool(settings.BYPASS_SAMPLE_AVAILABLE)


def validate_redirect(request):
    """
    Get the REDIRECT_FIELD_NAME and validates it is a URL on allowed hosts.
    """
    return validate_redirect_url(request.GET.get(REDIRECT_FIELD_NAME, None))


def validate_redirect_url(next_url):
    """
    Returns the next_url path if next_url matches allowed hosts.
    """
    if not next_url:
        return None
    parts = urlparse(next_url)
    if parts.netloc:
        domain, _ = split_domain_port(parts.netloc)
        allowed_hosts = (['*'] if django_settings.DEBUG
            else django_settings.ALLOWED_HOSTS)
        if not (domain and validate_host(domain, allowed_hosts)):
            return None
    return urlunparse(("", "", parts.path,
        parts.params, parts.query, parts.fragment))
