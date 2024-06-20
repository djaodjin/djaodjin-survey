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
from __future__ import unicode_literals

import logging, operator
from functools import reduce

from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.db.models.functions import TruncMonth, TruncYear
from django.db.models.query import RawQuerySet
from rest_framework.filters import (OrderingFilter as BaseOrderingFilter,
    SearchFilter as BaseSearchFilter, BaseFilterBackend)
from rest_framework.compat import distinct

from . import settings
from .compat import force_str, six
from .helpers import datetime_or_now, timezone_or_utc
from .models import PortfolioDoubleOptIn

LOGGER = logging.getLogger(__name__)


def search_terms_as_list(params):
    """
    Search terms are set by a ?q=... query parameter.
    When multiple search terms must be matched, they can be delimited
    by a comma.
    """
    params = params.replace('\x00', '')  # strip null characters
    results = []
    inside = False
    first = 0
    for last, letter in enumerate(params):
        if inside:
            if letter == '"':
                if first < last:
                    results += [params[first:last]]
                first = last + 1
                inside = False
        else:
            if letter in (',',):
                if first < last:
                    results += [params[first:last]]
                first = last + 1
            elif letter == '"':
                inside = True
                first = last + 1
    if first < len(params):
        results += [params[first:len(params)]]
    return results


class SearchFilter(BaseSearchFilter):

    search_field_param = settings.SEARCH_FIELDS_PARAM

    def filter_queryset(self, request, queryset, view):
        search_fields = self.get_valid_fields(request, queryset, view)
        search_terms = self.get_search_terms(request)
        LOGGER.debug("[SearchFilter.filter_queryset] search_terms=%s, "\
            "search_fields=%s", search_terms, search_fields)

        if not search_fields or not search_terms:
            return queryset

        orm_lookups = [
            self.construct_search(six.text_type(search_field))
            for search_field in search_fields
        ]

        base = queryset
        conditions = []
        for search_term in search_terms:
            queries = [
                models.Q(**{orm_lookup: search_term})
                for orm_lookup in orm_lookups
            ]
            conditions.append(reduce(operator.or_, queries))
        queryset = queryset.filter(reduce(operator.or_, conditions))

        if self.must_call_distinct(queryset, search_fields):
            # Filtering against a many-to-many field requires us to
            # call queryset.distinct() in order to avoid duplicate items
            # in the resulting queryset.
            # We try to avoid this if possible, for performance reasons.
            queryset = distinct(queryset, base)
        return queryset


    def filter_valid_fields(self, queryset, fields, view):
        #pylint:disable=protected-access
        model_fields = {
            field.name for field in queryset.model._meta.get_fields()}
        # We add all the fields that could be aliases then filter out the ones
        # which are not present in the model.
        alternate_fields = getattr(view, 'alternate_fields', {})
        for field in fields:
            field_lookup = field[0]
            lookup = self.lookup_prefixes.get(field_lookup)
            if lookup:
                field = field[1:]
            alternate_field = alternate_fields.get(field, None)
            if alternate_field:
                if lookup:
                    alternate_field = field_lookup + alternate_field
                if isinstance(alternate_field, (list, tuple)):
                    fields += tuple(alternate_field)
                else:
                    fields += tuple([alternate_field])

        valid_fields = []
        for field in fields:
            field_name = field
            lookup = self.lookup_prefixes.get(field_name[0])
            if lookup:
                field_name = field_name[1:]
            if '__' in field_name:
                relation, rel_field = field_name.split('__')
                try:
                    # check if the field is a relation
                    rel = queryset.model._meta.get_field(relation).remote_field
                    if rel:
                        # if the field doesn't exist the
                        # call will throw an exception
                        rel.model._meta.get_field(rel_field)
                        valid_fields.append(field)
                except FieldDoesNotExist:
                    pass
            elif field_name in model_fields:
                rel = queryset.model._meta.get_field(field_name).remote_field
                if not rel:
                    # if it is a relation fields (as a result valid),
                    # we don't want to end-up with a problem later on
                    # when we are trying `field__icontains=`.
                    valid_fields.append(field)

        return tuple(valid_fields)


    def get_query_param(self, request, key, default_value=None):
        try:
            return request.query_params.get(key, default_value)
        except AttributeError:
            pass
        return request.GET.get(key, default_value)


    def get_query_param_list(self, request, key, default_value=None):
        try:
            return request.query_params.getlist(key, default_value)
        except AttributeError:
            pass
        return request.GET.getlist(key, default_value)


    def get_query_fields(self, request):
        return self.get_query_param_list(request, self.search_field_param)


    def get_search_terms(self, request):
        """
        Search terms are set by a ?q=... query parameter.
        When multiple search terms must be matched, they can be delimited
        by a comma.
        """
        return search_terms_as_list(
            self.get_query_param(request, self.search_param, ''))


    def get_valid_fields(self, request, queryset, view, context=None):
        #pylint:disable=protected-access,unused-argument
        if context is None:
            context = {}

        fields = self.get_query_fields(request)
        # client-supplied fields take precedence
        if fields:
            fields = self.filter_valid_fields(queryset, fields, view)
        # if there are no fields (due to empty query params or wrong
        # fields we fallback to fields specified in the view
        if not fields:
            fields = getattr(view, 'search_fields', [])
            fields = self.filter_valid_fields(queryset, fields, view)
        return fields


    def get_schema_operation_parameters(self, view):
        search_fields = getattr(view, 'search_fields', None)
        search_field_names = []
        if search_fields:
            for search_field in search_fields:
                if isinstance(search_field, tuple):
                    search_field_names += [search_field[1]]
                else:
                    search_field_names += [search_field]
        search_fields_description = (
            "restrict searches to one or more fields in: %s."\
            " searches all fields when unspecified."  % (
            ', '.join(search_field_names)))
        return [
            {
                'name': self.search_param,
                'required': False,
                'in': 'query',
                'description': force_str(
                    "value to search for in the fields specified by %s" %
                    self.search_field_param),
                'schema': {
                    'type': 'string',
                },
            },
            {
                'name': self.search_field_param,
                'required': False,
                'in': 'query',
                'description': force_str(search_fields_description),
                'schema': {
                    'type': 'string',
                },
            },
        ]


