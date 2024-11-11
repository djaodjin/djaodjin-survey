# Copyright (c) 2024, DjaoDjin inc.
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

from django.db import transaction
from django.template.defaultfilters import slugify
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404

from .. import settings
from ..compat import gettext_lazy as _, reverse, six
from ..models import (EditableFilterEnumeratedAccounts, Answer, Campaign,
    Choice, EditableFilter, Matrix, PortfolioDoubleOptIn,
    Sample, Unit, convert_to_target_unit)
from ..utils import (get_account_model, get_belongs_model, get_question_model,
    get_account_serializer)


class EnumField(serializers.ChoiceField):
    """
    Treat a ``PositiveSmallIntegerField`` as an enum.
    """
    translated_choices = {}

    def __init__(self, choices, *args, **kwargs):
        self.translated_choices = {key: slugify(val) for key, val in choices}
        super(EnumField, self).__init__([(slugify(val), key)
            for key, val in choices],
            *args, **kwargs)

    def to_representation(self, value):
        if isinstance(value, list):
            result = [slugify(self.translated_choices.get(item, None))
                for item in value]
        else:
            result = slugify(self.translated_choices.get(value, None))
        return result

    def to_internal_value(self, data):
        if isinstance(data, list):
            result = [self.choices.get(item, None) for item in data]
        else:
            result = self.choices.get(data, None)
        if result is None:
            if not data:
                raise ValidationError(_("This field cannot be blank."))
            raise ValidationError(_("'%(data)s' is not a valid choice."\
                " Expected one of %(choices)s.") % {
                    'data': data, 'choices': [str(choice)
                    for choice in six.iterkeys(self.choices)]})
        return result


class ExtraField(serializers.CharField):

    def to_internal_value(self, data):
        if isinstance(data, dict):
            try:
                return json.dumps(data)
            except (TypeError, ValueError):
                pass
        return super(ExtraField, self).to_internal_value(data)

    def to_representation(self, value):
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (TypeError, ValueError):
                pass
        return super(ExtraField, self).to_representation(value)


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
    extra = ExtraField(read_only=True,
        help_text=_("Extra meta data (can be stringify JSON)"))
    rank = serializers.SerializerMethodField(read_only=True,
        help_text=_("rank in filter"))

    class Meta:
        model = get_account_model()
        fields = ('slug', 'printable_name', 'picture', 'extra', 'rank')

    @staticmethod
    def get_slug(obj):
        try:
            return obj.slug
        except AttributeError:
            pass
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
        except AttributeError:
            pass
        return None

    @staticmethod
    def get_rank(obj):
        try:
            return obj.rank
        except AttributeError:
            pass
        return 0


class AccountsDateRangeQueryParamSerializer(NoModelSerializer):

    accounts_start_at = serializers.CharField(required=False,
        help_text=_("start of the range as a date/time in ISO 8601 format"))
    accounts_ends_at = serializers.CharField(required=False,
        help_text=_("end of the range as a date/time in ISO 8601 format"))


class UnitQueryParamSerializer(NoModelSerializer):
    """
    Serializer for `unit` query parameter
    """
    unit = serializers.SlugRelatedField(required=False,
        queryset=Unit.objects.all(), slug_field='slug',
        help_text=_("Unit to return values in"))


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


class ConvertUnitSerializer(UnitSerializer):

    value = serializers.SerializerMethodField()

    class Meta(UnitSerializer.Meta):
        fields = UnitSerializer.Meta.fields + ('value',)
        read_only_fields = UnitSerializer.Meta.read_only_fields + ('value',)

    def get_value(self, dictionary):
        request = self.context.get('request')
        view = self.context.get('view')
        if request and view:
            value = request.query_params.get('value', 1)
            try:
                return convert_to_target_unit(value,
                    dictionary.factor, dictionary.scale, dictionary.content)
            except TypeError:
                # We just pretent we can't convert to the target unit.
                pass
        return None


class QuestionDetailSerializer(serializers.ModelSerializer):

    title = serializers.CharField(
        help_text=_("Title of the question as displayed in user interfaces"))
    text = serializers.CharField(required=False, allow_blank=True,
        help_text=_("Long form description about the question"))
    default_unit = serializers.SlugRelatedField(slug_field='slug',
        queryset=Unit.objects.all(),
        help_text=_("Default unit for measured field when none is specified"))
    extra = ExtraField(required=False,
        help_text=_("Extra meta data (can be stringify JSON)"))

    class Meta:
        model = get_question_model()
        fields = ('title', 'text', 'default_unit', 'extra', 'path')
        read_only_fields = ('path',)


