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

from collections import OrderedDict

from rest_framework.pagination import BasePagination
from rest_framework.response import Response


class MetricsPagination(BasePagination):
    """
    Decorate the results of an API call with unit, scale and title
    """
    def paginate_queryset(self, queryset, request, view=None):
        #pylint:disable=attribute-defined-outside-init
        self.view = view
        return queryset

    def get_paginated_response(self, data):
        return Response(OrderedDict([
            ('title', getattr(self.view, 'title', "")),
            ('scale', getattr(self.view, 'scale', 1)),
            ('unit', getattr(self.view, 'unit', None)),
            ('nb_accounts', getattr(self.view, 'nb_accounts', None)),
            ('labels', getattr(self.view, 'labels', None)),
            ('count', len(data)),
            ('results', data)
        ]))

    def get_paginated_response_schema(self, schema):
        if 'description' not in schema:
            schema.update({'description': "Items in the queryset"})
        return {
            'type': 'object',
            'properties': {
                'title': {
                    'type': 'integer',
                    'description': "Title for the results table"
                },
                'scale': {
                    'type': 'integer',
                    'description': "The scale of the number reported"\
                    " in the tables (ex: 1000 when numbers are reported"\
                    " in thousands)"
                },
                'unit': {
                    'type': 'integer',
                    'description': "Unit the measured field is in"
                },
                'nb_accounts': {
                    'type': 'integer',
                    'description': "Total number of accounts evaluated"
                },
                'labels': {
                    'type': 'array',
                    'description': "Labels for the x-axis when present"
                },
                'count': {
                    'type': 'integer',
                    'description': "The number of records"
                },
                'results': schema,
            },
        }
