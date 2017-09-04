# Copyright (c) 2017, DjaoDjin inc.
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

from rest_framework import generics, mixins, status
from rest_framework import response as http

from ..mixins import ResponseMixin
from ..models import Answer, Question
from .serializers import AnswerSerializer, ResponseSerializer


LOGGER = logging.getLogger(__name__)


class AnswerAPIView(ResponseMixin, mixins.CreateModelMixin,
                    generics.RetrieveUpdateDestroyAPIView):

    serializer_class = AnswerSerializer
    lookup_rank_kwarg = 'rank'

    @property
    def question(self):
        if not hasattr(self, '_question'):
            self._question = Question.objects.get(
                survey=self.sample.survey, rank=self.kwargs.get(
                    self.lookup_rank_kwarg))
        return self._question

    def update(self, request, *args, **kwargs):
        #pylint:disable=unused-argument
        partial = kwargs.pop('partial', False)
        serializer = self.get_serializer(data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        try:
            serializer.instance = Answer.objects.get(
                response=self.sample, question=self.question)
            self.perform_update(serializer)
        except Answer.DoesNotExist:
            self.perform_create(serializer)
            headers = self.get_success_headers(serializer.data)
            return http.Response(serializer.data,
                status=status.HTTP_201_CREATED, headers=headers)

        return http.Response(serializer.data)

    def perform_create(self, serializer):
        serializer.save(response=self.sample, question=self.question,
            rank=self.question.rank)


class ResponseAPIView(ResponseMixin, generics.RetrieveUpdateDestroyAPIView):

    serializer_class = ResponseSerializer

    def get_object(self):
        return self.sample
