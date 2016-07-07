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

from django.db import transaction
from rest_framework import serializers
from rest_framework.generics import get_object_or_404

from ..models import (Answer, Matrix, Portfolio, PortfolioPredicate, Question,
    Response, Question, SurveyModel)
from ..utils import get_account_model

#pylint:disable=old-style-class,no-init

class AnswerSerializer(serializers.ModelSerializer): #pylint: disable=no-init

    class Meta(object):
        model = Answer
        fields = ('created_at', 'body')


class QuestionSerializer(serializers.ModelSerializer):

    class Meta:
        model = Question
        fields = ('text', 'question_type', 'has_other', 'choices',
            'order', 'correct_answer', 'required')


class ResponseSerializer(serializers.ModelSerializer):

    answers = AnswerSerializer(many=True)

    class Meta(object):
        model = Response
        fields = ('slug', 'account', 'title', 'description', 'published',
            'quizz_mode', 'questions')
        read_only_fields = ('slug',)


class SurveyModelSerializer(serializers.ModelSerializer):

    questions = QuestionSerializer(many=True)

    class Meta(object):
        model = SurveyModel
        fields = ('slug', 'created_at', 'time_spent', 'is_frozen', 'answers')
        read_only_fields = ('slug',)


class PortfolioPredicateSerializer(serializers.ModelSerializer):

    rank = serializers.IntegerField(required=False)

    class Meta:
        model = PortfolioPredicate
        fields = ('rank', 'operator', 'operand', 'property', 'filterType')


class PortfolioSerializer(serializers.ModelSerializer):

    slug = serializers.CharField(required=False)
    predicates = PortfolioPredicateSerializer(many=True)

    class Meta:
        model = Portfolio
        fields = ('slug', 'title', 'tags', 'predicates')

    def create(self, validated_data):
        portfolio = Portfolio(
            title=validated_data['title'], tags=validated_data['tags'])
        with transaction.atomic():
            portfolio.save()
            for predicate in validated_data['predicates']:
                predicate, _ = PortfolioPredicate.objects.get_or_create(
                    rank=predicate['rank'],
                    operator=predicate['operator'],
                    operand=predicate['operand'],
                    property=predicate['property'],
                    filterType=predicate['filterType'])
                portfolio.predicates.add(predicate)
        return portfolio

    def update(self, instance, validated_data):
        portfolio = instance
        with transaction.atomic():
            portfolio.title = validated_data['title']
            portfolio.tags = validated_data['tags']
            portfolio.save()
            absents = set([item['pk']
                for item in instance.predicates.all().values('pk')])
            for idx, predicate in enumerate(validated_data['predicates']):
                predicate, _ = PortfolioPredicate.objects.get_or_create(
                    category=portfolio,
                    operator=predicate['operator'],
                    operand=predicate['operand'],
                    property=predicate['property'],
                    filterType=predicate['filterType'],
                defaults={'rank': idx})
                portfolio.predicates.add(predicate)
                absents = absents - set([predicate.pk])
            PortfolioPredicate.objects.filter(pk__in=absents).delete()
        return portfolio


class MatrixSerializer(serializers.ModelSerializer):

    slug = serializers.CharField(required=False)
    metric = PortfolioSerializer(required=False)
    cohorts = PortfolioSerializer(many=True)

    class Meta:
        model = Matrix
        fields = ('slug', 'title', 'metric', 'cohorts')

    def create(self, validated_data):
        matrix = Matrix(title=validated_data['title'])
        with transaction.atomic():
            matrix.save()
            portfolio_serializer = PortfolioSerializer()
            for cohort in validated_data['cohorts']:
                cohort = portfolio_serializer.create(cohort)
                matrix.predicates.add(cohort)
        return matrix

    def update(self, instance, validated_data):
        with transaction.atomic():
            instance.title = validated_data['title']
            if 'metric' in validated_data:
                instance.metric = get_object_or_404(Portfolio.objects.all(),
                    slug=validated_data['metric']['slug'])
            instance.save()
            absents = set([item['pk']
                for item in instance.cohorts.all().values('pk')])
            for cohort in validated_data['cohorts']:
                cohort = get_object_or_404(
                    Portfolio.objects.all(), slug=cohort['slug'])
                instance.cohorts.add(cohort)
                absents = absents - set([cohort.pk])
            instance.cohorts.remove(*list(absents))
        return instance


class AccountSerializer(serializers.ModelSerializer):

    class Meta:
        model = get_account_model()
        fields = ('username', 'first_name', 'last_name', 'email')
