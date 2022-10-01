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

from django.db import transaction
from django.template.defaultfilters import slugify
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404

from .. import settings
from ..compat import gettext_lazy as _, reverse, six
from ..helpers import extra_as_internal
from ..models import (Answer, Campaign, Choice,
    EditableFilter, EditablePredicate, Matrix, PortfolioDoubleOptIn,
    Sample, Unit)
from ..utils import (get_account_model, get_belongs_model, get_question_model,
    get_account_serializer)


class EnumField(serializers.Field):
    """
    Treat a ``PositiveSmallIntegerField`` as an enum.
    """
    choices = {}
    inverted_choices = {}

    def __init__(self, choices, *args, **kwargs):
        self.choices = dict(choices)
        self.inverted_choices = {
            slugify(val): key for key, val in six.iteritems(self.choices)}
        super(EnumField, self).__init__(*args, **kwargs)

    def to_representation(self, value):
        if isinstance(value, list):
            result = [slugify(self.choices.get(item, None)) for item in value]
        else:
            result = slugify(self.choices.get(value, None))
        return result

    def to_internal_value(self, data):
        if isinstance(data, list):
            result = [self.inverted_choices.get(item, None) for item in data]
        else:
            result = self.inverted_choices.get(data, None)
        if result is None:
            if not data:
                raise ValidationError(_("This field cannot be blank."))
            raise ValidationError(_("'%(data)s' is not a valid choice."\
                " Expected one of %(choices)s.") % {'data': data,
                    'choices': list(six.iterkeys(self.inverted_choices))})
        return result


class NoModelSerializer(serializers.Serializer):

    def create(self, validated_data):
        raise RuntimeError('`create()` should not be called.')

    def update(self, instance, validated_data):
        raise RuntimeError('`update()` should not be called.')


class AccountSerializer(serializers.ModelSerializer):

    slug = serializers.SerializerMethodField()
    printable_name = serializers.SerializerMethodField(read_only=True,
        help_text=_("Name that can be safely used for display in HTML pages"))
    picture = serializers.SerializerMethodField(read_only=True,
        help_text=_("URL location of the profile picture"))
    extra = serializers.SerializerMethodField(read_only=True,
        help_text=_("Extra meta data (can be stringify JSON)"))
    rank = serializers.SerializerMethodField(read_only=True,
        help_text=_("rank in filter"))

    class Meta:
        model = get_account_model()
        fields = ('slug', 'printable_name', 'picture', 'extra', 'rank')

    @staticmethod
    def get_slug(obj):
        if hasattr(obj, 'slug'):
            return obj.slug
        return obj.username

    @staticmethod
    def get_printable_name(obj):
        try:
            return obj.printable_name
        except AttributeError:
            pass
        return obj.get_full_name()

    @staticmethod
    def get_picture(obj):
        try:
            return obj.picture
        except:
            pass
        return None

    @staticmethod
    def get_extra(obj):
        extra = extra_as_internal(obj)
        return extra

    @staticmethod
    def get_rank(obj):
        try:
            return obj.rank
        except AttributeError:
            pass
        return 0


class AnswerSerializer(serializers.ModelSerializer):
    """
    Serializer of ``Answer`` when used individually.
    """
    unit = serializers.SlugRelatedField(required=False, allow_null=True,
        queryset=Unit.objects.all(), slug_field='slug',
        help_text=_("Unit the measured field is in"))
    measured = serializers.CharField(required=True, allow_null=True,
        allow_blank=True, help_text=_("measurement in unit"))

    created_at = serializers.DateTimeField(read_only=True,
        help_text=_("Date/time of creation (in ISO format)"))
    # We are not using a `UserSerializer` here because retrieving profile
    # information must go through the profiles API.
    collected_by = serializers.SlugRelatedField(read_only=True,
        required=False, slug_field='username',
        help_text=_("User that collected the answer"))

    class Meta(object):
        model = Answer
        fields = ('unit', 'measured', 'created_at', 'collected_by')
        read_only_fields = ('created_at', 'collected_by')


