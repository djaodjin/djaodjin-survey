# Copyright (c) 2023, DjaoDjin inc.
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

from django.db import transaction
from django.db.models import F, Max, Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import generics, response as http, status
from rest_framework.mixins import CreateModelMixin
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.pagination import PageNumberPagination

from .. import settings
from ..compat import reverse, six
from ..mixins import (AccountMixin, CampaignMixin, DateRangeContextMixin,
    MatrixMixin, QuestionMixin, SampleMixin)
from ..models import (Answer, Matrix, EditableFilter,
    EditableFilterEnumeratedAccounts, Sample, Unit, UnitEquivalences)
from ..pagination import MetricsPagination
from ..utils import (datetime_or_now, get_accessible_accounts,
    get_benchmarks_enumerated, get_account_model, get_question_model,
    get_account_serializer, get_question_serializer)
from .serializers import (AccountsFilterAddSerializer,
    CompareQuestionSerializer, EditableFilterSerializer, MatrixSerializer,
    SampleBenchmarksSerializer)

LOGGER = logging.getLogger(__name__)

class BenchmarkMixin(QuestionMixin, DateRangeContextMixin, CampaignMixin,
                     AccountMixin):
    scale = 1
    default_unit = 'profiles'
    valid_units = ('percentage',)
    title = "Benchmarks"

    @property
    def unit(self):
        #pylint:disable=attribute-defined-outside-init
        if not hasattr(self, '_unit'):
            self._unit = self.default_unit
            param_unit = self.get_query_param('unit')
            if param_unit is not None and param_unit in self.valid_units:
                self._unit = param_unit
        return self._unit

    def get_accessible_accounts(self, grantees):
        return get_accessible_accounts(grantees, campaign=self.campaign)

    def get_questions(self, prefix):
        """
        Overrides CampaignContentMixin.get_questions to return a list
        of questions based on the answers available in the benchmarks samples.
        """
        qualified_prefix = prefix
        if not qualified_prefix.endswith(settings.DB_PATH_SEP):
            qualified_prefix = qualified_prefix + settings.DB_PATH_SEP

        questions_queryset = get_question_model().objects.filter(
            Q(path=prefix) | Q(path__startswith=qualified_prefix)).values(
            'pk', 'path', 'ui_hint', 'content__title',
            'default_unit__slug', 'default_unit__title',
            'default_unit__system')
        questions_by_key = {question['pk']: {
            'path': question['path'],
            'title': question['content__title'],
            'ui_hint': question['ui_hint'],
            'default_unit': Unit(
                slug=question['default_unit__slug'],
                title=question['default_unit__title'],
                system=question['default_unit__system']),
        } for question in questions_queryset}

        self.attach_results(questions_by_key)

        return list(six.itervalues(questions_by_key))

    def _attach_results(self, questions_by_key, accessible_accounts,
                        title, slug):
        samples = []
        if accessible_accounts:
            # Calling `get_completed_assessments_at_by` with an `accounts`
            # arguments evaluating to `False` will return all the latest
            # frozen samples.
            samples = Sample.objects.get_completed_assessments_at_by(
                self.campaign,
                start_at=self.start_at, ends_at=self.ends_at,
                accounts=accessible_accounts)

        # samples that will be counted in the benchmark
        if samples:
            questions_by_key = get_benchmarks_enumerated(
                samples, questions_by_key.keys(), questions_by_key)
            for question in six.itervalues(questions_by_key):
                if not 'benchmarks' in question:
                    question['benchmarks'] = []
                account_benchmark = {
                    'slug': slug,
                    'title': title,
                    'values': []
                }
                for key, val in six.iteritems(question.get('rate', {})):
                    account_benchmark['values'] += [(key, int(val))]
                question['benchmarks'] += [account_benchmark]
        else:
            # We need a 'benchamrks' key, otherwise the serializer
            # will raise a `KeyError` exception leading to a 500 error.
            for question in six.itervalues(questions_by_key):
                if not 'benchmarks' in question:
                    question['benchmarks'] = []

    def attach_results(self, questions_by_key, account=None):
        account_slug = "all"
        account_title = "All"
        if not account:
            account = self.account
            account_slug = account.slug
            account_title = account.printable_name
        accessible_accounts = self.get_accessible_accounts([account])
        self._attach_results(questions_by_key, accessible_accounts,
            account_title, account_slug)


class BenchmarkAPIView(BenchmarkMixin, generics.ListAPIView):
    """
    Aggregated benchmark for requested accounts

    **Examples**:

    .. code-block:: http

        GET /api/energy-utility/reporting/sustainability/benchmarks\
/sustainability HTTP/1.1

    responds

    .. code-block:: json


        {
          "count": 4,
          "results": []
        }
    """
    serializer_class = SampleBenchmarksSerializer
    pagination_class = MetricsPagination

    def get_serializer_context(self):
        context = super(BenchmarkAPIView, self).get_serializer_context()
        context.update({
            'prefix': self.db_path if self.db_path else settings.DB_PATH_SEP,
        })
        return context

    def get_queryset(self):
        return self.get_questions(self.db_path)


