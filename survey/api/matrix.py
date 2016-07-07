# Copyright (c) 2016, DjaoDjin inc.
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
from collections import OrderedDict

from django.db.models import F
from extra_views.contrib.mixins import SearchableListMixin
from rest_framework import generics
from rest_framework.pagination import PageNumberPagination
from rest_framework import response as http

from ..mixins import MatrixMixin
from ..models import Answer, Matrix, Portfolio, Question
from ..utils import get_account_model
from .serializers import (PortfolioSerializer,
    MatrixSerializer, AccountSerializer, QuestionSerializer)


LOGGER = logging.getLogger(__name__)


class MatrixCreateAPIView(generics.ListCreateAPIView):
    """
    Filtered list of ``Question``.

    **Examples**:

    .. sourcecode:: http

        GET /api/matrix/

        Response:

        {
           "slug": "all",
           "title": "All accounts against all questions",
           "metric": {
               "slug": "all-questions",
               "title": "All questions",
               "predicates": []
           },
           "cohorts": [{
               "slug": "all-accounts",
               "title": "All accounts",
               "predicates": []
           }]
        }


    .. sourcecode:: http

        POST /api/matrix/

        {
           "slug": "all",
           "title": "All accounts against all questions",
           "metric": {
               "slug": "all-questions",
               "title": "All questions",
               "predicates": []
           },
           "cohorts": [{
               "slug": "all-accounts",
               "title": "All accounts",
               "predicates": []
           }]
        }

        Response:

        201 CREATED

        {
           "slug": "all",
           "title": "All accounts against all questions",
           "metric": {
               "slug": "all-questions",
               "title": "All questions",
               "predicates": []
           },
           "cohorts": [{
               "slug": "all-accounts",
               "title": "All accounts",
               "predicates": []
           }]
        }
    """
    serializer_class = MatrixSerializer

    def get_queryset(self):
        return Matrix.objects.all()


class MatrixDetailAPIView(MatrixMixin, generics.RetrieveUpdateDestroyAPIView):

    serializer_class = MatrixSerializer
    lookup_field = 'slug'
    lookup_url_kwarg = 'matrix'

    def get(self, request, *args, **kwargs):
        #pylint:disable=unused-argument,too-many-locals
        instance = self.get_object()
        scores = {}
        includes, excludes = instance.metric.as_kwargs()
        questions = Question.objects.filter(**includes).exclude(**excludes)
        nb_questions = len(questions)
        for cohort in instance.cohorts.all():
            includes, excludes = cohort.as_kwargs()
            accounts = get_account_model().objects.filter(
                **includes).exclude(**excludes)
            nb_correct_answers = Answer.objects.filter(
                response__user__in=accounts).filter(
                    body=F('question__correct_answer')).count()
            score = nb_correct_answers * 100 / (nb_questions * len(accounts))
            LOGGER.debug("score for '%s' = (%d * 100) / (%d * %d) = %f",
                str(cohort), nb_correct_answers, nb_questions, len(accounts),
                score)
            assert score <= 100
            scores.update({str(cohort): score})
        serializer = self.get_serializer(instance)
        val = serializer.data
        val.update({"scores": scores})
        return http.Response(val)


class PortfolioQuerysetMixin(object):

    @staticmethod
    def get_queryset():
        return Portfolio.objects.all()


class PortfolioListAPIView(SearchableListMixin, PortfolioQuerysetMixin,
                           generics.ListCreateAPIView):

    search_fields = ['tags']
    serializer_class = PortfolioSerializer


class PortfolioDetailAPIView(generics.RetrieveUpdateDestroyAPIView):

    serializer_class = PortfolioSerializer
    lookup_field = 'slug'
    lookup_url_kwarg = 'portfolio'

    def get_queryset(self):
        return Portfolio.objects.all()


class PortfolioPagination(PageNumberPagination):

    def paginate_queryset(self, queryset, request, view=None):
        self.portfolio = view.portfolio
        return super(PortfolioPagination, self).paginate_queryset(
            queryset, request, view=view)

    def get_paginated_response(self, data):
        return http.Response(OrderedDict([
            ('portfolio', PortfolioSerializer().to_representation(
                self.portfolio)),
            ('count', self.page.paginator.count),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('results', data)
        ]))


class PortfolioObjectsAPIView(generics.ListAPIView):

    pagination_class = PortfolioPagination
    serializer_class = None # override in subclasses
    lookup_field = 'slug'
    lookup_url_kwarg = 'portfolio'

    def get(self, request, *args, **kwargs): #pylint: disable=unused-argument
        self.portfolio = generics.get_object_or_404(Portfolio.objects.all(),
            slug=self.kwargs[self.lookup_url_kwarg])
        return super(PortfolioObjectsAPIView, self).get(
            request, *args, **kwargs)


class AccountListAPIView(PortfolioObjectsAPIView):
    """
    Filtered list of ``Portfolio``.

    **Examples**:

    .. sourcecode:: http

        GET /api/questions/languages

        Response:

        {
           "slug": "languages",
           "title": "All questions related to languages"
           "predicates":[{
               "operator": "contains",
               "operand": "language",
               "property": "text",
               "filterType":"keepmatching"
           }]
        }
    """
    serializer_class = AccountSerializer

    def get_queryset(self):
        return self.get_serializer_class().Meta.model.objects.all()


class QuestionListAPIView(PortfolioObjectsAPIView):
    """
    Filtered list of ``Question``.

    **Examples**:

    .. sourcecode:: http

        GET /api/questions/languages

        Response:

        {
           "slug": "languages",
           "title": "All questions related to languages"
           "predicates":[{
               "operator": "contains",
               "operand": "language",
               "property": "text",
               "filterType":"keepmatching"
           }]
        }
    """
    serializer_class = QuestionSerializer

    def get_queryset(self):
        return Question.objects.all()