class ChoiceSerializer(serializers.ModelSerializer):

    class Meta:
        model = Choice
        fields = ('text', 'descr')
        read_only_fields = ('text', 'descr')


class UnitSerializer(serializers.ModelSerializer):

    system = EnumField(choices=Unit.SYSTEMS,
        help_text=_("One of standard (metric system), imperial,"\
            " rank, enum, or freetext"))
    choices = ChoiceSerializer(many=True, required=False)

    class Meta:
        model = Unit
        fields = ('slug', 'title', 'system', 'choices')
        read_only_fields = ('slug', 'choices',)


class QuestionCreateSerializer(serializers.ModelSerializer):

    title = serializers.CharField(allow_blank=True)
    default_unit = serializers.SlugRelatedField(slug_field='slug',
        queryset=Unit.objects.all(),
        help_text=_("Default unit for measured field when none is specified"))

    class Meta:
        model = get_question_model()
        fields = ('title', 'text', 'default_unit', 'correct_answer',
            'extra')


class QuestionDetailSerializer(QuestionCreateSerializer):

    class Meta:
        model = QuestionCreateSerializer.Meta.model
        fields = QuestionCreateSerializer.Meta.fields + ('path',)


class CampaignQuestionSerializer(serializers.ModelSerializer):
    """
    Serializer of ``Question`` when used in a list of answers
    """
    title = serializers.CharField(allow_blank=True,
        help_text=_("Short description"))
    default_unit = UnitSerializer()
    ui_hint = EnumField(choices=get_question_model().UI_HINTS,
        help_text=_("Hint for the user interface on"\
            " how to present the input field"))

    class Meta:
        model = get_question_model()
        fields = ('path', 'title', 'default_unit', 'ui_hint')


class SampleAnswerSerializer(AnswerSerializer):
    """
    Serializer of ``Answer`` when used in list.
    """
    question = CampaignQuestionSerializer(
        help_text=_("Question the answer refers to"))
    required = serializers.BooleanField(required=False,
        help_text=_("Whether an answer is required or not."))

    class Meta(object):
        model = AnswerSerializer.Meta.model
        fields = AnswerSerializer.Meta.fields + ('question', 'required')
        read_only_fields = AnswerSerializer.Meta.read_only_fields + (
            'required',)


class SampleCreateSerializer(serializers.ModelSerializer):

    campaign = serializers.SlugRelatedField(slug_field='slug',
        queryset=Campaign.objects.all(), required=False,
        help_text=("Campaign this sample is part of."))

    class Meta(object):
        model = Sample
        fields = ('campaign',)


class SampleSerializer(SampleCreateSerializer):

    campaign = serializers.SlugRelatedField(slug_field='slug',
        read_only=True, allow_null=True,
        help_text=("Campaign this sample is part of."))
    account = serializers.SlugRelatedField(slug_field='slug',
        read_only=True, required=False,
        help_text=("Account this sample belongs to."))
    location = serializers.URLField(read_only=True, allow_null=True,
        help_text=("URL at which the response is visible."))

    class Meta(object):
        model = Sample
        fields = ('campaign', 'slug', 'account', 'created_at',
            'updated_at', 'is_frozen', 'location')
        read_only_fields = ('campaign', 'slug', 'account', 'created_at',
            'updated_at', 'is_frozen', 'location')

    @staticmethod
    def get_location(obj):
        return getattr(obj, 'location', None)


class CampaignSerializer(serializers.ModelSerializer):
    """
    Short description of the campaign.
    """

    account = serializers.SlugRelatedField(
        slug_field=settings.BELONGS_LOOKUP_FIELD,
        queryset=get_belongs_model().objects.all(),
        help_text=("Account this sample belongs to."))

    class Meta(object):
        model = Campaign
        fields = ('slug', 'account', 'title', 'description', 'active',)
        read_only_fields = ('slug',)


