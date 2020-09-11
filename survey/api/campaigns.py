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

from ..mixins import CampaignMixin
from .serializers import CampaignSerializer


LOGGER = logging.getLogger(__name__)


class CampaignAPIView(CampaignMixin, generics.RetrieveDestroyAPIView):
    """
    Retrieves a campaign

    Retrieves the details of a ``Campaign``.

    **Tags**: survey

    **Examples**

    .. code-block:: http

        GET /api/cowork/campaign/best-practices/ HTTP/1.1

    responds

    .. code-block:: json

        {
            "slug": "best-practices",
            "account": "envconnect",
            "title": "Assessment on Best Practices",
            "active": true,
            "quizz_mode": false,
            "questions": [
                {
                    "path": "/product-design",
                    "title": "Product Design",
                    "unit": "assessment-choices",
                },
                {
                    "path": "/packaging-design",
                    "title": "Packaging Design",
                    "unit": "assessment-choices",
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

        Removes a ``Campaign`` and all associated ``Sample``
        from the database.

        **Tags**: survey

        **Examples**

        .. code-block:: http

            DELETE /api/cowork/campaign/best-practices/ HTTP/1.1
        """
        #pylint:disable=useless-super-delegation
        return super(CampaignAPIView, self).delete(request, *args, **kwargs)
