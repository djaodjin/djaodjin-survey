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

from django.core.urlresolvers import reverse
from django.shortcuts import get_object_or_404
from django.views.generic import TemplateView, DetailView, ListView

from ..compat import csrf
from ..mixins import MatrixMixin, PortfolioMixin
from ..models import Portfolio


class MatrixListView(MatrixMixin, ListView):

    template_name = "survey/matrix.html"

    def get_context_data(self, *args, **kwargs):
        context = super(MatrixListView, self).get_context_data(*args, **kwargs)
        context.update({
            'portfolio_api' :reverse('portfolio_api_base'),
            'questioncategory_api': reverse('questioncategory_api_base'),
        })
        return context


class MatrixDetailView(MatrixMixin, DetailView):

    template_name = "survey/matrix.html"

    def get_object(self, queryset=None):
        if queryset is None:
            queryset = self.get_queryset()
        return get_object_or_404(
            queryset, slug=self.kwargs.get(self.matrix_url_kwarg))

    def get_context_data(self, *args, **kwargs):
        context = super(MatrixDetailView, self).get_context_data(
            *args, **kwargs)
        selected = list(self.object.cohorts.all())
        cohorts = Portfolio.objects.filter(tags='cohort')
        for cohort in cohorts:
            if cohort in selected:
                cohort.is_selected = True
        metrics = Portfolio.objects.filter(tags='metric')
        for metric in metrics:
            if metric == self.object.metric:
                metric.is_selected = True
        context.update({
            'cohorts': cohorts,
            'metrics': metrics,
            'portfolio_api' :reverse('portfolio_api_base'),
            'questioncategory_api': reverse('questioncategory_api_base'),
            'matrix_api': reverse('matrix_api', args=(self.object,)),
        })
        return context


class PortfolioView(PortfolioMixin, TemplateView):

    api_url = None
    template_name = "survey/categorize.html"

    def get_context_data(self, *args, **kwargs):
        context = super(PortfolioView, self).get_context_data(
            *args, **kwargs)
        context.update(csrf(self.request))
        context.update({
            'filter_api': reverse('portfolio_api', args=(self.portfolio,)),
            'objects_api': reverse(self.api_url, args=(self.portfolio,))
        })
        return context

class AccountListView(PortfolioView):

    api_url = 'accounts_api'


class QuestionListView(PortfolioView):

    api_url = 'questioncategory_api'
