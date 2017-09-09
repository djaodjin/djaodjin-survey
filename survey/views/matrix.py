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

from django.core.urlresolvers import reverse
from django.shortcuts import get_object_or_404
from django.views.generic import TemplateView, DetailView, ListView

from ..compat import csrf
from survey.models import Response
from ..mixins import (EditableFilterMixin, MatrixMixin, MatrixQuerysetMixin,
    SurveyModelMixin)
from ..models import EditableFilter


class MatrixListView(MatrixQuerysetMixin, ListView):

    template_name = "survey/matrix/index.html"

    def get_context_data(self, *args, **kwargs):
        context = super(MatrixListView, self).get_context_data(*args, **kwargs)
        url_kwargs = self.get_url_kwargs()
        context.update({
            'editable_filter_api': reverse(
                'editable_filter_api_base', kwargs=url_kwargs),
            'matrix_api_base': reverse(
                'matrix_api_base', kwargs=url_kwargs),
        })
        return context


class MatrixDetailView(MatrixMixin, DetailView):

    template_name = "survey/matrix/matrix.html"

    def get_cohorts(self):
        """
        Returns the list of cohorts shown in the Matrix decorated
        with ``is_selected`` for cohorts the user shows.
        """
        selected = list(self.object.cohorts.all())
        cohorts = EditableFilter.objects.filter(tags='cohort')
        for cohort in cohorts:
            if cohort in selected:
                cohort.is_selected = True
        return cohorts

    def get_context_data(self, *args, **kwargs):
        context = super(MatrixDetailView, self).get_context_data(
            *args, **kwargs)
        metrics = EditableFilter.objects.filter(tags='metric')
        for metric in metrics:
            if metric == self.object.metric:
                metric.is_selected = True
        url_kwargs = self.get_url_kwargs()
        context.update({
            'cohorts': self.get_cohorts(),
            'metrics': metrics,
            'editable_filter_api_base': reverse(
                'editable_filter_api_base', kwargs=url_kwargs),
        })
        url_kwargs.update({self.matrix_url_kwarg: self.object})
        context.update({
            'matrix_api': reverse('matrix_api', kwargs=url_kwargs),
        })
        return context

    def get_object(self, queryset=None):
        if queryset is None:
            queryset = self.get_queryset()
        return get_object_or_404(
            queryset, slug=self.kwargs.get(self.matrix_url_kwarg))

    def get_template_names(self):
        names = super(MatrixDetailView, self).get_template_names()
        names.insert(0, "survey/matrix/%s.html" % self.object.slug)
        return names


class RespondentListView(SurveyModelMixin, ListView):

    model = Response
    template_name = 'survey/respondent_list.html'

    def get_queryset(self):
        return super(RespondentListView, self).get_queryset().filter(
            survey=self.get_survey(), is_frozen=True)

    def get_context_data(self, **kwargs):
        context = super(RespondentListView, self).get_context_data(**kwargs)
        context.update({'survey': self.get_survey()})
        return context


class EditableFilterView(EditableFilterMixin, TemplateView):

    api_url = None
    template_name = "survey/categorize.html"

    def get_context_data(self, *args, **kwargs):
        context = super(EditableFilterView, self).get_context_data(
            *args, **kwargs)
        context.update(csrf(self.request))
        url_kwargs = self.get_url_kwargs()
        url_kwargs.update({'editable_filter': self.editable_filter})
        context.update({
            'editable_filter_api': reverse(
                'editable_filter_api', kwargs=url_kwargs),
            'objects_api': reverse(self.api_url, kwargs=url_kwargs)
        })
        return context


class AccountListView(EditableFilterView):

    api_url = 'accounts_api'


class QuestionListView(EditableFilterView):

    api_url = 'questions_api'
