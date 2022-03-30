# Copyright (c) 2021, DjaoDjin inc.
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

from ..mixins import CampaignMixin, CampaignQuerysetMixin, DateRangeContextMixin
from .serializers import CampaignSerializer, CampaignCreateSerializer
from ..filters import DateRangeFilter, OrderingFilter, SearchFilter


LOGGER = logging.getLogger(__name__)


class CampaignAPIView(CampaignMixin, generics.RetrieveDestroyAPIView):
    """
    Retrieves a campaign

    Retrieves the details of a ``Campaign``.

    **Tags**: assessments

    **Examples**

    .. code-block:: http

        GET /api/envconnect/campaign/construction HTTP/1.1

    responds

    .. code-block:: json

        {
            "slug": "construction",
            "account": "envconnect",
            "title": "Assessment on sustainable construction practices",
            "active": true,
            "quizz_mode": false,
            "questions": [
                {
                    "path": "/construction/product-design",
                    "title": "Product Design",
                    "default_unit": {
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
                    },
                    "ui_hint": "radio"
                },
                {
                    "path": "/construction/packaging-design",
                    "title": "Packaging Design",
                    "default_unit": {
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
                    },
                    "ui_hint": "radio"
                }
            ]
        }
    """
    serializer_class = CampaignSerializer

    def get_object(self):
        return self.campaign

    def delete(self, request, *args, **kwargs):
        """
        Deletes a campaign

        Removes a ``Campaign`` and all associated ``Sample``.
        The underlying ``Answer`` that were grouped in a ``Sample`` remain
        present in the database. These ``Answer`` are just no longer grouped
        logically in a ``Sample``.

        **Tags**: editors

        **Examples**

        .. code-block:: http

            DELETE /api/envconnect/campaign/boxes-enclosures HTTP/1.1
        """
        #pylint:disable=useless-super-delegation
        return super(CampaignAPIView, self).delete(request, *args, **kwargs)


class SmartCampaignListMixin(DateRangeContextMixin):
    """
    ``Campaign`` list which is also searchable and sortable.
    """
    search_fields = ('title',)

    ordering_fields = [
        ('created_at', 'created_at'),
        ('title', 'title'),
    ]

    filter_backends = (DateRangeFilter, SearchFilter, OrderingFilter,)


class CampaignListAPIView(SmartCampaignListMixin, CampaignQuerysetMixin,
                          generics.ListCreateAPIView):

    serializer_class = CampaignSerializer

    def get_serializer_class(self):
        if self.request.method.lower() == 'post':
            return CampaignCreateSerializer
        return super(CampaignListAPIView, self).get_serializer_class()

    def perform_create(self, serializer):
        serializer.save(account=self.account)
