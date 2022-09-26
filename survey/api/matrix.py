# Copyright (c) 2022, DjaoDjin inc.
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

from django.core.exceptions import FieldError
from django.db import transaction
from django.db.models import F, Max, Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import generics, response as http, status
from rest_framework.mixins import CreateModelMixin
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.pagination import PageNumberPagination

from ..compat import reverse
from ..mixins import AccountMixin, MatrixMixin
from ..models import (Answer, Matrix, EditableFilter,
    EditableFilterEnumeratedAccounts)
from ..utils import (get_account_model, get_account_serializer,
    get_question_serializer)
from .serializers import (AccountsFilterAddSerializer,
    EditableFilterSerializer, MatrixSerializer)


LOGGER = logging.getLogger(__name__)


class MatrixCreateAPIView(generics.ListCreateAPIView):
    """
    Lists matrices

    **Examples**:

    .. code-block:: http

        GET /api/energy-utility/reporting/sustainability/matrix HTTP/1.1

    responds

    .. code-block:: json

        {
          "count": 1,
          "results": [
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
          ]
        }
    """
    serializer_class = MatrixSerializer

    def get_queryset(self):
        return Matrix.objects.all()

    def post(self, request, *args, **kwargs):
        """
        Creates a new matrix

        **Examples**:

        .. code-block:: http

            POST /api/energy-utility/reporting/sustainability/matrix HTTP/1.1

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

        GET /api/energy-utility/reporting/sustainability/matrix/languages HTTP/1.1

   responds

    .. code-block:: json

        {
           "slug": "languages",
           "title": "All cohorts for all questions",
           "values": {
               "portfolio-a": 0.1,
               "portfolio-b": 0.5
           }
        }
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

            PUT /api/energy-utility/reporting/sustainability/matrix/languages HTTP/1.1

        .. code-block:: json

            {
              "title": "Average scores by supplier industry sub-sector",
              "cohorts": []
            }

        responds

        .. code-block:: json

            {
              "slug": "languages",
              "title": "All cohorts for all questions",
              "cohorts": []
            }
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

            DELETE /api/energy-utility/reporting/sustainability/matrix/languages HTTP/1.1
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
        #pylint:disable=attribute-defined-outside-init
        if not hasattr(self, '_matrix'):
            self._matrix = Matrix.objects.filter(
                slug=self.kwargs.get(self.matrix_url_kwarg)).first()
        return self._matrix

    def get_accounts(self):
        #pylint:disable=unused-argument
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
            'cut': (EditableFilterSerializer().to_representation(cut)
                if cut else None),
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


class EditableFilterQuerysetMixin(AccountMixin):

    def get_queryset(self):
        return EditableFilter.objects.filter(
            Q(account__isnull=True) | Q(account=self.account)).order_by('slug')


class EditableFilterListAPIView(EditableFilterQuerysetMixin,
                                generics.ListAPIView):
    """
    Lists fitlers

    **Tags**: reporting

    **Examples**

    .. code-block:: http

         GET /api/energy-utility/filters HTTP/1.1

    responds

    .. code-block:: json

      {
          "count": 2,
          "next": null,
          "previous": null,
          "results": [{
              "slug": "boxes-and-enclosures",
              "title": "Boxes & enclosures",
              "extra": "",
              "predicates": [{
                  "rank": 0,
                  "operator": "startswith",
                  "operand": "/metal/boxes-and-enclosures",
                  "field": "extra",
                  "selector": "keepmatching"
              }],
              "likely_metric": null
          }]
      }
    """
    serializer_class = EditableFilterSerializer
    ordering_fields = ('slug',)
    search_fields = (
        'tags',
    )
    filter_backends = (SearchFilter, OrderingFilter)


class EditableFilterDetailAPIView(AccountMixin,
                                  generics.RetrieveUpdateDestroyAPIView):
    serializer_class = EditableFilterSerializer
    lookup_field = 'slug'
    lookup_url_kwarg = 'editable_filter'

    @property
    def editable_filter(self):
        #pylint:disable=attribute-defined-outside-init
        if not hasattr(self, '_editable_filter'):
            self._editable_filter = get_object_or_404(
                EditableFilter.objects.all(),
                account=self.account,
                slug=self.kwargs.get(self.lookup_url_kwarg))
        return self._editable_filter

    def get_object(self):
        editable_filter = self.editable_filter
        editable_filter.results = get_account_model().objects.filter(
            filters__editable_filter=self.editable_filter).annotate(
                rank=Max('filters__rank')).order_by('rank')
        return editable_filter


class AccountsFilterDetailAPIView(CreateModelMixin,
                                  EditableFilterDetailAPIView):
    """
    Retrieves a profiles fitler

    **Tags**: reporting

    **Examples**

    .. code-block:: http

         GET /api/energy-utility/filters/accounts/suppliers HTTP/1.1

    responds

    .. code-block:: json

         {
           "slug": "suppliers",
           "title": "Energy utility suppliers",
           "extra": null,
           "predicates": [],
           "likely_metric": null,
           "results": [{
                "facility": "Main factory",
                "fuel_type": "natural-gas",
                "allocation": "Energy utility",
                "created_at": null,
                "ends_at": null,
                "amount": 100,
                "unit": "mmbtu"
            }]
        }
    """
    def get_serializer_class(self):
        if self.request.method.lower() == 'post':
            return AccountsFilterAddSerializer
        return super(AccountsFilterDetailAPIView, self).get_serializer_class()

    def put(self, request, *args, **kwargs):
        """
        Updates a fitler

        **Tags**: reporting

        **Examples**

        .. code-block:: http

             PUT /api/energy-utility/filters/accounts/suppliers HTTP/1.1

        .. code-block:: json

            {
                "title": "Energy utility suppliers",
                "predicates": []
            }

        responds

        .. code-block:: json

         {
           "slug": "suppliers",
           "title": "Energy utility suppliers",
           "extra": null,
           "predicates": [],
           "likely_metric": null,
           "results": [{
                "facility": "Main factory",
                "fuel_type": "natural-gas",
                "allocation": "Energy utility",
                "created_at": null,
                "ends_at": null,
                "amount": 100,
                "unit": "mmbtu"
            }]
        }
        """
        #pylint:disable=useless-super-delegation
        return super(AccountsFilterDetailAPIView, self).put(
            request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        """
        Deletes a profiles fitler

        **Tags**: reporting

        **Examples**

        .. code-block:: http

             DELETE /api/energy-utility/filters/accounts/suppliers HTTP/1.1
        """
        #pylint:disable=useless-super-delegation
        return super(AccountsFilterDetailAPIView, self).delete(
            request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        """
        Updates a profiles fitler

        **Tags**: reporting

        **Examples**

        .. code-block:: http

             PUT /api/energy-utility/filters/accounts/suppliers HTTP/1.1

        .. code-block:: json

            {
                "full_name": "Main"
            }

        responds

        .. code-block:: json

            {
                "slug": "main",
                "full_name": "Main"
            }
        """
        #pylint:disable=useless-super-delegation
        return self.create(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Create the `Account` (if necessary) and add it to the filter.
        with transaction.atomic():
            account_slug = serializer.validated_data.get('slug')
            extra = serializer.validated_data.get('extra')
            if account_slug:
                account_queryset = get_account_model().objects.all()
                account_lookup_field = settings.ACCOUNT_LOOKUP_FIELD
                filter_args = {account_lookup_field: account_slug}
                account = get_object_or_404(account_queryset, **filter_args)
            else:
                account = get_account_model().objects.create(
                    full_name=serializer.validated_data.get('full_name'),
                    extra=extra)
            last_rank = EditableFilterEnumeratedAccounts.objects.filter(
                editable_filter=self.editable_filter).aggregate(
                Max('rank')).get('rank__max')
            if not last_rank:
                last_rank = 0
            enum_account = EditableFilterEnumeratedAccounts.objects.create(
                account=account,
                editable_filter=self.editable_filter,
                rank=last_rank + 1)
            account.rank = enum_account.rank

        account_serializer = get_account_serializer()()
        headers = self.get_success_headers(serializer.data)
        return http.Response(account_serializer.to_representation(account),
            status=status.HTTP_201_CREATED, headers=headers)


class AccountsFilterEnumeratedAPIView(generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieves a profile in an enumerated profiles filter

    **Tags**: reporting

    **Examples**

    .. code-block:: http

         GET /api/energy-utility/filters/accounts/suppliers/1 HTTP/1.1

    responds

    .. code-block:: json

         {
           "slug": "main-factory",
           "full_name": "Main factory"
         }
    """
    lookup_field = 'rank'
    serializer_class = AccountsFilterAddSerializer

    def get_queryset(self):
        queryset = EditableFilterEnumeratedAccounts.objects.filter(
            editable_filter__slug=self.kwargs.get('editable_filter'))
        return queryset

    def get_object(self):
        """
        Returns the object the view is displaying.

        You may want to override this if you need to provide non-standard
        queryset lookups.  Eg if objects are referenced using multiple
        keyword arguments in the url conf.
        """
        queryset = self.filter_queryset(self.get_queryset())

        # Perform the lookup filtering.
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field

        assert lookup_url_kwarg in self.kwargs, (
            'Expected view %s to be called with a URL keyword argument '
            'named "%s". Fix your URL conf, or set the `.lookup_field` '
            'attribute on the view correctly.' %
            (self.__class__.__name__, lookup_url_kwarg)
        )

        filter_kwargs = {self.lookup_field: self.kwargs[lookup_url_kwarg]}
        obj = get_object_or_404(queryset, **filter_kwargs)

        # May raise a permission denied
        self.check_object_permissions(self.request, obj)

        return obj


    def put(self, request, *args, **kwargs):
        """
        Updates a profile in an enumerated profiles filter

        **Tags**: reporting

        **Examples**

        .. code-block:: http

             PUT /api/energy-utility/filters/accounts/suppliers/1 HTTP/1.1

        .. code-block:: json

            {
                "full_name": "Main factory"
            }

        responds

        .. code-block:: json

            {
                "slug": "main-factory",
                "full_name": "Main factory"
            }
        """
        #pylint:disable=useless-parent-delegation
        return super(AccountsFilterEnumeratedAPIView, self).put(
            request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        """
        Deletes a profile in an enumerated profiles filter

        **Tags**: reporting

        **Examples**

        .. code-block:: http

             DELETE /api/energy-utility/filters/accounts/suppliers/1 HTTP/1.1
        """
        #pylint:disable=useless-parent-delegation
        return super(AccountsFilterEnumeratedAPIView, self).delete(
            request, *args, **kwargs)


class QuestionsFilterDetailAPIView(EditableFilterDetailAPIView):
    """
    Retrieves a questions fitler

    **Tags**: reporting

    **Examples**

    .. code-block:: http

         GET /api/energy-utility/filters/questions/governance HTTP/1.1

    responds

    .. code-block:: json

        {
            "slug": "governance",
            "title": "Governance questions",
            "predicates": [{
                "rank": 1,
                "operator": "contains",
                "operand": "Energy",
                "field": "extra",
                "selector": "keepmatching"
            }]
        }
    """

    def put(self, request, *args, **kwargs):
        """
        Updates a questions fitler

        **Tags**: reporting

        **Examples**

        .. code-block:: http

             PUT /api/energy-utility/filters/questions/governance HTTP/1.1

        .. code-block:: json

            {
                "slug": "governance",
                "title": "Governance questions",
                "predicates": [{
                    "rank": 1,
                    "operator": "contains",
                    "operand": "Energy",
                    "field": "extra",
                    "selector": "keepmatching"
                }]
            }

        responds

        .. code-block:: json

            {
                "slug": "governance",
                "title": "Governance questions",
                "predicates": [{
                    "rank": 1,
                    "operator": "contains",
                    "operand": "Energy",
                    "field": "extra",
                    "selector": "keepmatching"
                }]
            }
        """
        #pylint:disable=useless-super-delegation
        return super(QuestionsFilterDetailAPIView, self).put(
            request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        """
        Deletes a questions fitler

        **Tags**: reporting

        **Examples**

        .. code-block:: http

             DELETE /api/energy-utility/filters/questions/governance HTTP/1.1
        """
        #pylint:disable=useless-super-delegation
        return super(QuestionsFilterDetailAPIView, self).delete(
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


class EditableFilterObjectsAPIView(generics.ListCreateAPIView):
    """
    Base class to filter accounts and questions
    """
#    pagination_class = EditableFilterPagination
    serializer_class = None # override in subclasses
    lookup_field = 'slug'
    lookup_url_kwarg = 'editable_filter'

    def get_queryset(self):
        return self.get_serializer_class().Meta.model.objects.all()

    def post(self, request, *args, **kwargs):
        """
        Creates a fitler

        **Tags**: reporting

        **Examples**

        .. code-block:: http

             POST /api/energy-utility/filters HTTP/1.1

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
        return super(EditableFilterObjectsAPIView, self).post(
            request, *args, **kwargs)


class AccountsFilterListAPIView(EditableFilterObjectsAPIView):
    """
    Lists profiles filters

    **Tags**: reporting

    **Examples**:

    .. code-block:: http

        GET /api/supplier-1/filters/accounts HTTP/1.1

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
    serializer_class = EditableFilterSerializer

    def post(self, request, *args, **kwargs):
        """
        Creates a profiles fitler

        **Tags**: reporting

        **Examples**

        .. code-block:: http

             POST /api/energy-utility/filters/accounts HTTP/1.1

        .. code-block:: json

            {
            }

        responds

        .. code-block:: json

            {
               "slug": "supplier-1",
               "printable_name": "Supplier 1",
               "extra": null
            }
        """
        #pylint:disable=useless-super-delegation
        return super(AccountsFilterListAPIView, self).post(
            request, *args, **kwargs)


class QuestionsFilterListAPIView(EditableFilterObjectsAPIView):
    """
    Lists questions filters

    **Tags**: reporting

    **Examples**:

    .. code-block:: http

        GET /api/supplier-1/filters/questions HTTP/1.1

    responds

    .. code-block:: json

        {
            "count": 1,
            "previous": null,
            "next": null,
            "results": [{
              "path": "/construction/product-design",
              "title": "Product Design",
              "default_unit": "assessment",
              "ui_hint": "radio"
            }]
        }
    """
    serializer_class = get_question_serializer()

    def post(self, request, *args, **kwargs):
        """
        Creates a questions fitler

        **Tags**: reporting

        **Examples**

        .. code-block:: http

             POST /api/energy-utility/filters/questions HTTP/1.1

        .. code-block:: json

            {
                "title": "Construction",
                "default_unit": "assessment",
                "path": "/construction/product-design"
            }

        responds

        .. code-block:: json

            {
                "title": "Construction",
                "default_unit": "assessment",
                "path": "/construction/product-design"
            }
        """
        #pylint:disable=useless-super-delegation
        return super(QuestionsFilterListAPIView, self).post(
            request, *args, **kwargs)
