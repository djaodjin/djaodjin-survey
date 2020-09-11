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

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.translation import ugettext_lazy as _
from rest_framework import serializers
from rest_framework.generics import get_object_or_404

from .. import settings
from ..models import (Answer, Campaign, EditableFilter,
    EditablePredicate, Matrix, Metric, Sample, Unit)
from ..utils import get_account_model, get_belongs_model, get_question_model


class AnswerSerializer(serializers.ModelSerializer):
    """
    Serializer of ``Answer`` when used individually.
    """
    metric = serializers.SlugRelatedField(required=False,
        queryset=Metric.objects.all(), slug_field='slug',
        help_text=_("Metric the measured field represents"))
    unit = serializers.SlugRelatedField(required=False,
        queryset=Unit.objects.all(), slug_field='slug',
        help_text=_("Unit the measured field is in"))
    measured = serializers.CharField(required=True, allow_blank=True,
        help_text=_("measurement in unit"))

    created_at = serializers.DateTimeField(read_only=True,
        help_text=_("Date/time of creation (in ISO format)"))
    # We are not using a `UserSerializer` here because retrieving profile
    # information must go through the profiles API.
    collected_by = serializers.SlugRelatedField(required=False,
        queryset=get_user_model().objects.all(), slug_field='username',
        help_text=_("User that collected the answer"))

    class Meta(object):
        model = Answer
        fields = ('metric', 'unit', 'measured', 'created_at', 'collected_by')
        read_only_fields = ('created_at', 'collected_by')


class QuestionCreateSerializer(serializers.ModelSerializer):

    title = serializers.CharField(allow_blank=True)
    default_metric = serializers.SlugRelatedField(slug_field='slug',
        queryset=Metric.objects.all())

    class Meta:
        model = get_question_model()
        fields = ('title', 'text', 'default_metric', 'correct_answer',
            'extra')


class QuestionDetailSerializer(QuestionCreateSerializer):

    class Meta:
        model = QuestionCreateSerializer.Meta.model
        fields = QuestionCreateSerializer.Meta.fields + ('path',)


class CampaignQuestionSerializer(serializers.ModelSerializer):

    title = serializers.CharField(allow_blank=True)
    default_metric = serializers.SlugRelatedField(slug_field='slug',
        queryset=Metric.objects.all())

    class Meta:
        model = get_question_model()
        fields = ('path', 'default_metric', 'title')


class SampleAnswerSerializer(AnswerSerializer):
    """
    Serializer of ``Answer`` when used in list.
    """
    question = CampaignQuestionSerializer()
    required = serializers.BooleanField(required=False)

    class Meta(object):
        model = AnswerSerializer.Meta.model
        fields = AnswerSerializer.Meta.fields + ('question', 'required')
        read_only_fields = AnswerSerializer.Meta.read_only_fields


class SampleSerializer(serializers.ModelSerializer):

    campaign = serializers.SlugRelatedField(slug_field='slug',
        queryset=Campaign.objects.all(), required=False,
        help_text=("Campaign this sample is part of."))
    account = serializers.SlugRelatedField(slug_field='slug',
        queryset=get_account_model().objects.all(), required=False,
        help_text=("Account this sample belongs to."))

    class Meta(object):
        model = Sample
        fields = ('slug', 'account', 'created_at',
            'campaign', 'time_spent', 'is_frozen')
        read_only_fields = ('slug', 'account', 'created_at',
            'campaign', 'time_spent')


class CampaignSerializer(serializers.ModelSerializer):

    account = serializers.SlugRelatedField(
        slug_field=settings.BELONGS_LOOKUP_FIELD,
        queryset=get_belongs_model().objects.all(),
        help_text=("Account this sample belongs to."))
    questions = CampaignQuestionSerializer(many=True)

    class Meta(object):
        model = Campaign
        fields = ('slug', 'account', 'title', 'description', 'active',
            'quizz_mode', 'questions')
        read_only_fields = ('slug',)


class CampaignCreateSerializer(serializers.ModelSerializer):

    # XXX The `slug` might be useful in order to create campaign aliases
    # (ref. feedback campaign)
    account = serializers.SlugRelatedField(
        slug_field=settings.BELONGS_LOOKUP_FIELD,
        queryset=get_belongs_model().objects.all())
    questions = QuestionCreateSerializer(many=True)

    class Meta(object):
        model = Campaign
        fields = ('account', 'title', 'description', 'active',
            'quizz_mode', 'questions')


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