class BenchmarkIndexAPIView(BenchmarkAPIView):
    """
    Aggregated benchmark for requested accounts

    **Examples**:

    .. code-block:: http

        GET /api/energy-utility/reporting/sustainability/benchmarks HTTP/1.1

    responds

    .. code-block:: json


        {
          "count": 4,
          "results": []
        }
    """


class SampleBenchmarkMixin(SampleMixin, BenchmarkMixin):

    @property
    def campaign(self):
        #pylint:disable=attribute-defined-outside-init
        if not hasattr(self, '_campaign'):
            self._campaign = self.sample.campaign
        return self._campaign

    @property
    def ends_at(self):
        #pylint:disable=attribute-defined-outside-init
        if not hasattr(self, '_ends_at'):
            self._ends_at = (self.sample.created_at if self.sample.is_frozen
                else datetime_or_now())
        return self._ends_at

    def get_accessible_accounts(self, grantees):
        return get_account_model().objects.all()


class SampleBenchmarksAPIView(SampleBenchmarkMixin, generics.ListAPIView):
    """
    Benchmark a sub-tree of questions against peers

    **Examples**:

    .. code-block:: http

        GET /api/supplier-1/sample/46f66f70f5ad41b29c4df08f683a9a7a/benchmarks\
/sustainability HTTP/1.1

    responds

    .. code-block:: json


        {
          "count": 4,
          "results": []
        }
    """
    serializer_class = SampleBenchmarksSerializer
    pagination_class = MetricsPagination

    def get_serializer_context(self):
        context = super(SampleBenchmarksAPIView, self).get_serializer_context()
        context.update({
            'prefix': self.db_path if self.db_path else settings.DB_PATH_SEP,
        })
        return context

    def get_queryset(self):
        return self.get_questions(self.db_path)


class SampleBenchmarksIndexAPIView(SampleBenchmarksAPIView):
    """
    Benchmark against peers

    **Examples**:

    .. code-block:: http

        GET /api/supplier-1/sample/46f66f70f5ad41b29c4df08f683a9a7a/benchmarks\
 HTTP/1.1

    responds

    .. code-block:: json


        {
          "count": 4,
          "results": []
        }
    """


