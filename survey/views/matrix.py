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

import json
import datetime

from django.core.urlresolvers import reverse
from django.views.generic import (View, TemplateView)

from django.http import HttpResponse
import django.db.models.manager
import django.db.models.query
import django.contrib.auth.models
from django.apps import apps as django_apps

from ..compat import csrf
from ..models import (Question,
                      Response,
                      Answer,
                      Portfolio,
                      SurveyModel,
                      QuestionCategory,
                      PortfolioPredicate,
                      QuestionCategoryPredicate)
from ..mixins import QuestionMixin, SurveyModelMixin
from ..settings import ACCOUNT_MODEL
from ..compat import csrf

class MatrixView(TemplateView):
    template_name = "survey/matrix.html"

    def get_context_data(self):
        return {
            'portfolio_api' :reverse('portfolio_api'),
            'questioncategory_api': reverse('questioncategory_api'),
        }

def select_keys(obj, ks):
    d = {}
    for k in ks:
        d[k] = getattr(obj, k)
    return d


def encode_json(obj):

    if isinstance(obj, django.contrib.auth.models.User):
        d = select_keys(obj, [
            'first_name',
            'last_name',
            'email',
            'username',
        ])
        d.update({
            'id': obj.email
        })
        return d
    if isinstance(obj, Response):
        return select_keys(obj, [
            'survey',
            'answers',
            'user',
        ])
    elif isinstance(obj, Answer):
        return select_keys(obj, [
            'created_at',
            'updated_at',
            'question',
            'index',
            'body',
        ])
    elif isinstance(obj, SurveyModel):
        return select_keys(obj, [
            'start_date',
            'end_date',
            'title',
            'description',
            'published',
            'quizz_mode',
            'one_response_only',
            'questions',
        ])
    elif isinstance(obj, Question):
        d = select_keys(obj, [
            'text',
            'question_type',
            'has_other',
            'choices',
            'order',
            'correct_answer',
            'required',
        ])
        d.update({
            'id': ':'.join([obj.survey.slug, str(obj.order)])
        })
        return d


    elif isinstance(obj, Portfolio):
        d = select_keys(obj, [
            'title',
            'slug',
        ])
        d.update({
            'predicates': obj.predicates.order_by('order')
        })
        return d
    elif isinstance(obj, QuestionCategory):
        d = select_keys(obj, [
            'title',
            'slug',
        ])
        d.update({
            'predicates': obj.predicates.order_by('order')
        })
        return d
    elif isinstance(obj, PortfolioPredicate):
        return select_keys(obj, [
            'operator',
            'operand',
            'property',
            'filterType',
        ])
    elif isinstance(obj, QuestionCategoryPredicate):
        return select_keys(obj, [
            'operator',
            'operand',
            'property',
            'filterType',
        ])

    elif isinstance(obj, datetime.datetime):
        return obj.isoformat()
    elif isinstance(obj, django.db.models.manager.Manager):
        return obj.all()
    elif isinstance(obj, django.db.models.query.QuerySet):
        return list(obj)
    else:
        return obj

def pretty_json(obj, *args, **kw):
    return json.dumps(obj, sort_keys=True, indent=4, separators=(',', ': '), *args, **kw)

class MatrixApi(View):
    def get(self, request):
        responses = Response.objects.all()

        return HttpResponse(pretty_json(responses, default=encode_json),
                            content_type='application/json')


class PortfolioView(TemplateView):
    template_name = "survey/categorize.html"

    def get_context_data(self, *args, **kwargs):
        context = super(PortfolioView, self).get_context_data(
            *args, **kwargs)
        context.update(csrf(self.request))
        context.update({
            'category_api': reverse('portfolio_api'),
        })
        return context

class QuestionCategoryView(TemplateView):
    template_name = "survey/categorize.html"

    def get_context_data(self, *args, **kwargs):
        context = super(QuestionCategoryView, self).get_context_data(
            *args, **kwargs)
        context.update(csrf(self.request))
        context.update({
            'category_api': reverse('questioncategory_api'),
        })
        return context



def get_account_model():
    """
    Returns the ``Account`` model that is active in this project.
    """
    try:
        return django_apps.get_model(ACCOUNT_MODEL)
    except ValueError:
        raise ImproperlyConfigured(
            "ACCOUNT_MODEL must be of the form 'app_label.model_name'")
    except LookupError:
        raise ImproperlyConfigured("ACCOUNT_MODEL refers to model '%s'"\
" that has not been installed" % ACCOUNT_MODEL)

class CategoryApi(View):
    # override in subclasses
    categoryModel = None
    predicateModel = None
    objectModel = None

    def get(self, request):

        categories = list(self.categoryModel.objects.all())
        # accounts = get_account_model().objects.all()
        objects = self.objectModel.objects.all()

        data = {
            'categories': categories,
            'objects': objects,
        }

        return HttpResponse(pretty_json(data, default=encode_json),
                            content_type='application/json')


    def post(self, request):
        category = json.loads(request.body)

        if category['slug'] is None:
            # create
            c = self.categoryModel(title=category['title'])
            c.save()
        else:
            # update
            c = self.categoryModel.objects.get(slug=category['slug'])
            c.title = category['title']
            c.save()


        # always update predicates
        c.predicates.all().delete()
        for i, predicateData in enumerate(category['predicates']):
            predicate = self.predicateModel(operator=predicateData['operator'],
                                            operand=predicateData['operand'],
                                            property=predicateData['property'],
                                            filterType=predicateData['filterType'],
                                            order=i,
                                            category=c)
            predicate.save()


        return HttpResponse(pretty_json(c, default=encode_json), content_type='application/json')

class PortfolioApi(CategoryApi):
    categoryModel = Portfolio
    predicateModel = PortfolioPredicate
    objectModel = get_account_model()

class QuestionCategoryApi(CategoryApi):
    categoryModel = QuestionCategory
    predicateModel = QuestionCategoryPredicate
    objectModel = Question


