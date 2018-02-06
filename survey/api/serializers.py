# Copyright (c) 2018, DjaoDjin inc.
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
from django.utils import six
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404

from ..models import (Answer, Campaign, Choice, Matrix, EditableFilter,
    EditablePredicate, Question, Sample, Unit)
from ..utils import get_account_model

#pylint:disable=old-style-class,no-init

class AnswerSerializer(serializers.ModelSerializer):
    """
    Serializer of ``Answer`` when used individually.
    """

    measured = serializers.CharField(required=True)

    class Meta(object):
        model = Answer
        fields = ('created_at', 'measured')

    def validate_measured(self, data):
        unit = self.context['question'].default_metric.unit
        if unit.system == Unit.SYSTEM_ENUMERATED:
            try:
                data = Choice.objects.get(unit=unit, text=data).pk
            except Choice.DoesNotExist:
                choices = Choice.objects.filter(unit=unit)
                raise ValidationError(
                    "'%s' is not a valid choice. Expected one of %s." % (
                    data, [choice for choice in six.itervalues(choices)]))
        return data


class QuestionSerializer(serializers.ModelSerializer):

    unit = serializers.SlugRelatedField(slug_field='slug',
        queryset=Unit.objects.all())

    class Meta:
        model = Question
        fields = ('path', 'title', 'text', 'unit', 'correct_answer', 'extra')


class SampleAnswerSerializer(serializers.ModelSerializer):
    """
    Serializer of ``Answer`` when used in list.
    """
    question = serializers.SlugRelatedField(slug_field='path',
        queryset=Question.objects.all())
    measured = serializers.CharField(required=True)

    class Meta(object):
        model = Answer
        fields = ('question', 'measured')

    def validate_measured(self, data):
        if self.context['question'].unit.system == Unit.SYSTEM_ENUMERATED:
            try:
                data = Choice.objects.get(
                    unit=self.context['question'].unit, text=data).pk
            except Choice.DoesNotExist:
                choices = Choice.objects.filter(
                    unit=self.context['question'].unit)
                raise ValidationError(
                    "'%s' is not a valid choice. Expected one of %s." % (
                    data, [choice for choice in six.itervalues(choices)]))
        return data


class SampleSerializer(serializers.ModelSerializer):

    campaign = serializers.SlugRelatedField(source='survey', slug_field='slug',
        queryset=Campaign.objects.all(), required=False)
    account = serializers.SlugRelatedField(slug_field='slug',
        queryset=get_account_model().objects.all(), required=False)
    answers = SampleAnswerSerializer(many=True, required=False)

    class Meta(object):
        model = Sample
        fields = ('slug', 'account', 'created_at', 'is_frozen', 'campaign',
            'time_spent', 'answers')
        read_only_fields = ('slug', 'account', 'created_at', 'time_spent')


class CampaignSerializer(serializers.ModelSerializer):

    account = serializers.SlugRelatedField(slug_field='slug',
        queryset=get_account_model().objects.all())
    questions = QuestionSerializer(many=True)

    class Meta(object):
        model = Campaign
        fields = ('slug', 'account', 'title', 'description', 'active',
            'quizz_mode', 'questions')
        read_only_fields = ('slug',)


class EditablePredicateSerializer(serializers.ModelSerializer):

    rank = serializers.IntegerField(required=False)

    class Meta:
        model = EditablePredicate
        fields = ('rank', 'operator', 'operand', 'field', 'selector')


class EditableFilterSerializer(serializers.ModelSerializer):

    slug = serializers.CharField(required=False)
    likely_metric = serializers.SerializerMethodField()
    predicates = EditablePredicateSerializer(many=True)

    class Meta:
        model = EditableFilter
        fields = ('slug', 'title', 'tags', 'predicates', 'likely_metric')

    @staticmethod
    def get_likely_metric(obj):
        return getattr(obj, 'likely_metric', None)

    def create(self, validated_data):
        editable_filter = EditableFilter(
            title=validated_data['title'], tags=validated_data['tags'])
        with transaction.atomic():
            editable_filter.save()
            for predicate in validated_data['predicates']:
                predicate, _ = EditablePredicate.objects.get_or_create(
                    rank=predicate['rank'],
                    operator=predicate['operator'],
                    operand=predicate['operand'],
                    field=predicate['field'],
                    selector=predicate['selector'])
                editable_filter.predicates.add(predicate)
        return editable_filter

    def update(self, instance, validated_data):
        with transaction.atomic():
            instance.title = validated_data['title']
            instance.tags = validated_data['tags']
            instance.save()
            absents = set([item['pk']
                for item in instance.predicates.all().values('pk')])
            for idx, predicate in enumerate(validated_data['predicates']):
                predicate, _ = EditablePredicate.objects.get_or_create(
                    editable_filter=instance,
                    operator=predicate['operator'],
                    operand=predicate['operand'],
                    field=predicate['field'],
                    selector=predicate['selector'],
                    defaults={'rank': idx})
                instance.predicates.add(predicate)
                absents = absents - set([predicate.pk])
            EditablePredicate.objects.filter(pk__in=absents).delete()
        return instance


class MatrixSerializer(serializers.ModelSerializer):

    slug = serializers.CharField(required=False)
    metric = EditableFilterSerializer(required=False)
    cohorts = EditableFilterSerializer(many=True)
    cut = EditableFilterSerializer(required=False)

    class Meta:
        model = Matrix
        fields = ('slug', 'title', 'metric', 'cohorts', 'cut')

    def create(self, validated_data):
        matrix = Matrix(title=validated_data['title'])
        with transaction.atomic():
            matrix.save()
            editable_filter_serializer = EditableFilterSerializer()
            for cohort in validated_data['cohorts']:
                cohort = editable_filter_serializer.create(cohort)
                matrix.predicates.add(cohort)
        return matrix

    def update(self, instance, validated_data):
        with transaction.atomic():
            instance.title = validated_data['title']
            if 'metric' in validated_data:
                instance.metric = get_object_or_404(
                    EditableFilter.objects.all(),
                    slug=validated_data['metric']['slug'])
            instance.save()
            absents = set([item['pk']
                for item in instance.cohorts.all().values('pk')])
            for cohort in validated_data['cohorts']:
                cohort = get_object_or_404(
                    EditableFilter.objects.all(), slug=cohort['slug'])
                instance.cohorts.add(cohort)
                absents = absents - set([cohort.pk])
            instance.cohorts.remove(*list(absents))
        return instance


class AccountSerializer(serializers.ModelSerializer):

    class Meta:
        model = get_account_model()
        fields = ('slug', 'email')
