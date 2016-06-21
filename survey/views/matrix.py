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

from django.core.exceptions import ImproperlyConfigured
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
from ..settings import ACCOUNT_MODEL


class MatrixView(TemplateView):
    template_name = "survey/matrix.html"

    def get_context_data(self):
        return {
            'portfolio_api' :reverse('portfolio_api'),
            'questioncategory_api': reverse('questioncategory_api'),
        }

def select_keys(obj, key_selectors):
    result = {}
    for key in key_selectors:
        result[key] = getattr(obj, key)
    return result


def encode_json(obj):
    data = None
    if isinstance(obj, django.contrib.auth.models.User):
        data = select_keys(obj, [
            'first_name',
            'last_name',
            'email',
            'username',
        ])
        data.update({
            'id': obj.email
        })
    if isinstance(obj, Response):
        data = select_keys(obj, [
            'survey',
            'answers',
            'user',
        ])
    elif isinstance(obj, Answer):
        data = select_keys(obj, [
            'created_at',
            'updated_at',
            'question',
            'index',
            'body',
        ])
    elif isinstance(obj, SurveyModel):
        data = select_keys(obj, [
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
        data = select_keys(obj, [
            'text',
            'question_type',
            'has_other',
            'choices',
            'order',
            'correct_answer',
            'required',
        ])
        data.update({
            'id': ':'.join([obj.survey.slug, str(obj.order)])
        })

    elif isinstance(obj, Portfolio):
        data = select_keys(obj, [
            'title',
            'slug',
        ])
        data.update({
            'predicates': obj.predicates.order_by('order')
        })
    elif isinstance(obj, QuestionCategory):
        data = select_keys(obj, [
            'title',
            'slug',
        ])
        data.update({
            'predicates': obj.predicates.order_by('order')
        })
    elif isinstance(obj, PortfolioPredicate):
        data = select_keys(obj, [
            'operator',
            'operand',
            'property',
            'filterType',
        ])
    elif isinstance(obj, QuestionCategoryPredicate):
        data = select_keys(obj, [
            'operator',
            'operand',
            'property',
            'filterType',
        ])

    elif isinstance(obj, datetime.datetime):
        data = obj.isoformat()
    elif isinstance(obj, django.db.models.manager.Manager):
        data = obj.all()
    elif isinstance(obj, django.db.models.query.QuerySet):
        data = list(obj)
    else:
        data = obj
    return data


def pretty_json(obj, *args, **kw):
    return json.dumps(obj, sort_keys=True, indent=4,
        separators=(',', ': '), *args, **kw)

class MatrixApi(View):

    @staticmethod
    def get(request, *args, **kwargs): #pylint:disable=unused-argument
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
    category_model = None
    predicate_model = None
    object_model = None

    def get(self, request): #pylint: disable=unused-argument

        categories = list(self.category_model.objects.all())
        # accounts = get_account_model().objects.all()
        objects = self.object_model.objects.all()

        data = {
            'categories': categories,
            'objects': objects,
        }

        return HttpResponse(pretty_json(data, default=encode_json),
                            content_type='application/json')


    def post(self, request):
        category = json.loads(request.body)

        if self.category_model is None:
            raise ImproperlyConfigured(
                "%s.category_model must be defined", self.__class__.name)
        if self.predicate_model is None:
            raise ImproperlyConfigured(
                "%s.predicate_model must be defined", self.__class__.name)

        if category['slug'] is None:
            # create
            #pylint:disable=not-callable
            catmodel = self.category_model(title=category['title'])
            catmodel.save()
        else:
            # update
            catmodel = self.category_model.objects.get(slug=category['slug'])
            catmodel.title = category['title']
            catmodel.save()


        # always update predicates
        catmodel.predicates.all().delete()
        for idx, predicate_data in enumerate(category['predicates']):
            #pylint:disable=not-callable
            predicate = self.predicate_model(
                operator=predicate_data['operator'],
                operand=predicate_data['operand'],
                property=predicate_data['property'],
                filterType=predicate_data['filterType'],
                order=idx,
                category=catmodel)
            predicate.save()

        return HttpResponse(pretty_json(catmodel, default=encode_json),
            content_type='application/json')

class PortfolioApi(CategoryApi):
    category_model = Portfolio
    predicate_model = PortfolioPredicate
    object_model = get_account_model()

class QuestionCategoryApi(CategoryApi):
    category_model = QuestionCategory
    predicate_model = QuestionCategoryPredicate
    object_model = Question