class OrderingFilter(BaseOrderingFilter):

    def get_query_param(self, request, key, default_value=None):
        try:
            return request.query_params.getlist(key, default_value)
        except AttributeError:
            pass
        return request.GET.get(key, default_value)

    def get_valid_fields(self, queryset, view, context=None):
        #pylint:disable=protected-access
        if context is None:
            context = {}

        model_fields = {
            field.name for field in queryset.model._meta.get_fields()}
        # XXX base
        base_fields = super(OrderingFilter, self).get_valid_fields(
            queryset, view, context=context)
        alternate_fields = getattr(view, 'alternate_fields', {})
        for field in base_fields:
            alternate_field = alternate_fields.get(field[0], None)
            if alternate_field:
                if isinstance(alternate_field, (list, tuple)):
                    base_fields += [(item, item) for item in alternate_field]
                else:
                    base_fields += [(alternate_field, alternate_field)]
        valid_fields = []
        for field in base_fields:
            if '__' in field[0]:
                relation, rel_field = field[0].split('__')
                try:
                    # check if the field is a relation
                    rel = queryset.model._meta.get_field(relation).remote_field
                    if rel:
                        # if the field doesn't exist the
                        # call will throw an exception
                        rel.model._meta.get_field(rel_field)
                        valid_fields.append(field)
                except FieldDoesNotExist:
                    pass
            elif field[0] in model_fields:
                valid_fields.append(field)
        return tuple(valid_fields)

    def remove_invalid_fields(self, queryset, fields, view, request):
        valid_fields = {item[1]: item[0]
            for item in self.get_valid_fields(
                queryset, view, {'request': request})}
        ordering = []
        for term in fields:
            alias = term
            reverse = False
            if alias.startswith('-'):
                alias = alias[1:]
                reverse = True
            real_field = valid_fields.get(alias)
            if real_field:
                if reverse:
                    real_field = '-' + real_field
                ordering.append(real_field)
        return ordering

    def get_ordering(self, request, queryset, view):
        # We use an alternate ordering if the fields are not present
        # in the second model.
        # (ex: Organization.full_name vs. User.first_name)
        ordering = []
        default = self.get_default_ordering(view)
        if default:
            ordering = self.remove_invalid_fields(
                queryset, default, view, request)
        default_ordering = list(ordering)
        params = self.get_query_param(request, self.ordering_param)
        if params:
            if isinstance(params, six.string_types):
                params = params.split(',')
            fields = [param.strip() for param in params]
            alternate_fields = getattr(view, 'alternate_fields', {})
            for field in fields:
                reverse = False
                if field.startswith('-'):
                    field = field[1:]
                    reverse = True
                alternate_field = alternate_fields.get(field, None)
                if alternate_field:
                    if reverse:
                        if isinstance(alternate_field, (list, tuple)):
                            fields += ['-%s' % item for item in alternate_field]
                        else:
                            fields += ['-%s' % alternate_field]
                    else:
                        if isinstance(alternate_field, (list, tuple)):
                            fields += alternate_field
                        else:
                            fields += [alternate_field]
            ordering = self.remove_invalid_fields(
                queryset, fields, view, request) + default_ordering
        LOGGER.debug("[OrderingFilter] params=%s, default_ordering=%s,"\
            " ordering_fields=%s", params, default_ordering, ordering)
        return ordering

    def get_schema_operation_parameters(self, view):
        # validating presence of coreapi and coreschema
        super(OrderingFilter, self).get_schema_fields(view)
        ordering_fields = getattr(view, 'ordering_fields', [])
        sort_fields_description = "sort by %s. If a field is preceded by"\
            " a minus sign ('-'), the order will be reversed. Multiple 'o'"\
            " parameters can be specified to produce a stable"\
            " result." % ', '.join([field[1] for field in ordering_fields])
        return [
            {
                'name': self.ordering_param,
                'required': False,
                'in': 'query',
                'description': force_str(sort_fields_description),
                'schema': {
                    'type': 'string',
                },
            },
        ]