class QuestionUpdateSerializer(QuestionDetailSerializer):

    title = serializers.CharField(required=False,
        help_text=_("Title of the question as displayed in user interfaces"))
    default_unit = serializers.SlugRelatedField(required=False,
        slug_field='slug', queryset=Unit.objects.all(),
        help_text=_("Default unit for measured field when none is specified"))
    required = serializers.BooleanField(required=False,
        help_text=_("Whether an answer is required or not when the question"\
        " is part of a campaign"))

    class Meta(QuestionDetailSerializer.Meta):
        fields = QuestionDetailSerializer.Meta.fields + ('required',)


class QuestionCreateSerializer(QuestionUpdateSerializer):

    title = serializers.CharField(required=True,
        help_text=_("Title of the question as displayed in user interfaces"))

    class Meta(QuestionUpdateSerializer.Meta):
        fields = QuestionUpdateSerializer.Meta.fields


class QuestionSerializer(serializers.ModelSerializer):
    """
    Serializer of ``Question`` when used in a list of answers
    """
    title = serializers.CharField(required=False, allow_blank=True,
        help_text=_("Short description"))
    default_unit = UnitSerializer()
    ui_hint = EnumField(choices=get_question_model().UI_HINTS, required=False,
        help_text=_("Hint for the user interface on"\
            " how to present the input field"))

    class Meta:
        model = get_question_model()
        fields = ('path', 'title', 'default_unit', 'ui_hint')
        read_only_fields = ('path',)


class SampleAnswerSerializer(QuestionSerializer):
    """
    Serializer of ``Answer`` when used in list.
    """
    required = serializers.BooleanField(required=False,
        help_text=_("Whether an answer is required or not."))
    answers = serializers.ListField(child=AnswerSerializer(), required=False)
    candidates = serializers.ListField(child=AnswerSerializer(), required=False)

    class Meta(object):
        model = QuestionSerializer.Meta.model
        fields = QuestionSerializer.Meta.fields + (
            'required', 'answers', 'candidates')
        read_only_fields = QuestionSerializer.Meta.read_only_fields + (
            'required',)


class CampaignSerializer(serializers.ModelSerializer):
    """
    Short description of the campaign.
    """

    account = serializers.SlugRelatedField(
        slug_field=settings.BELONGS_LOOKUP_FIELD,
        queryset=get_belongs_model().objects.all(),
        help_text=_("Account this sample belongs to."))

    class Meta(object):
        model = Campaign
        fields = ('slug', 'account', 'title', 'description', 'created_at',
            'active')
        read_only_fields = ('slug', 'account', 'created_at')


class CampaignCreateSerializer(serializers.ModelSerializer):

    questions = QuestionCreateSerializer(many=True, required=False)

    class Meta(object):
        model = Campaign
        fields = ('slug', 'title', 'description', 'quizz_mode', 'questions')
        read_only_fields = ('slug',)


class CampaignDetailSerializer(serializers.ModelSerializer):

    account = serializers.SlugRelatedField(
        slug_field=settings.BELONGS_LOOKUP_FIELD,
        queryset=get_belongs_model().objects.all(),
        help_text=_("Account this sample belongs to."))
    questions = QuestionSerializer(many=True)

    class Meta(object):
        model = Campaign
        fields = ('slug', 'account', 'title', 'description', 'active',
            'quizz_mode', 'questions')
        read_only_fields = ('slug',)


class SampleCreateSerializer(serializers.ModelSerializer):

    campaign = serializers.SlugRelatedField(slug_field='slug',
        queryset=Campaign.objects.all(), required=False,
        help_text=_("Campaign this sample is part of."))

    class Meta(object):
        model = Sample
        fields = ('campaign',)


class SampleSerializer(SampleCreateSerializer):

    campaign = CampaignSerializer(
        read_only=True, allow_null=True,
        help_text=_("Campaign this sample is part of"))
    account = serializers.SlugRelatedField(slug_field='slug',
        read_only=True, required=False,
        help_text=_("Account this sample belongs to"))
    location = serializers.URLField(read_only=True, allow_null=True,
        help_text=_("URL at which the response is visible"))
    grantees = serializers.ListField(required=False,
        help_text=_("Profiles with which sample was shared"))

    class Meta(object):
        model = Sample
        fields = ('campaign', 'slug', 'account', 'created_at',
            'updated_at', 'is_frozen', 'location', 'grantees')
        read_only_fields = ('campaign', 'slug', 'account', 'created_at',
            'updated_at', 'is_frozen', 'location', 'grantees')

    @staticmethod
    def get_location(obj):
        return getattr(obj, 'location', None)


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


