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

import logging, re
from collections import OrderedDict

from django.core.urlresolvers import reverse
from django.db.models import F
from django.http import Http404
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

        [{
           "slug": "languages",
           "title": "All cohorts for all questions"
           "scores":{
               "portfolio-a": "0.1",
               "portfolio-b": "0.5",
           }
        }]
    """

    serializer_class = MatrixSerializer
    lookup_field = 'slug'
    lookup_url_kwarg = 'path'
    question_model = get_question_serializer().Meta.model

    def aggregate_scores(self, metric, cohorts, cut=None, accounts=None):
        #pylint:disable=unused-argument
        if accounts is None:
            accounts = get_account_model().objects.all()
        scores = {}
        if metric:
            assert 'metric' in metric.tags, \
                "filter '%s' is not tagged as a metric" % str(metric)
            includes, excludes = metric.as_kwargs()
            questions = self.question_model.objects.filter(
                **includes).exclude(**excludes)
            nb_questions = len(questions)
            if nb_questions > 0:
                for cohort in cohorts:
                    includes, excludes = cohort.as_kwargs()
                    qs_accounts = accounts.filter(**includes).exclude(
                        **excludes)
                    nb_accounts = len(qs_accounts)
                    if nb_accounts > 0:
                        nb_correct_answers = Answer.objects.filter(
                            question__in=questions,
                            response__account__in=qs_accounts).filter(
                                text=F('question__correct_answer')).count()
                        score = nb_correct_answers * 100 / (
                            nb_questions * nb_accounts)
                        LOGGER.debug("score for '%s' = (%d * 100) "\
                            "/ (%d * %d) = %f", str(cohort), nb_correct_answers,
                            nb_questions, nb_accounts, score)
                        assert score <= 100
                        scores.update({str(cohort): score})
        return {"scores": scores}

    @property
    def matrix(self):
        if not hasattr(self, '_matrix'):
            self._matrix = Matrix.objects.filter(
                slug=self.kwargs.get(self.matrix_url_kwarg)).first()
        return self._matrix

    def get_accounts(self):
        #pylint:disable=unused-argument,no-self-use
        return get_account_model().objects.all()

    def get_likely_metric(self, cohort_slug):
        """
        Returns a URL to a ``Matrix`` derived from *cohort*.

        Many times people will use the same name to either mean a cohort
        or a metric and expect the system will magically switch between
        both meaning. This is an attempt at magic.
        """
        likely_metric = None
        look = re.match(r"(\S+)(-\d+)", cohort_slug)
        if look:
            try:
                likely_metric = self.request.build_absolute_uri(
                    reverse('matrix_chart', args=(
                        EditableFilter.objects.get(slug=look.group(1)).slug,)))
            except EditableFilter.DoesNotExist:
                pass
        return likely_metric


    def get(self, request, *args, **kwargs):
        #pylint:disable=unused-argument,too-many-locals
        matrix = self.matrix
        if matrix:
            metric = self.matrix.metric
        else:
            parts = self.kwargs.get(self.matrix_url_kwarg).split('/')
            metric = get_object_or_404(EditableFilter, slug=parts[-1])
            matrix = Matrix.objects.filter(slug=parts[0]).first()
        if not matrix:
            raise Http404()

        cohort_serializer = EditableFilterSerializer
        cohorts = matrix.cohorts.exclude(tags__contains='aggregate')
        public_cohorts = matrix.cohorts.filter(tags__contains='aggregate')
        cut = matrix.cut
        if not cohorts:
            # We don't have any cohorts, let's show individual accounts instead.
            if cut:
                includes, excludes = cut.as_kwargs()
                accounts = self.get_accounts().filter(
                    **includes).exclude(**excludes)
            else:
                accounts = self.get_accounts()
            cohort_serializer = get_account_serializer()
            cohorts = accounts

        result = []
        scores = {}
        val = {
            'slug': metric.slug,
            'title': metric.title,
            'metric': EditableFilterSerializer().to_representation(metric),
            'cut': EditableFilterSerializer().to_representation(cut),
            'cohorts': cohort_serializer(many=True).to_representation(cohorts)}

        # In some case, a metric and cohort have a connection
        # and could have the same name.
        for cohort in val['cohorts']:
            likely_metric = self.get_likely_metric(cohort['slug'])
            if likely_metric:
                cohort['likely_metric'] = likely_metric

        scores.update(val)
        scores.update({"values": self.aggregate_scores(
            metric, cohorts, cut, accounts=self.get_accounts())})
        result += [scores]
        if public_cohorts:
            public_scores = {}
            public_scores.update(val)
            public_scores.update(
                {"cohorts": EditableFilterSerializer(
                    public_cohorts, many=True).data,
                 "values": self.aggregate_scores(metric, public_cohorts)})
            result += [public_scores]
        return http.Response(result)


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
