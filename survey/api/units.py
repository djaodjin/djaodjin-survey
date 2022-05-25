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

import logging

from rest_framework import generics
from rest_framework.filters import BaseFilterBackend

from .serializers import UnitSerializer


LOGGER = logging.getLogger(__name__)


class EquivalenceFilter(BaseFilterBackend):
    """
    Units that can be used intercheably
    """
    def get_schema_operation_parameters(self, view):
        return [
            {
                'name': 'eq',
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
    Retrieves a unit of measurement

    Retrieves the details of a ``Unit``.

    **Tags**: assessments

    **Examples**

    .. code-block:: http

        GET /api/units/assessment HTTP/1.1

    responds

    .. code-block:: json

        {
            "slug": "assessments",
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
    serializer_class = UnitSerializer

    def get_object(self):
        return self.unit


class UnitListAPIView(generics.ListAPIView):
    """
    Lists units available

    **Tags**: assessments

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
            "slug": "assessments",
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
    serializer_class = UnitSerializer
    filter_backends = (EquivalenceFilter,)