class EditableFilterSerializer(serializers.ModelSerializer):

    account = serializers.SlugRelatedField(read_only=True,
        slug_field=settings.BELONGS_LOOKUP_FIELD,
        help_text=_("Account the group belongs to"))

    class Meta:
        model = EditableFilter
        fields = ('slug', 'title', 'account', 'extra')
        read_only_fields = ('account',)


class EditableFilterUpdateSerializer(EditableFilterSerializer):

    slug = serializers.SlugField(required=False)
    extra = ExtraField(required=False, allow_null=True, allow_blank=True,
        help_text=_("Extra meta data (can be stringify JSON)"))

    class Meta(EditableFilterSerializer.Meta):
        fields = EditableFilterSerializer.Meta.fields


class EditableFilterCreateSerializer(EditableFilterUpdateSerializer):

    class Meta(EditableFilterUpdateSerializer.Meta):
        fields = EditableFilterUpdateSerializer.Meta.fields


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
                matrix.cohorts.add(cohort)
        return matrix

    def update(self, instance, validated_data):
        with transaction.atomic():
            instance.title = validated_data['title']
            if 'metric' in validated_data:
                instance.metric = get_object_or_404(
                    EditableFilter.objects.all(),
                    slug=validated_data['metric']['slug'])
            instance.save()
            absents = set(instance.cohorts.all().values_list('pk', flat=True))
            for cohort in validated_data['cohorts']:
                cohort = get_object_or_404(
                    EditableFilter.objects.all(), slug=cohort['slug'])
                instance.cohorts.add(cohort)
                absents = absents - set([cohort.pk])
            instance.cohorts.remove(*list(absents))
        return instance


class KeyValueTuple(serializers.ListField):
    # `KeyValueTuple` is typed as a (String, Integer) tuple.
    # by not specifying a child field, the serialized data
    # is generated as expected. Otherwise we would end up
    # with a (String, String).

    min_length = 2
    max_length = 3


class TableSerializer(NoModelSerializer):

    slug = serializers.SlugField(
        help_text=_("Unique key in the table for the data series"))
    title = serializers.CharField(required=False, read_only=True,
        help_text=_("Title of data serie that can be safely used for display"\
        " in HTML pages"))
    extra = ExtraField(required=False,
        help_text=_("Extra meta data (can be stringify JSON)"))
    values = serializers.ListField(
        child=KeyValueTuple(),
        help_text="Datapoints in the serie")


class SampleBenchmarksSerializer(QuestionSerializer):
    """
    Benchmarks for one question when used in a list of `Question`.
    """
    benchmarks = serializers.ListField(child=TableSerializer())

    class Meta(QuestionSerializer.Meta):
        fields = QuestionSerializer.Meta.fields + ('benchmarks',)


class MetricsSerializer(NoModelSerializer):

    scale = serializers.FloatField(required=False,
        help_text=_("The scale of the number reported in the tables (ex: 1000"\
        " when numbers are reported in thousands)"))
    unit = serializers.SlugRelatedField(required=False, allow_null=True,
        queryset=Unit.objects.all(), slug_field='slug',
        help_text=_("Unit the measured field is in"))
    title = serializers.CharField(
        help_text=_("Title for the table"))
    results = TableSerializer(many=True,
        help_text=_("Data series"))


class CompareQuestionSerializer(QuestionSerializer):
    """
    Serializer for a question in the `results` field of a Compare API call.
    """
    values = serializers.ListField(
        child=serializers.ListField(child=AnswerSerializer()), required=False)

    class Meta(QuestionSerializer.Meta):
        fields = QuestionSerializer.Meta.fields + ('values',)



class InviteeSerializer(NoModelSerializer):

    slug = serializers.SlugField()
    full_name = serializers.CharField(required=False)
    email = serializers.EmailField(required=False)
    printable_name = serializers.SerializerMethodField()

    @staticmethod
    def get_printable_name(obj):
        try:
            return str(obj.full_name)
        except AttributeError:
            pass
        return obj.get('full_name')


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
    extra = ExtraField(required=False,
        help_text=_("Extra meta data (can be stringify JSON)"))

    class Meta:
        model = PortfolioDoubleOptIn
        fields = ('accounts', 'campaign', 'message', 'ends_at', 'extra')
        read_only_fields = ('ends_at',)