class DateRangeFilter(BaseFilterBackend):

    forced_date_range = True
    date_field = 'created_at'
    alternate_date_field = 'date_joined'
    start_at_param = 'start_at'
    ends_at_param = 'ends_at'

    def get_params(self, request, view):
        tzinfo = timezone_or_utc(request.GET.get('timezone'))
        ends_at = None
        if self.ends_at_param:
            ends_at = request.GET.get(self.ends_at_param)
        start_at = request.GET.get(self.start_at_param)
        forced_date_range = getattr(view, 'forced_date_range',
            self.forced_date_range)
        if forced_date_range or ends_at:
            if ends_at is not None:
                ends_at = ends_at.strip('"')
            ends_at = datetime_or_now(ends_at)
            ends_at = ends_at.astimezone(tzinfo)
        if start_at:
            start_at = datetime_or_now(start_at.strip('"'))
            start_at = start_at.astimezone(tzinfo)
        return start_at, ends_at

    def get_date_field(self, model):
        #pylint:disable=protected-access
        model_fields = {
            field.name for field in model._meta.get_fields()}
        if self.date_field in model_fields:
            return self.date_field
        if self.alternate_date_field in model_fields:
            return self.alternate_date_field
        return None

    def filter_queryset(self, request, queryset, view):
        start_at, ends_at = self.get_params(request, view)
        field = self.get_date_field(queryset.model)
        if not field:
            return queryset
        kwargs = {}
        if ends_at:
            kwargs.update({'%s__lt' % field: ends_at})
        if start_at:
            kwargs.update({'%s__gte' % field: start_at})
        return queryset.filter(**kwargs)

    def get_schema_operation_parameters(self, view):
        fields = super(DateRangeFilter, self).get_schema_operation_parameters(
            view)
        fields += [{
            'name': self.start_at_param,
            'required': False,
            'in': 'query',
            'description': force_str("date/time in ISO 8601 format"),
            'schema': {
                'type': 'string',
            },
        }]
        if self.ends_at_param:
            fields += [{
                'name': self.ends_at_param,
                'required': False,
                'in': 'query',
                'description': force_str("date/time in ISO 8601 format"),
                'schema': {
                    'type': 'string',
                },
            }]
        return fields


