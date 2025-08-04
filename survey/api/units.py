# Copyright (c) 2025, DjaoDjin inc.
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

from django.db.models import F
from rest_framework import generics
from rest_framework.filters import BaseFilterBackend
from rest_framework.pagination import BasePagination
from rest_framework.response import Response

from ..docs import extend_schema
from ..filters import SearchFilter
from ..models import Choice, Unit
from .serializers import (ChoiceSerializer, ConvertUnitSerializer, EnumField,
    UnitSerializer)

LOGGER = logging.getLogger(__name__)


class ChoicesPagination(BasePagination):

    def paginate_queryset(self, queryset, request, view=None):
        #pylint:disable=attribute-defined-outside-init
        self.unit = getattr(view, 'unit', None)
        return queryset

    def get_paginated_response(self, data):
        system = EnumField(choices=Unit.SYSTEMS).to_representation(
            self.unit.system)
        return Response({
            'slug': self.unit.slug,
            'title': self.unit.title,
            'system': system,
            'results': data,
        })

    def get_paginated_response_schema(self, schema):
        return {
            'type': 'object',
            'required': ['slug', 'title', 'system', 'results'],
            'properties': {
                'slug': {
                    'type': 'string',
                    'example': "yes-no",
                },
                'title': {
                    'type': 'string',
                    'example': "Yes/No",
                },
                'system': {
                    'type': 'string',
                    'example': "enum",
                },
                'results': schema,
            },
        }


class EquivalenceFilter(BaseFilterBackend):
    """
    Units that can be used intercheably
    """
    equiv_term = 'eq'

    def get_equiv_terms(self, request):
        """
        Search terms are set by a ?eq=... query parameter,
        and may be comma and/or whitespace delimited.
        """
        params = request.query_params.get(self.equiv_term, '')
        params = params.replace('\x00', '')  # strip null characters
        params = params.replace(',', ' ')
        return params.split()

    def filter_queryset(self, request, queryset, view):
        equiv_terms = self.get_equiv_terms(request)
        if equiv_terms:
            return queryset.filter(
                target_equivalences__source__slug__in=equiv_terms).annotate(
                    factor=F('target_equivalences__factor'),
                    scale=F('target_equivalences__scale'),
                    content=F('target_equivalences__content'))
        return queryset

    def get_schema_operation_parameters(self, view):
        return [
            {
                'name': self.equiv_term,
                'required': False,
                'in': 'query',
                'description':
                    "units that can be used intercheably with this one",
                'schema': {
                    'type': 'string',
                },
            },
        ]



class UnitDetailAPIView(generics.RetrieveAPIView):
    """
    Retrieves a unit

    Retrieves the details of a ``Unit``.

    **Tags**: content

    **Examples**

    .. code-block:: http

        GET /api/units/assessment HTTP/1.1

    responds

    .. code-block:: json

        {
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
        }
    """
    queryset = Unit.objects.all()
    serializer_class = UnitSerializer
    lookup_field = 'slug'
    lookup_url_kwarg = 'unit'
    search_fields = ( # applies to `Choice`, not `self.object` (of type `Unit`)
        'text',
        'descr'
    )

    @property
    def unit(self):
        if not hasattr(self, '_unit'):
            #pylint:disable=attribute-defined-outside-init
            self._unit = self.get_object()
        return self._unit

    def get_serializer_context(self):
        context = super(UnitDetailAPIView, self).get_serializer_context()
        if self.unit.system == Unit.SYSTEM_ENUMERATED:
            search_filter = SearchFilter()
            if search_filter.get_search_terms(self.request):
                queryset = search_filter.filter_queryset(
                    self.request, self.unit.choices, self)
                context.update({
                    'choices': queryset
                })
        return context


class ChoiceListAPIView(generics.ListAPIView):
    """
    Retrieves enumerated choices for a unit

    Retrieves choices of a ``Unit`` with an enum system. The results can
    be filtered by a search criteria.

    **Tags**: content

    **Examples**

    .. code-block:: http

        GET /api/units/assessment/search?q=yes HTTP/1.1

    responds

    .. code-block:: json

        {
            "slug": "assessment",
            "title": "assessments",
            "system": "enum",
            "results": [
                {
                    "rank": 1,
                    "text": "mostly-yes",
                    "descr": "Mostly yes"
                },
                {
                    "rank": 2,
                    "text": "yes",
                    "descr": "Yes"
                }
            ]
        }
    """
    queryset = Choice.objects.all()
    serializer_class = ChoiceSerializer
    lookup_field = 'slug'
    lookup_url_kwarg = 'unit'
    search_fields = (
        'text',
        'descr'
    )
    filter_backends = (SearchFilter,)
    pagination_class = ChoicesPagination

    @property
    def unit(self):
        if not hasattr(self, '_unit'):
            #pylint:disable=attribute-defined-outside-init
            self._unit = generics.get_object_or_404(Unit.objects.all(),
                slug=self.kwargs.get(self.lookup_url_kwarg))
        return self._unit

    def get_queryset(self):
        return self.unit.choices


class UnitListAPIView(generics.ListAPIView):
    """
    Lists units

    **Tags**: content

    This API end-point lists all the units of measurement available
    to record datapoints.

    Alongside the usual metric units (meters, kilogram, etc.) and imperial
    units (inch, pounds, etc.), there could be units with a rank system
    (natural integers), or an enumerated system (finite set of values with
    no order). A special unit is used to represent free form text.

    **Examples**

    .. code-block:: http

        GET /api/units HTTP/1.1

    responds

    .. code-block:: json

        {
          "count": 1,
          "previous": null,
          "next": null,
          "results": [{
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
          }]
        }
    """
    search_fields = (
        'slug',
    )

    serializer_class = UnitSerializer
    filter_backends = (EquivalenceFilter, SearchFilter)
    queryset = Unit.objects.all().order_by('slug')

    def get_query_param(self, key, default_value=None):
        try:
            return self.request.query_params.get(key, default_value)
        except AttributeError:
            pass
        return self.request.GET.get(key, default_value)


    def get_serializer_class(self):
        if self.get_query_param('eq'):
            return ConvertUnitSerializer
        return super(UnitListAPIView, self).get_serializer_class()


    @extend_schema(operation_id='units_index')
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)
