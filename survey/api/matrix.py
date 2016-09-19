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
from django.shortcuts import get_object_or_404
from extra_views.contrib.mixins import SearchableListMixin
from rest_framework import generics
from rest_framework.pagination import PageNumberPagination
from rest_framework import response as http

from ..mixins import MatrixMixin
from ..models import Answer, Matrix, EditableFilter
from ..utils import (get_account_model, get_account_serializer,
    get_question_serializer)
from .serializers import EditableFilterSerializer, MatrixSerializer


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
    """
    A table of scores for cohorts aganist a metric.

    **Examples**:

    .. sourcecode:: http

        GET /api/matrix/languages

        Response:

        {
           "slug": "languages",
           "title": "All cohorts for all questions"
           "scores":[{
               "portfolio-a": "0.1",
               "portfolio-b": "0.5",
           }]
        }
    """

    serializer_class = MatrixSerializer
    lookup_field = 'slug'
    lookup_url_kwarg = 'matrix'
    question_model = get_question_serializer().Meta.model

    def get(self, request, *args, **kwargs):
        #pylint:disable=unused-argument,too-many-locals
        instance = Matrix.objects.filter(
            slug=self.kwargs.get(self.matrix_url_kwarg)).first()
        if instance:
            metric = instance.metric
            cohorts = instance.cohorts.all()
            serializer = self.get_serializer(instance)
            val = serializer.data
        else:
            metric = get_object_or_404(EditableFilter,
                slug=self.kwargs.get(self.matrix_url_kwarg))
            cohorts = []
            for cohort_slug in request.GET:
                cohorts += [get_object_or_404(EditableFilter, slug=cohort_slug)]
            val = {
                'slug': metric.slug,
                'title': metric.title,
                'metric': EditableFilterSerializer().to_representation(metric),
                'cohorts': EditableFilterSerializer(
                    many=True).to_representation(cohorts)}

        scores = {}
        if metric:
            includes, excludes = metric.as_kwargs()
            questions = self.question_model.objects.filter(
                **includes).exclude(**excludes)
            nb_questions = len(questions)
            if nb_questions > 0:
                for cohort in cohorts:
                    includes, excludes = cohort.as_kwargs()
                    accounts = get_account_model().objects.filter(
                        **includes).exclude(**excludes)
                    nb_accounts = len(accounts)
                    if nb_accounts > 0:
                        nb_correct_answers = Answer.objects.filter(
                            question__in=questions,
                            response__account__in=accounts).filter(
                                text=F('question__correct_answer')).count()
                        score = nb_correct_answers * 100 / (
                            nb_questions * nb_accounts)
                        LOGGER.debug("score for '%s' = (%d * 100) "\
                            "/ (%d * %d) = %f", str(cohort), nb_correct_answers,
                            nb_questions, nb_accounts, score)
                        assert score <= 100
                        scores.update({str(cohort): score})
        val.update({"scores": scores})
        return http.Response(val)


class EditableFilterQuerysetMixin(object):

    @staticmethod
    def get_queryset():
        return EditableFilter.objects.all()


class EditableFilterListAPIView(SearchableListMixin,
                EditableFilterQuerysetMixin, generics.ListCreateAPIView):

    search_fields = ['tags']
    serializer_class = EditableFilterSerializer


class EditableFilterDetailAPIView(generics.RetrieveUpdateDestroyAPIView):

    serializer_class = EditableFilterSerializer
    lookup_field = 'slug'
    lookup_url_kwarg = 'editable_filter'

    def get_queryset(self):
        return EditableFilter.objects.all()


class EditableFilterPagination(PageNumberPagination):

    def paginate_queryset(self, queryset, request, view=None):
        self.editable_filter = view.editable_filter
        return super(EditableFilterPagination, self).paginate_queryset(
            queryset, request, view=view)

    def get_paginated_response(self, data):
        return http.Response(OrderedDict([
            ('editable_filter', EditableFilterSerializer().to_representation(
                self.editable_filter)),
            ('count', self.page.paginator.count),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('results', data)
        ]))


class EditableFilterObjectsAPIView(generics.ListAPIView):

    pagination_class = EditableFilterPagination
    serializer_class = None # override in subclasses
    lookup_field = 'slug'
    lookup_url_kwarg = 'editable_filter'

    def get_queryset(self):
        return self.get_serializer_class().Meta.model.objects.all()

    def get(self, request, *args, **kwargs): #pylint: disable=unused-argument
        self.editable_filter = generics.get_object_or_404(
            EditableFilter.objects.all(),
            slug=self.kwargs[self.lookup_url_kwarg])
        return super(EditableFilterObjectsAPIView, self).get(
            request, *args, **kwargs)


class AccountListAPIView(EditableFilterObjectsAPIView):
    """
    Filtered list of ``EditableFilter``.

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
               "field": "text",
               "selector":"keepmatching"
           }]
        }
    """
    serializer_class = get_account_serializer()


class QuestionListAPIView(EditableFilterObjectsAPIView):
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
               "field": "text",
               "selector":"keepmatching"
           }]
        }
    """
    serializer_class = get_question_serializer()