class AggregateByPeriodFilter(DateRangeFilter):

    period_type_param = 'period_type'
    nb_periods_param = 'nb_periods'

    def filter_queryset(self, request, queryset, view):
        if isinstance(queryset, (RawQuerySet, list)):
            return queryset

        period_type = request.GET.get(self.period_type_param)
        if period_type == 'yearly':
            queryset = queryset.annotate(
                period=TruncYear('sample__created_at')).values(
                    'question_id',
                    'question_path',
                    'question_title',
                    'question_default_unit_slug',
                    'question_default_unit_title',
                    'question_default_unit_system',
                    'choice',
                    'period')
        elif period_type == 'monthly':
            queryset = queryset.annotate(
                period=TruncMonth('sample__created_at')).values(
                    'question_id',
                    'question_path',
                    'question_title',
                    'question_default_unit_slug',
                    'question_default_unit_title',
                    'question_default_unit_system',
                    'choice',
                    'period')
        # XXX Calling QuerySet.annotate() after union() is not supported.
        return queryset.annotate(count=models.Count('sample_id'))


    def get_schema_operation_parameters(self, view):
        fields = super(AggregateByPeriodFilter,
            self).get_schema_operation_parameters(view)
        fields += [{
            'name': self.period_type_param,
            'required': False,
            'in': 'query',
            'description': force_str("aggregate period (yearly or monthly)"),
            'schema': {
                'type': 'string',
            },
        }]
        if self.nb_periods_param:
            fields += [{
                'name': self.nb_periods_param,
                'required': False,
                'in': 'query',
                'description': force_str("number of periods"),
                'schema': {
                    'type': 'integer',
                },
            }]
        return fields


class StateFilter(BaseFilterBackend):

    state_param = 'state'
    state_field = 'state'
    state_candidates = []

    def get_query_param(self, request, key, default_value=None):
        try:
            return request.query_params.get(key, default_value)
        except AttributeError:
            pass
        return request.GET.get(key, default_value)

    def filter_queryset(self, request, queryset, view):
        state = self.get_query_param(request, self.state_param, '')
        flt = None
        for val in state.split(','):
            for candidate in self.state_candidates:
                if val == candidate[1]:
                    if flt:
                        flt |= models.Q(**{self.state_field: candidate[0]})
                    else:
                        flt = models.Q(**{self.state_field: candidate[0]})
                    break
        if flt is not None:
            queryset = queryset.filter(flt)
        return queryset

    def get_schema_operation_parameters(self, view):
        fields = super(StateFilter, self).get_schema_operation_parameters(view)
        fields += [
            {
                'name': self.state_param,
                'required': False,
                'in': 'query',
                'description': force_str("filter by state (%(choices)s)" % {
                    'choices': ", ".join([
                        candidate[1] for candidate in self.state_candidates])
                }),
                'schema': {
                    'type': 'string',
                },
            },
        ]
        return fields


class DoubleOptInStateFilter(StateFilter):

    state_param = 'state'
    state_field = 'state'
    state_candidates = PortfolioDoubleOptIn.STATES


class SampleStateFilter(StateFilter):

    state_param = 'state'
    state_field = 'is_frozen'
    state_candidates = [
        (False, 'active'),
        (True, 'completed')
    ]