class CompareAPIView(DateRangeContextMixin, CampaignMixin, AccountMixin,
                     generics.ListAPIView):
    """
    Lists compared samples

    **Examples**:

    .. code-block:: http

        GET /api/energy-utility/reporting/sustainability/matrix/compare\
/sustainability HTTP/1.1

    responds

    .. code-block:: json


        {
          "count": 4,
          "results": []
        }
    """
    serializer_class = CompareQuestionSerializer

    @property
    def samples(self):
        """
        Samples to compare

        One per column
        """
        #pylint:disable=attribute-defined-outside-init
        if not hasattr(self, '_samples'):
            accessible_accounts = get_accessible_accounts(
                [self.account], campaign=self.campaign)
            if accessible_accounts:
                # Calling `get_completed_assessments_at_by` with an `accounts`
                # arguments evaluating to `False` will return all the latest
                # frozen samples.
                self._samples = Sample.objects.get_completed_assessments_at_by(
                    self.campaign,
                    start_at=self.start_at, ends_at=self.ends_at,
                    accounts=accessible_accounts)
            else:
                self._samples = Sample.objects.none()
        return self._samples

    @property
    def labels(self):
        """
        Labels for columns
        """
        #pylint:disable=attribute-defined-outside-init
        if not hasattr(self, '_labels'):
            self._labels = sorted([
                sample.account.printable_name for sample in self.samples])
        return self._labels

    @staticmethod
    def next_answer(answers_iterator, questions_by_key, extra_fields):
        answer = next(answers_iterator)
        question_pk = answer.question_id
        value = questions_by_key.get(question_pk)
        if not value:
            question = answer.question
            default_unit = question.default_unit
            value = {
                'path': question.path,
                'title': question.title,
                'rank': answer.rank,
                'required': answer.required,
                'default_unit': default_unit,
                'ui_hint': question.ui_hint,
            }
            for field_name in extra_fields:
                value.update({field_name: getattr(question, field_name)})
            questions_by_key.update({question_pk: value})
        else:
            default_unit = value.get('default_unit')

        if( answer.unit == default_unit or
            UnitEquivalences.objects.filter(
                source=default_unit, target=answer.unit).exists() or
            UnitEquivalences.objects.filter(
                source=answer.unit, target=default_unit).exists() ):
            # we have the answer we are looking for.
            nb_respondents = value.get('nb_respondents', 0) + 1
            value.update({'nb_respondents': nb_respondents})
        return answer

    def as_answer(self, key):
        return key

    @staticmethod
    def equiv_default_unit(values):
        results = []
        for val in values:
            found = False
            for resp in val:
                try:
                    if resp.is_equiv_default_unit:
                        found = {
                            'measured': resp.measured_text,
                            'unit': resp.unit,
                            'created_at': resp.created_at,
                            'collected_by': resp.collected_by,
                        }
                        break
                except AttributeError:
                    pass
            results += [[found]]
        return results

    def attach_results(self, questions_by_key, answers,
                       extra_fields=None):
        if extra_fields is None:
            extra_fields = []

        question = None
        values = []
        key = None
        answer = None
        keys_iterator = iter(self.labels)
        answers_iterator = iter(answers)
        try:
            answer = self.next_answer(answers_iterator,
                questions_by_key, extra_fields=extra_fields)
            question = answer.question
        except StopIteration:
            pass
        try:
            key = self.as_answer(next(keys_iterator))
        except StopIteration:
            pass
        # `answers` will be populated even when there is no `Answer` model
        # just so we can get the list of questions.
        # On the other hand self.labels will be an empty list if there are
        # no samples to compare.
        try:
            while answer:
                if answer.question != question:
                    try:
                        while key:
                            values += [[{}]]
                            key = self.as_answer(next(keys_iterator))
                    except StopIteration:
                        keys_iterator = iter(self.labels)
                        try:
                            key = self.as_answer(next(keys_iterator))
                        except StopIteration:
                            key = None
                    questions_by_key[question.pk].update({
                        'values': self.equiv_default_unit(values)})
                    values = []
                    question = answer.question

                if key and answer.sample.account.printable_name > key:
                    while answer.sample.account.printable_name > key:
                        values += [[{}]]
                        key = self.as_answer(next(keys_iterator))
                elif key and answer.sample.account.printable_name < key:
                    try:
                        try:
                            sample = values[-1][0].sample
                        except AttributeError:
                            sample = values[-1][0].get('sample')
                        if answer.sample != sample:
                            values += [[answer]]
                        else:
                            values[-1] += [answer]
                    except IndexError:
                        values += [[answer]]
                    try:
                        answer = self.next_answer(answers_iterator,
                            questions_by_key, extra_fields=extra_fields)
                    except StopIteration:
                        answer = None
                else:
                    try:
                        try:
                            sample = values[-1][0].sample
                        except AttributeError:
                            sample = values[-1][0].get('sample')
                        if answer.sample != sample:
                            values += [[answer]]
                        else:
                            values[-1] += [answer]
                    except IndexError:
                        values += [[answer]]
                    try:
                        answer = self.next_answer(answers_iterator,
                            questions_by_key, extra_fields=extra_fields)
                    except StopIteration:
                        answer = None
                    try:
                        key = self.as_answer(next(keys_iterator))
                    except StopIteration:
                        key = None
            while key:
                values += [[{}]]
                key = self.as_answer(next(keys_iterator))
        except StopIteration:
            pass
        if question:
            questions_by_key[question.pk].update({
                'values': self.equiv_default_unit(values)})


    def get_questions(self, prefix):
        """
        Overrides CampaignContentMixin.get_questions to return a list
        of questions based on the answers available in the compared samples.
        """
        if not prefix.endswith(settings.DB_PATH_SEP):
            prefix = prefix + settings.DB_PATH_SEP

        questions_by_key = {}
        if self.samples:
            self.attach_results(
                questions_by_key,
                Answer.objects.get_frozen_answers(
                    self.campaign, self.samples, prefix=prefix))

        return list(six.itervalues(questions_by_key))


    def get_serializer_context(self):
        context = super(CompareAPIView, self).get_serializer_context()
        context.update({
            'prefix': self.db_path if self.db_path else settings.DB_PATH_SEP,
        })
        return context

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        # Ready to serialize
        serializer = self.get_serializer_class()(
            queryset, many=True, context=self.get_serializer_context())

        return self.get_paginated_response(serializer.data)


    def get_paginated_response(self, data):
        return http.Response(OrderedDict([
            ('count', len(data)),
            ('results', data),
            ('units', {}),
            ('labels', self.labels),
        ]))

    def get_queryset(self):
        return self.get_questions(self.db_path)


class CompareIndexAPIView(CompareAPIView):
    """
    Lists compared samples

    **Examples**:

    .. code-block:: http

        GET /api/energy-utility/reporting/sustainability/matrix/compare HTTP/1.1

    responds

    .. code-block:: json


        {
          "count": 4,
          "results": []
        }
    """


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
        #pylint:disable=attribute-defined-outside-init
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
               "title": "Supplier 1",
               "extra": null,
               "predicates": [],
               "likely_metric": [],
               "results": []
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
              "title": "Supplier 1"
            }

        responds

        .. code-block:: json

            {
               "slug": "supplier-1",
               "title": "Supplier 1",
               "extra": null,
               "predicates": [],
               "likely_metric": [],
               "results": []
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
