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
from django.views.generic import (View, TemplateView)

from django.http import HttpResponse
import django.db.models.manager
import django.db.models.query
import django.contrib.auth.models

from ..compat import csrf
from ..forms import QuestionForm
from ..models import Question, SurveyModel,Response, Answer
from ..mixins import QuestionMixin, SurveyModelMixin

import json
import datetime

class MatrixView(TemplateView):
    template_name = "survey/matrix.html"

    def get_context_data(self):
        return {}

def select_keys(obj, ks):
    d = {}
    for k in ks:
        d[k] = getattr(obj, k)
    print d
    return d


def encode_json(obj):
    print obj,type(obj)

    if isinstance(obj, django.contrib.auth.models.User):
        return select_keys(obj, [
            'first_name',
            'last_name',
            'email',
            'username',            
        ])
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
        return select_keys(obj, [
            'text',
            'question_type',
            'has_other',
            'choices',
            'order',
            'correct_answer',
            'required',
        ])
    elif isinstance(obj, datetime.datetime):
        return obj.isoformat()
    elif isinstance(obj, django.db.models.manager.Manager):
        return obj.all()
    elif isinstance(obj, django.db.models.query.QuerySet):
        return list(obj)
    else:
        return obj

def pretty_json(obj,*args, **kw):
    return json.dumps(obj, sort_keys=True,indent=4, separators=(',', ': '), *args, **kw)

class MatrixApi(View):
    def get(self, request):
        responses = Response.objects.filter(survey__id=2).all()
        return HttpResponse(pretty_json(responses,default=encode_json), content_type='application/json')