class CampaignDetailSerializer(serializers.ModelSerializer):

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

    questions = QuestionCreateSerializer(many=True, required=False)

    class Meta(object):
        model = Campaign
        fields = ('slug', 'title', 'description', 'quizz_mode', 'questions')
        read_only_fields = ('slug',)


class DatapointSerializer(AnswerSerializer):
    """
    Serializer of ``Answer`` when used to retrieve data points.
    """
    account = serializers.SerializerMethodField()

    class Meta(object):
        model = AnswerSerializer.Meta.model
        fields = AnswerSerializer.Meta.fields + ('account',)

    @staticmethod
    def get_account(obj):
        serializer_class = get_account_serializer()
        return serializer_class().to_representation(obj.sample.account)


class EditableFilterAnswerSerializer(AnswerSerializer):
    """
    Serializer of ``Answer`` when used to create data points.
    """
    slug = serializers.SlugRelatedField(slug_field='slug',
        queryset=get_account_model().objects.all(),
        help_text=("Account this sample belongs to."))
    unit = serializers.SlugRelatedField(
        queryset=Unit.objects.all(), slug_field='slug',
        help_text=_("Unit the measured field is in"))

    class Meta(object):
        model = AnswerSerializer.Meta.model
        fields = AnswerSerializer.Meta.fields + ('slug',)


class EditableFilterValuesCreateSerializer(NoModelSerializer):

    baseline_at = serializers.CharField(required=False)
    created_at = serializers.CharField()
    items = EditableFilterAnswerSerializer(many=True)

    class Meta(object):
        fields = ('baseline_at', 'created_at', 'items',)


class EditablePredicateSerializer(serializers.ModelSerializer):

    rank = serializers.IntegerField(required=False)

    class Meta:
        model = EditablePredicate
        fields = ('rank', 'operator', 'operand', 'field', 'selector')


class EditableFilterSerializer(serializers.ModelSerializer):

    slug = serializers.CharField(required=False)
    likely_metric = serializers.SerializerMethodField()
    predicates = EditablePredicateSerializer(many=True, required=False)
    results = get_account_serializer()(many=True, required=False) # XXX do we still need this field?

    class Meta:
        model = EditableFilter
        fields = ('slug', 'title', 'extra', 'predicates', 'likely_metric',
                  'results')

    @staticmethod
    def get_likely_metric(obj):
        return getattr(obj, 'likely_metric', None)

    def create(self, validated_data):
        editable_filter = EditableFilter(
            title=validated_data['title'], extra=validated_data.get('extra'))
        with transaction.atomic():
            editable_filter.save()
            for predicate in validated_data.get('predicates', []):
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
            instance.extra = validated_data['extra']
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


class KeyValueTuple(serializers.ListField):

    child = serializers.CharField() # XXX (String, Integer)
    min_length = 3
    max_length = 3


class TableSerializer(NoModelSerializer):

    key = serializers.CharField(
        help_text=_("Unique key in the table for the data series"))
    values = serializers.ListField(
        child=KeyValueTuple(),
        help_text="Datapoints in the serie")


class MetricsSerializer(NoModelSerializer):

    scale = serializers.FloatField(required=False,
        help_text=_("The scale of the number reported in the tables (ex: 1000"\
        " when numbers are reported in thousands of dollars)"))
    unit = serializers.CharField(required=False,
        help_text=_("Three-letter ISO 4217 code for currency unit (ex: usd)"))
    title = serializers.CharField(
        help_text=_("Title for the table"))
    table = TableSerializer(many=True)


class InviteeSerializer(NoModelSerializer):

    slug = serializers.SlugField()
    full_name = serializers.CharField()
    email = serializers.EmailField(required=False)
    printable_name = serializers.SerializerMethodField()

    @staticmethod
    def get_printable_name(obj):
        return str(obj.full_name)


