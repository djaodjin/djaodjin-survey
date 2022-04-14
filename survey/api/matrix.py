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

import logging, re
from collections import OrderedDict

from django.db.models import F
from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import generics, response as http
from rest_framework.filters import SearchFilter
from rest_framework.pagination import PageNumberPagination

from ..compat import reverse
from ..mixins import MatrixMixin
from ..models import Answer, Matrix, EditableFilter
from ..utils import (get_account_model, get_account_serializer,
    get_question_serializer)
from .serializers import EditableFilterSerializer, MatrixSerializer


LOGGER = logging.getLogger(__name__)


class MatrixCreateAPIView(generics.ListCreateAPIView):
    """
    Lists matrices

    **Examples**:

    .. code-block:: http

        GET /api/matrix/ HTTP/1.1

    responds

    .. code-block:: json

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

    def post(self, request, *args, **kwargs):
        """
        Creates a new matrix

        .. code-block:: http

            POST /api/matrix/ HTTP/1.1

        .. code-block:: json

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

        responds

        .. code-block:: json

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
        #pylint:disable=useless-super-delegation
        return super(MatrixCreateAPIView, self).post(request, *args, **kwargs)


class MatrixDetailAPIView(MatrixMixin, generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieves a matrix of scores for cohorts aganist a metric.

    **Tags**: reporting

    **Examples**

    .. code-block:: http

        GET /api/matrix/languages HTTP/1.1

   responds

    .. code-block:: json

        [{
           "slug": "languages",
           "title": "All cohorts for all questions"
           "values": {
               "portfolio-a": 0.1,
               "portfolio-b": 0.5
           }
        }]
    """

    serializer_class = MatrixSerializer
    lookup_field = 'slug'
    lookup_url_kwarg = 'path'
    question_model = get_question_serializer().Meta.model

    def put(self, request, *args, **kwargs):
        """
        Updates a matrix of scores for cohorts against a metric

        **Tags**: reporting

        **Examples**

        .. code-block:: http

            PUT /api/matrix/languages HTTP/1.1

        .. code-block:: json

            {
              "title": "Average scores by supplier industry sub-sector",
              "cohorts": []
            }

        responds

        .. code-block:: json

            [{
              "slug": "languages",
              "title": "All cohorts for all questions"
              "values":{
                "portfolio-a": "0.1",
                 "portfolio-b": "0.5",
             }
            }]
        """
        #pylint:disable=useless-super-delegation
        return super(MatrixDetailAPIView, self).put(
            request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        """
        Deletes a matrix of scores for cohorts against a metric

        **Tags**: reporting

        **Examples**

        .. code-block:: http

            DELETE /api/matrix/languages HTTP/1.1
        """
        #pylint:disable=useless-super-delegation
        return super(MatrixDetailAPIView, self).put(
            request, *args, **kwargs)

    def aggregate_scores(self, metric, cohorts, cut=None, accounts=None):
        #pylint:disable=unused-argument,too-many-locals
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
                    if isinstance(cohort, EditableFilter):
                        includes, excludes = cohort.as_kwargs()
                        qs_accounts = accounts.filter(
                            **includes).exclude(**excludes)
                    else:
                        # If `matrix.cohorts is None`, the `cohorts` argument
                        # will be a list of single account objects.
                        qs_accounts = [cohort]
                    nb_accounts = len(qs_accounts)
                    if nb_accounts > 0:
                        nb_correct_answers = Answer.objects.filter(
                            question__in=questions,
                            sample__account__in=qs_accounts).filter(
                                measured=F('question__correct_answer')).count()
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
            # Implementation Note: switch cohorts from an queryset
            # of `EditableFilter` to a queryset of `Account` ...
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


class EditableFilterListAPIView(EditableFilterQuerysetMixin,
                                generics.ListCreateAPIView):
    """
    Lists fitlers

    **Tags**: reporting

    **Examples**

    .. code-block:: http

         GET /api/xia/matrix/filters HTTP/1.1

    responds

    .. code-block:: json

        {
            "count": 2,
            "previous": null,
            "next": null,
            "results": [
                {
                    "slug": "construction",
                    "title": "Construction",
                    "tags": "cohort",
                    "predicates": [
                    {
                        "rank": 0,
                        "operator": "contains",
                        "operand": "construction",
                        "field": "extra",
                        "selector": "keepmatching"
                    }
                    ],
                    "likely_metric": null
                },
                {
                    "slug": "boxes-and-enclosures",
                    "title": "Boxes and enclosures",
                    "tags": "metric",
                    "predicates": [
                    {
                        "rank": 0,
                        "operator": "startsWith",
                        "operand": "/metal/boxes-and-enclosures/",
                        "field": "path",
                        "selector": "keepmatching"
                     }
                     ],
                     "likely_metric": null
                }
            ]
        }
    """
    serializer_class = EditableFilterSerializer
    search_fields = (
        'tags',
    )
    filter_backends = (SearchFilter,)

    def post(self, request, *args, **kwargs):
        """
        Creates a fitler

        **Tags**: reporting

        **Examples**

        .. code-block:: http

             POST /api/xia/matrix/filters HTTP/1.1

        .. code-block:: json

            {
                "slug": "construction",
                "title": "Construction",
                "tags": "cohort",
                "predicates": [
                {
                    "rank": 0,
                    "operator": "contains",
                    "operand": "construction",
                    "field": "extra",
                    "selector": "keepmatching"
                }
                ],
                "likely_metric": null
            }

        responds

        .. code-block:: json

            {
                "slug": "construction",
                "title": "Construction",
                "tags": "cohort",
                "predicates": [
                {
                    "rank": 0,
                    "operator": "contains",
                    "operand": "construction",
                    "field": "extra",
                    "selector": "keepmatching"
                }
                ],
                "likely_metric": null
            }
        """
        #pylint:disable=useless-super-delegation
        return super(EditableFilterListAPIView, self).post(
            request, *args, **kwargs)


class EditableFilterDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieves a fitler

    **Tags**: reporting

    **Examples**

    .. code-block:: http

         GET /api/energy-utility/matrix/filters/suppliers HTTP/1.1

    responds

    .. code-block:: json

        {
            "slug": "suppliers",
            "title": "Energy utility suppliers",
            "tags": "cohort, aggregate",
            "predicates": [{
                "rank": 1,
                "operator": "contains",
                "operand": "Energy",
                "field": "extra",
                "selector": "keepmatching"
            }],
            "likely_metric": null
        }
    """
    serializer_class = EditableFilterSerializer
    lookup_field = 'slug'
    lookup_url_kwarg = 'editable_filter'

    def get_queryset(self):
        return EditableFilter.objects.all()

    def put(self, request, *args, **kwargs):
        """
        Updates a fitler

        **Tags**: reporting

        **Examples**

        .. code-block:: http

             PUT /api/energy-utility/matrix/filters/suppliers HTTP/1.1

        .. code-block:: json

            {
                "slug": "suppliers",
                "title": "Energy utility suppliers",
                "tags": "cohort, aggregate",
                "predicates": [{
                    "rank": 1,
                    "operator": "contains",
                    "operand": "Energy",
                    "field": "extra",
                    "selector": "keepmatching"
                }],
                "likely_metric": null
            }

        responds

        .. code-block:: json

            {
                "slug": "suppliers",
                "title": "Energy utility suppliers",
                "tags": "cohort, aggregate",
                "predicates": [{
                    "rank": 1,
                    "operator": "contains",
                    "operand": "Energy",
                    "field": "extra",
                    "selector": "keepmatching"
                }],
                "likely_metric": null
            }
        """
        #pylint:disable=useless-super-delegation
        return super(EditableFilterDetailAPIView, self).put(
            request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        """
        Deletes a fitler

        **Tags**: reporting

        **Examples**

        .. code-block:: http

             DELETE /api/energy-utility/matrix/filters/suppliers HTTP/1.1
        """
        #pylint:disable=useless-super-delegation
        return super(EditableFilterDetailAPIView, self).delete(
            request, *args, **kwargs)


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
    """
    List filter objects

    **Tags**: reporting

    **Examples**

    .. code-block:: http

         GET /api/xia/matrix/filters HTTP/1.1

    responds

    .. code-block:: json

        {
            "created_at": "2020-01-01T00:00:00Z",
            "measured": 12
        }
    """
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

    **Tags**: reporting

    **Examples**:

    .. code-block:: http

        GET /api/supplier-1/matrix/accounts/languages HTTP/1.1

    responds

    .. code-block:: json

        {
            "count": 1,
            "previous": null,
            "next": null,
            "results": [
            {
               "slug": "supplier-1",
               "full_name": "Supplier 1",
               "email": "supplier-1@localhost.localdomain"
           }]
        }
    """
    serializer_class = get_account_serializer()


class QuestionListAPIView(EditableFilterObjectsAPIView):
    """
    Filtered list of ``Question``.

    **Tags**: reporting

    **Examples**:

    .. code-block:: http

        GET /api/supplier-1/matrix/questions/languages HTTP/1.1

    responds

    .. code-block:: json

        {
            "count": 1,
            "previous": null,
            "next": null,
            "results": [
            {
               "operator": "contains",
               "operand": "language",
               "field": "text",
               "selector":"keepmatching"
            }]
        }
    """
    serializer_class = get_question_serializer()