class PortfolioOptInUpdateSerializer(serializers.ModelSerializer):

    extra = ExtraField(required=False,
        help_text=_("Extra meta data (can be stringify JSON)"))

    class Meta:
        model = PortfolioDoubleOptIn
        fields = ('extra',)


class PortfolioReceivedSerializer(serializers.ModelSerializer):

    # `PortfolioReceivedSerializer` is used in `PortfoliosAPIView` which
    # is used by the receiving profile.

    grantee = serializers.SlugRelatedField(
        queryset=get_account_model().objects.all(),
        slug_field=settings.ACCOUNT_LOOKUP_FIELD)
    account = serializers.SlugRelatedField(
        queryset=get_account_model().objects.all(),
        slug_field=settings.ACCOUNT_LOOKUP_FIELD)
    campaign = CampaignSerializer(allow_null=True,
        help_text=_("Campaign granted/requested"))
    state = EnumField(choices=PortfolioDoubleOptIn.STATES)
    expected_behavior = EnumField(
        choices=PortfolioDoubleOptIn.EXPECTED_BEHAVIOR, required=False)
    api_accept = serializers.SerializerMethodField()
    api_remove = serializers.SerializerMethodField()

    class Meta:
        model = PortfolioDoubleOptIn
        fields = ('grantee', 'account', 'campaign', 'created_at', 'ends_at',
            'state', 'expected_behavior', 'api_accept', 'api_remove')
        read_only_fields = ('created_at', 'ends_at',
            'state', 'expected_behavior', 'api_accept', 'api_remove')

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


class PortfolioOptInSerializer(PortfolioReceivedSerializer):

    extra = ExtraField(required=False,
        help_text=_("Extra meta data (can be stringify JSON)"))

    class Meta(PortfolioReceivedSerializer.Meta):
        fields = PortfolioReceivedSerializer.Meta.fields + (
            'extra',)
        read_only_fields = PortfolioReceivedSerializer.Meta.read_only_fields + (
            'extra',)


class CohortSerializer(serializers.ModelSerializer):

    slug = serializers.CharField(source='account.slug', required=False,
        help_text=_("Unique identifier for the profile"))
    full_name = serializers.CharField(source='account.full_name',
        required=False,
        help_text=_("Human readable name for the profile"))
    path = serializers.CharField(source='question.path', required=False,
        help_text=_("Path for the question used to filter profiles"))
    measured = serializers.CharField(source='humanize_measured', required=False,
        help_text=_("Answer to the question used to filter profiles"))
    # XXX `source='account.extra'` because of how GHG Emissions factors
    #     are encoded.
    extra = ExtraField(source='account.extra', required=False,
        help_text=_("Extra meta data (can be stringify JSON)"))

    class Meta:
        model = EditableFilterEnumeratedAccounts
        fields = ('slug', 'full_name', 'path', 'measured', 'extra')


class CohortAddSerializer(CohortSerializer):

    slug = serializers.CharField(required=False,
        help_text=_("Unique identifier for the profile"))
    full_name = serializers.CharField(required=False,
        help_text=_("Human readable name for the profile"))
    path = serializers.CharField(required=False,
        help_text=_("Path for the question used to filter profiles"))
    measured = serializers.CharField(required=False,
        help_text=_("Answer to the question used to filter profiles"))
    extra = ExtraField(required=False,
        help_text=_("Extra meta data (can be stringify JSON)"))

    class Meta:
        model = CohortSerializer.Meta.model
        fields = CohortSerializer.Meta.fields

    def validate(self, attrs):
        slug = attrs.get('slug', None)
        full_name = attrs.get('full_name', None)
        path = attrs.get('path', None)
        measured = attrs.get('measured', None)
        if not (slug or full_name or (path and measured)):
            raise ValidationError(
                _("An account or a question/answer must be specified"))
        return attrs

    def validate_path(self, obj):
        if not get_question_model().objects.filter(path=obj).exists():
            raise ValidationError(
                _("Question with the specificed path does not exist."))
        return obj


class QueryParamForceSerializer(NoModelSerializer):

    force = serializers.BooleanField(required=False,
        help_text=_("Forces freeze of sample"))


class ValidationErrorSerializer(NoModelSerializer):
    """
    Details on why collected data is invalid
    """
    detail = serializers.CharField(help_text=_("Describes the reason for"\
        " the error in plain text"))