class PortfolioGrantCreateSerializer(serializers.ModelSerializer):

    accounts = serializers.SlugRelatedField(required=False, many=True,
        queryset=get_account_model().objects.all(),
        slug_field=settings.ACCOUNT_LOOKUP_FIELD)
    campaign = serializers.SlugRelatedField(required=False,
        queryset=Campaign.objects.all(), slug_field='slug')
    message = serializers.CharField(required=False, allow_null=True)
    grantee = InviteeSerializer()

    class Meta:
        model = PortfolioDoubleOptIn
        fields = ("accounts", "campaign", "message", "ends_at", "grantee",)
        read_only_fields = ("ends_at",)


class PortfolioRequestCreateSerializer(serializers.ModelSerializer):

    accounts = InviteeSerializer(many=True)
    campaign = serializers.SlugRelatedField(required=False,
        queryset=Campaign.objects.all(), slug_field='slug')
    message = serializers.CharField(required=False, allow_null=True)

    class Meta:
        model = PortfolioDoubleOptIn
        fields = ("accounts", "campaign", "message", "ends_at",)
        read_only_fields = ("ends_at",)


class PortfolioOptInSerializer(serializers.ModelSerializer):

    grantee = serializers.SlugRelatedField(
        queryset=get_account_model().objects.all(),
        slug_field=settings.ACCOUNT_LOOKUP_FIELD)
    account = serializers.SlugRelatedField(
        queryset=get_account_model().objects.all(),
        slug_field=settings.ACCOUNT_LOOKUP_FIELD)
    campaign = serializers.SlugRelatedField(
        queryset=Campaign.objects.all(), slug_field='slug')
    state = EnumField(choices=PortfolioDoubleOptIn.STATES)
    api_accept = serializers.SerializerMethodField()
    api_remove = serializers.SerializerMethodField()

    class Meta:
        model = PortfolioDoubleOptIn
        fields = ('grantee', 'account', 'campaign', 'ends_at',
            'state', 'api_accept', 'api_remove')
        read_only_fields = ('ends_at', 'state', 'api_accept', 'api_remove')

    def get_api_accept(self, obj):
        api_endpoint = None
        view = self.context.get('view')
        if (obj.state == PortfolioDoubleOptIn.OPTIN_GRANT_INITIATED and
            view.account == obj.grantee):
            api_endpoint = reverse('api_portfolios_grant_accept',
                args=(obj.grantee, obj.verification_key,))
        elif (obj.state == PortfolioDoubleOptIn.OPTIN_REQUEST_INITIATED and
            view.account == obj.account):
            api_endpoint = reverse('api_portfolios_request_accept',
                args=(obj.account, obj.verification_key,))
        request = self.context.get('request')
        if request and api_endpoint:
            return request.build_absolute_uri(api_endpoint)
        return api_endpoint

    def get_api_remove(self, obj):
        api_endpoint = None
        view = self.context.get('view')
        if (obj.state == PortfolioDoubleOptIn.OPTIN_GRANT_INITIATED and
            view.account == obj.account):
            api_endpoint = reverse('api_portfolios_grant_accept',
                args=(obj.account, obj.verification_key,))
        elif (obj.state == PortfolioDoubleOptIn.OPTIN_REQUEST_INITIATED and
            view.account == obj.grantee):
            api_endpoint = reverse('api_portfolios_request_accept',
                args=(obj.grantee, obj.verification_key,))
        request = self.context.get('request')
        if request and api_endpoint:
            return request.build_absolute_uri(api_endpoint)
        return api_endpoint


class AccountsFilterAddSerializer(serializers.ModelSerializer):

    slug = serializers.CharField(required=False)
    full_name = serializers.CharField()
    extra = serializers.CharField(required=False)

    class Meta:
        model = get_account_model()
        fields = ('slug', 'full_name', 'extra')
