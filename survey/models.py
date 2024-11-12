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
"""
The models implement a
`star schema database <https://en.wikipedia.org/wiki/Star_schema>`_ centered
around ``Answer`` to store measurements.

``Matrix`` and ``EditablePredicate`` implement views and dashboards typically
used for reporting analytics.

``Portfolio`` and ``PortfolioDoubleOptIn`` implement access control to the
underlying ``Sample`` accessible to an account/user.
"""
import datetime, hashlib, random, uuid

from django import VERSION as DJANGO_VERSION
from django.contrib.auth import get_user_model
from django.db import models, transaction
from django.template.defaultfilters import slugify
from django.utils import timezone

from . import settings
from .compat import (gettext_lazy as _, import_string,
    python_2_unicode_compatible)
from .helpers import datetime_or_now, SlugifyFieldMixin
from .queries import (UNIT_SYSTEM_STANDARD, UNIT_SYSTEM_IMPERIAL,
    UNIT_SYSTEM_RANK, UNIT_SYSTEM_ENUMERATED, UNIT_SYSTEM_FREETEXT,
    UNIT_SYSTEM_DATETIME, get_account_model, get_question_model,
    sql_completed_at_by, sql_has_different_answers,
    sql_latest_frozen_by_accounts, sql_frozen_answers)


def get_extra_field_class():
    extra_class = settings.EXTRA_FIELD
    if extra_class is None:
        extra_class = models.TextField
    elif isinstance(extra_class, str):
        extra_class = import_string(extra_class)
    return extra_class


@python_2_unicode_compatible
class Unit(models.Model):
    """
    Unit in which an ``Answer.measured`` value is collected.

    There are 6 types of units, each with its own use.

    +----+------------+------------------------------------------------------+
    | Unit Type       | Description                                          |
    +====+============+======================================================+
    | SYSTEM_STANDARD | SI or International System of Units (ex: m, kg, J)   |
    +----+------------+------------------------------------------------------+
    | SYSTEM_IMPERIAL | Imperial/US customary measurement system (ex: ft, lb)|
    +----+------------+------------------------------------------------------+
    | SYSTEM_RANK     | Natural positive integer (ex: score, percentage)     |
    +----+------------+------------------------------------------------------+
    |SYSTEM_ENUMERATED| Finite set of named values (ex: Yes, No, N/A)        |
    +----+------------+------------------------------------------------------+
    | SYSTEM_FREETEXT | UTF-8 text string                                    |
    +----+------------+------------------------------------------------------+
    | SYSTEM_DATETIME | Date/time in Gregorian calendar                      |
    +----+------------+------------------------------------------------------+
    """

    SYSTEM_STANDARD = UNIT_SYSTEM_STANDARD
    SYSTEM_IMPERIAL = UNIT_SYSTEM_IMPERIAL
    SYSTEM_RANK = UNIT_SYSTEM_RANK
    SYSTEM_ENUMERATED = UNIT_SYSTEM_ENUMERATED
    SYSTEM_FREETEXT = UNIT_SYSTEM_FREETEXT
    SYSTEM_DATETIME = UNIT_SYSTEM_DATETIME

    SYSTEMS = [
            (SYSTEM_STANDARD, 'standard'),
            (SYSTEM_IMPERIAL, 'imperial'),
            (SYSTEM_RANK, 'rank'),
            (SYSTEM_ENUMERATED, 'enum'),
            (SYSTEM_FREETEXT, 'freetext'),
            (SYSTEM_DATETIME, 'datetime'),
        ]

    METRIC_SYSTEMS = [
        SYSTEM_STANDARD,
        SYSTEM_IMPERIAL,
    ]

    NUMERICAL_SYSTEMS = METRIC_SYSTEMS + [
        SYSTEM_RANK
    ]

    slug = models.SlugField(max_length=150, unique=True, db_index=True,
        help_text=_("Unique identifier that can be used in a URL"))
    title = models.CharField(max_length=150,
        help_text=_("Short description suitable for display"))
    system = models.PositiveSmallIntegerField(
        choices=SYSTEMS, default=SYSTEM_STANDARD,
        help_text=_("One of standard (metric system), imperial,"\
            " rank, enum, or freetext"))

    @property
    def choices(self):
        if self.system == self.SYSTEM_ENUMERATED:
            return Choice.objects.filter(
                question__isnull=True, unit=self).order_by('rank')
        return None

    def __str__(self):
        return str(self.slug)


class UnitEquivalencesMaganger(models.Manager):

    def are_equiv(self, left, right):
        return self.filter(
            (models.Q(source=left) & models.Q(target=right)) |
            (models.Q(source=right) & models.Q(target=left))
        ).exists()


@python_2_unicode_compatible
class UnitEquivalences(models.Model):
    """
    Pairs of units that can be translated one to the other.
    """
    objects = UnitEquivalencesMaganger()

    source = models.ForeignKey(Unit, on_delete=models.CASCADE,
        related_name='source_equivalences',
        help_text=_("Source unit in the equivalence"))
    target = models.ForeignKey(Unit, on_delete=models.CASCADE,
        related_name='target_equivalences',
        help_text=_("Target unit in the equivalence"))
    content = models.TextField(null=True,
        help_text=_("Description of the equivalence function"))
    # Implementation Note: We set `factor` to zero by default such
    # that a misconfigured equivalence will result in "odd" results.
    # By default the scale is 1 because in general we are converting
    # from one system to another without affecting the scale
    # (ex: SI to US Customary).
    factor = models.FloatField(default=0)
    scale = models.FloatField(default=1)

    def __str__(self):
        return "%s:%s" % (self.source, self.target)


    def as_source_unit(self, value):
        if not self.content:
            raise NotImplementedError("cannot convert %s to %s" % (
                self.target, self.source))
        return convert_to_source_unit(
            value, self.factor, self.scale, self.content)


    def as_target_unit(self, value):
        if not self.content:
            raise NotImplementedError("cannot convert %s to %s" % (
                self.source, self.target))
        return convert_to_target_unit(
            value, self.factor, self.scale, self.content)


@python_2_unicode_compatible
class Choice(models.Model):
    """
    Choice for a multiple choice question, or text blob for `Answer`
    with a 'freetext' unit.
    """
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT,
            related_name='enums')
    question = models.ForeignKey(settings.QUESTION_MODEL,
        on_delete=models.PROTECT, null=True)
    rank = models.IntegerField(
        help_text=_("used to order choice when presenting a question"))
    text = models.TextField(
        help_text=_("short name for the enumerated value"\
        " (as used in source code)"))
    descr = models.TextField(
        help_text=_("long form description of the enumerated value"\
        " (for help tooltips)"))

    class Meta:
        unique_together = ('unit', 'question', 'rank')

    def __str__(self):
        return str(self.text)


@python_2_unicode_compatible
class Content(models.Model):
    """
    Description (title and long form text) of a `Question`.
    """

    title = models.CharField(max_length=50,
        help_text=_("Short description"))
    text = models.TextField(
        help_text=_("Detailed description about the question"))

    def __str__(self):
        return slugify(self.title)


@python_2_unicode_compatible
class AbstractQuestion(SlugifyFieldMixin, models.Model):

    slug_field = 'path'

    TEXT = 'textarea'
    RADIO = 'radio'
    SELECT_MULTIPLE = 'checkbox'
    NUMBER = 'number'
    ENERGY = 'energy'
    WATER = 'water'
    WASTE = 'waste'
    GHG_EMISSIONS = 'ghg-emissions'
    GHG_EMISSIONS_SCOPE3 = 'ghg-emissions-scope3'

    UI_HINTS = (
            (TEXT, 'textarea'),
            (RADIO, 'radio'),
            (SELECT_MULTIPLE, 'checkbox'),
            (NUMBER, 'number'),
            (ENERGY, 'energy'),
            (WATER, 'water'),
            (WASTE, 'waste'),
            (GHG_EMISSIONS, 'ghg-emissions'),
            (GHG_EMISSIONS_SCOPE3, 'ghg-emissions-scope3'),
    )

    class Meta:
        abstract = True

    path = models.CharField(max_length=1024, unique=True, db_index=True,
        help_text=_("Unique identifier that can be used in URL"))
    content = models.ForeignKey(settings.CONTENT_MODEL,
        on_delete=models.PROTECT, related_name='question',
        help_text=_("Title, description and metadata about the question"))
    ui_hint = models.CharField(
        max_length=20, choices=UI_HINTS, default=RADIO,
        help_text=_("Choose the type of answser."))
    correct_answer = models.ForeignKey(Choice, related_name='correct_for',
        null=True, on_delete=models.PROTECT, blank=True)
    default_unit = models.ForeignKey(Unit, on_delete=models.PROTECT,
        related_name='question',
        help_text=_("Default unit for measured field when none is specified"))
    extra = get_extra_field_class()(null=True, blank=True,
        help_text=_("Extra meta data (can be stringify JSON)"))

    def __str__(self):
        return str(self.path)

    @property
    def title(self):
        return self.content.title

    @property
    def text(self):
        return self.content.text

    @property
    def choices(self):
        if self.default_unit.system == Unit.SYSTEM_ENUMERATED:
            if Choice.objects.filter(
                    question=self, unit=self.default_unit).exists():
                choices_qs = Choice.objects.filter(question=self,
                    unit=self.default_unit)
            else:
                choices_qs = Choice.objects.filter(
                    question__isnull=True, unit=self.default_unit)
            return choices_qs.order_by('rank')
        return None

    def save(self, force_insert=False, force_update=False,
             using=None, update_fields=None):
        if not self.title:
            max_length = self._meta.get_field('title').max_length
            self.title = self.text[:max_length]
        return super(AbstractQuestion, self).save(
            force_insert=force_insert, force_update=force_update,
            using=using, update_fields=update_fields)

    def get_correct_answer(self):
        correct_answer_list = []
        if self.correct_answer:
            #pylint: disable=no-member
            correct_answer_list = [
                asw.strip() for asw in self.correct_answer.text.split('\n')]
        return correct_answer_list


@python_2_unicode_compatible
class Question(AbstractQuestion):

    class Meta(AbstractQuestion.Meta):
        swappable = 'QUESTION_MODEL'

    def __str__(self):
        return str(self.path)


@python_2_unicode_compatible
class Campaign(SlugifyFieldMixin, models.Model):

    slug = models.SlugField(unique=True,
        help_text=_("Unique identifier that can be used in a URL"))
    created_at = models.DateTimeField(auto_now_add=True)
    title = models.CharField(max_length=150,
        help_text=_("Title of the campaign as displayed in user interfaces"))
    description = models.TextField(null=True, blank=True,
        help_text=_("Long form description displayed to users responding"\
        " to the campaign"))
    account = models.ForeignKey(settings.BELONGS_MODEL,
        on_delete=models.PROTECT, null=True,
        help_text=_("Acccount that can make edits to the campaign"))
    active = models.BooleanField(default=False,
        help_text=_("Whether the campaign is available or not"))
    # quizz_mode, defaults_single_page, one_response_only are managing workflow
    # and layout.
    quizz_mode = models.BooleanField(default=False,
        help_text=_("If checked, correct answser are required"))
    defaults_single_page = models.BooleanField(default=False,
        help_text=_("If checked, will display all questions on a single page,"\
" else there will be one question per page."))
    one_response_only = models.BooleanField(default=False,
        help_text=_("Only allows to answer campaign once."))
    questions = models.ManyToManyField(settings.QUESTION_MODEL,
        through='survey.EnumeratedQuestions', related_name='campaigns',
        help_text=_("Questions which are part of the campaign"))
    extra = get_extra_field_class()(null=True, blank=True,
        help_text=_("Extra meta data (can be stringify JSON)"))

    def __str__(self):
        return str(self.slug)

    @property
    def has_questions(self):
        return self.questions.exists()

    @property
    def nb_questions(self):
        if not hasattr(self, '_nb_questions'):
            #pylint:disable=attribute-defined-outside-init
            self._nb_questions = self.get_nb_questions()
        return self._nb_questions

    @property
    def nb_required_questions(self):
        if not hasattr(self, '_nb_required_questions'):
            #pylint:disable=attribute-defined-outside-init
            self._nb_required_questions = self.get_nb_required_questions()
        return self._nb_required_questions

    def get_questions(self, prefixes=None):
        if not prefixes:
            prefixes = []
        filtered_in = None
        #pylint:disable=superfluous-parens
        for prefix in prefixes:
            filtered_q = models.Q(path__startswith=prefix)
            if filtered_in:
                filtered_in |= filtered_q
            else:
                filtered_in = filtered_q
        queryset = self.questions.all()
        if filtered_in:
            queryset = queryset.filter(filtered_q)
        return queryset

    def get_nb_questions(self, prefixes=None):
        return self.get_questions(prefixes=prefixes).distinct().count()

    def get_nb_required_questions(self, prefixes=None):
        return self.get_questions(prefixes=prefixes).filter(
            enumeratedquestions__required=True).distinct().count()


@python_2_unicode_compatible
class EnumeratedQuestions(models.Model):

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE)
    question = models.ForeignKey(settings.QUESTION_MODEL,
        on_delete=models.CASCADE)
    rank = models.IntegerField(
        help_text=_("used to order questions when presenting a campaign."))
    required = models.BooleanField(default=True,
        help_text=_("If checked, an answer is required"))

    class Meta:
        unique_together = ('campaign', 'rank')

    def __str__(self):
        return str(self.question.path)


class SampleManager(models.Manager):

    def create_for_account(self, account_name, **kwargs):
        account_lookup_kwargs = {settings.ACCOUNT_LOOKUP_FIELD: account_name}
        return self.create(account=get_account_model().objects.get(
                **account_lookup_kwargs), **kwargs)

    def get_completed_assessments_at_by(self, campaign, accounts=None,
                                        start_at=None, ends_at=None,
                                        prefix=None, title="",
                                        exclude_accounts=None,
                                        extra=None):
        """
        Returns the most recent frozen assessment before an optionally specified
        date, indexed by account. Furthermore the query can be restricted
        to answers on a specific segment using `prefix` and matching text
        in the `extra` field.

        All accounts in ``excludes`` are not added to the index. This is
        typically used to filter out 'testing' accounts
        """
        #pylint:disable=too-many-arguments
        # XXX Rename method to `get_latest_frozen_by_accounts`
        return self.raw(sql_completed_at_by(
            campaign, accounts=accounts,
            start_at=start_at, ends_at=ends_at,
            prefix=prefix, title=title,
            exclude_accounts=exclude_accounts, extra=extra))


    def get_latest_frozen_by_accounts(self, campaign=None,
                                      start_at=None, ends_at=None,
                                      tags=None, pks_only=False):
        """
        Returns the most recent frozen sample in an optionally specified
        date range, indexed by account.

        The returned queryset can be further filtered by a campaign and
        a set of tags.
        """
        #pylint:disable=too-many-arguments
        return self.raw(sql_latest_frozen_by_accounts(campaign,
            start_at=start_at, ends_at=ends_at,
            tags=tags, pks_only=pks_only))


    def get_score(self, sample):
        answers = Answer.objects.populate(sample)
        nb_correct_answers = 0
        nb_questions = len(answers)
        for answer in answers:
            if answer.question.ui_hint == Question.RADIO:
                if answer.measured in answer.question.get_correct_answer():
                    nb_correct_answers += 1
            elif answer.question.ui_hint == Question.SELECT_MULTIPLE:
                multiple_choices = answer.get_multiple_choices()
                if not (set(multiple_choices)
                       ^ set(answer.question.get_correct_answer())):
                    # Perfect match
                    nb_correct_answers += 1

        # XXX Score will be computed incorrectly when some Answers are free
        # form text.
        if nb_questions > 0:
            score = (nb_correct_answers * 100) / nb_questions
        else:
            score = None
        return score, answers


@python_2_unicode_compatible
class Sample(models.Model):
    """
    Sample to a Campaign. A Sample is composed of multiple Answers
    to Questions.
    """
    objects = SampleManager()

    slug = models.SlugField(unique=True,
        help_text="Unique identifier for the sample. It can be used in a URL.")
    created_at = models.DateTimeField(default=timezone.now,
        help_text="Date/time of creation (in ISO format)")
    updated_at = models.DateTimeField(auto_now=True,
        help_text="Date/time of last update (in ISO format)")
    time_spent = models.DurationField(default=datetime.timedelta,
        help_text="Total recorded time to complete the survey")
    campaign = models.ForeignKey(Campaign, null=True, on_delete=models.PROTECT)
    account = models.ForeignKey(settings.ACCOUNT_MODEL,
        null=True, on_delete=models.PROTECT, related_name='samples')
    is_frozen = models.BooleanField(default=False,
        help_text="When True, answers to that sample cannot be updated.")
    extra = get_extra_field_class()(null=True, blank=True,
        help_text=_("Extra meta data (can be stringify JSON)"))

    def __str__(self):
        return str(self.slug)

    @property
    def nb_answers(self):
        #pylint:disable=attribute-defined-outside-init
        if not hasattr(self, '_nb_answers'):
            self._nb_answers = Answer.objects.filter(
                sample=self,
                question__default_unit=models.F('unit_id')).count()
        return self._nb_answers

    @property
    def nb_required_answers(self):
        #pylint:disable=attribute-defined-outside-init
        if not hasattr(self, '_nb_required_answers'):
            self._nb_required_answers = Answer.objects.filter(
                sample=self,
                question__default_unit=models.F('unit_id'),
                question__enumeratedquestions__required=True,
                question__enumeratedquestions__campaign=self.campaign).count()
        return self._nb_required_answers

    def has_identical_answers(self, right):
        return not(Sample.objects.raw(sql_has_different_answers(self, right)) or
            Sample.objects.raw(sql_has_different_answers(right, self)))

    def save(self, force_insert=False, force_update=False,
             using=None, update_fields=None):
        if not self.slug:
            self.slug = slugify(uuid.uuid4().hex)
        return super(Sample, self).save(
            force_insert=force_insert, force_update=force_update,
            using=using, update_fields=update_fields)

    def get_answers_by_rank(self):
        # We attempt to get Django ORM to generate SQL equivalent to:
        # ```
        # SELECT survey_answer.* FROM survey_answer
        # INNER JOIN survey_sample
        # ON survey_answer.sample_id = survey_sample.id
        # INNER JOIN survey_enumeratedquestions
        # ON survey_answer.question_id = survey_enumeratedquestions.question_id
        # ON survey_sample.campaign_id = survey_enumeratedquestions.campaign_id
        # WHERE survey_answer.sample_id = %(sample_id)d
        # ORDER BY survey_enumeratedquestions.rank
        # ```
        queryset = Answer.objects.filter(
            sample=self,
            question__campaigns__in=[self.campaign.pk]).order_by(
            'question__enumeratedquestions__rank').annotate(
                _rank=models.F('question__enumeratedquestions__rank'))
        return queryset


class AnswerManager(models.Manager):

    @staticmethod
    def as_sql_campaign_clause(campaign):
        kwargs = {}
        if campaign:
            if isinstance(campaign, Campaign):
                kwargs.update({'answer__sample__campaign': campaign})
            else:
                kwargs.update({'answer__sample__campaign__slug': campaign})
        return kwargs


    def get_frozen_answers(self, campaign, samples, prefix=None, excludes=None):
        queryset = self.raw(sql_frozen_answers(
            campaign, samples, prefix=prefix, excludes=excludes))
        if DJANGO_VERSION[0] >= 3:
            return queryset.prefetch_related(
                'unit', 'collected_by', 'question', 'question__content',
                'question__default_unit')
        # Py27/Django11 does not support `prefetch_related` on raw queryset.
        return queryset


    def populate(self, sample):
        """
        Return a list of ``Answer`` for all questions in the campaign
        associated to a *sample* even when there are no such record
        in the db.
        """
        at_time = datetime_or_now()
        answers = self.filter(sample=sample)
        if sample.campaign:
            questions = get_question_model().objects.filter(
                campaigns__pk=sample.campaign.pk).exclude(
                pk__in=answers.values('question'))
            answers = list(answers)
            for question in questions:
                answers += [Answer(
                    created_at=at_time, question=question, sample=sample)]
        return answers


@python_2_unicode_compatible
class Answer(models.Model):
    """
    An Answer to a Question as part of Sample to a Campaign.
    """
    MEASURED_MAX_VALUE = 2 ** 31 - 1

    objects = AnswerManager()

    created_at = models.DateTimeField()
    question = models.ForeignKey(settings.QUESTION_MODEL,
        on_delete=models.PROTECT)
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT)
    measured = models.IntegerField(null=True)
    denominator = models.IntegerField(null=True, default=1)
    collected_by = models.ForeignKey(settings.AUTH_USER_MODEL,
        null=True, on_delete=models.PROTECT)
    # Optional fields when the answer is part of a campaign.
    sample = models.ForeignKey(Sample, on_delete=models.CASCADE,
        related_name='answers')

    class Meta:
        unique_together = ('sample', 'question', 'unit')

    def __str__(self):
        if self.sample_id:
            return '%s-%d' % (self.sample.slug, self.rank)
        return str(self.question.content)

    @property
    def measured_text(self):
        #pylint:disable=attribute-defined-outside-init
        if not hasattr(self, '_measured_text'):
            if self.unit.system in Unit.NUMERICAL_SYSTEMS:
                self._measured_text = str(self.measured)
            else:
                self._measured_text = Choice.objects.get(
                    pk=self.measured, unit=self.unit).text
        return self._measured_text

    @property
    def is_equiv_default_unit(self):
        """
        Returns True if the answer unit is equivalent
        to the question default unit.
        """
        #pylint:disable=attribute-defined-outside-init
        if not hasattr(self, '_is_equiv_default_unit'):
            if self.unit == self.question.default_unit:
                self._is_equiv_default_unit = True
            else:
                self._is_equiv_default_unit = \
                    UnitEquivalences.objects.are_equiv(
                        self.unit, self.question.default_unit)
        return self._is_equiv_default_unit

    @property
    def rank(self):
        #pylint:disable=attribute-defined-outside-init
        if not hasattr(self, '_rank'):
            try:
                self._rank = EnumeratedQuestions.objects.get(
                    campaign=self.sample.campaign, question=self.question).rank
            except EnumeratedQuestions.DoesNotExist:
                self._rank = 0
        return self._rank

    def get_multiple_choices(self):
        text = Choice.objects.get(pk=self.measured).text
        return text.replace('[', '').replace(']', '').replace(
            'u\'', '').replace('\'', '').split(', ')


@python_2_unicode_compatible
class AnswerCollected(models.Model):

    collected = models.TextField(
        help_text=_("The measure as inputed by the user (ex: 5'2'')"))
    answer = models.ForeignKey(Answer, on_delete=models.CASCADE,
        help_text=_("The associated Answer for that collected datapoint"))
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT,
        help_text=_("The unit the collected measure was specified in"))

    def __str__(self):
        return "<AnswerCollected(answer_id=%d, unit_id=%d, collected=%s)>" % (
            self.answer_id, self.unit_id, self.collected)


@python_2_unicode_compatible
class EditableFilter(SlugifyFieldMixin, models.Model):
    """
    A model type and list of predicates to create a subset of the
    of the rows of a model type
    """
    slug = models.SlugField(unique=True,
      help_text=_("Unique identifier for the group that can be used in a URL"))
    title = models.CharField(max_length=255,
        help_text=_("Title for the group"))
    account = models.ForeignKey(settings.BELONGS_MODEL,
        on_delete=models.PROTECT, null=True,
        help_text=_("account the group belongs to"))
    extra = get_extra_field_class()(null=True, blank=True,
        help_text=_("Extra meta data (can be stringify JSON)"))

    def __str__(self):
        return str(self.slug)

    def as_kwargs(self):
        includes = {}
        excludes = {}
        for predicate in self.predicates.all().order_by('rank'):
            if predicate.selector == 'keepmatching':
                includes.update(predicate.as_kwargs())
            elif predicate.selector == 'removematching':
                excludes.update(predicate.as_kwargs())
        return includes, excludes


@python_2_unicode_compatible
class EditablePredicate(models.Model):
    """
    A predicate describing a step to narrow or enlarge
    a set of records in a portfolio.
    """
    rank = models.IntegerField()
    editable_filter = models.ForeignKey(
        EditableFilter, on_delete=models.CASCADE, related_name='predicates')
    operator = models.CharField(max_length=255)
    operand = models.CharField(max_length=255)
    field = models.CharField(max_length=255) # field on a Question.
    selector = models.CharField(max_length=255)

    def __str__(self):
        return '%s-%d' % (self.editable_filter.slug, int(self.rank))

    def as_kwargs(self):
        kwargs = {}
        if self.operator == 'equals':
            kwargs = {self.field: self.operand}
        elif self.operator == 'startsWith':
            kwargs = {"%s__startswith" % self.field: self.operand}
        elif self.operator == 'endsWith':
            kwargs = {"%s__endswith" % self.field: self.operand}
        elif self.operator == 'contains':
            kwargs = {"%s__contains" % self.field: self.operand}
        return kwargs


@python_2_unicode_compatible
class EditableFilterEnumeratedAccounts(models.Model):
    """
    A list of directly specified accounts to include in the filter.
    """
    rank = models.IntegerField(
        help_text=_("used to order accounts when presenting a filter"))
    editable_filter = models.ForeignKey(
        EditableFilter, on_delete=models.CASCADE, related_name='accounts')
    account = models.ForeignKey(settings.ACCOUNT_MODEL, null=True,
        on_delete=models.CASCADE, related_name='filters')
    question = models.ForeignKey(settings.QUESTION_MODEL, null=True,
        on_delete=models.CASCADE)
    measured = models.IntegerField(null=True)

    class Meta:
        unique_together = ('editable_filter', 'rank')

    def __str__(self):
        return '%s-%d' % (self.editable_filter.slug, int(self.rank))

    @property
    def humanize_measured(self):
        if not hasattr(self, '_humanize_measured'):
            #pylint:disable=attribute-defined-outside-init
            self._humanize_measured = self.measured
            if (self.question and
                self.question.default_unit.system == Unit.SYSTEM_ENUMERATED):
                try:
                    self._humanize_measured = Choice.objects.get(
                        models.Q(question__isnull=True)
                        | models.Q(question=self.question),
                        unit=self.question.default_unit, pk=self.measured).text
                except Choice.DoesNotExist:
                    self._humanize_measured = 'invalid'
        return self._humanize_measured


@python_2_unicode_compatible
class Matrix(SlugifyFieldMixin, models.Model):
    """
    Represent a set of cohorts against a metric.
    """

    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True,
        help_text=_("Long form description of the matrix"))
    account = models.ForeignKey(settings.BELONGS_MODEL,
        null=True, on_delete=models.CASCADE)
    metric = models.ForeignKey(EditableFilter, related_name='measured',
        null=True, on_delete=models.PROTECT)
    cohorts = models.ManyToManyField(EditableFilter, related_name='matrices')
    cut = models.ForeignKey(EditableFilter,
        null=True, on_delete=models.SET_NULL, related_name='cuts')
    extra = get_extra_field_class()(null=True, blank=True,
        help_text=_("Extra meta data (can be stringify JSON)"))

    def __str__(self):
        return str(self.slug)


@python_2_unicode_compatible
class Portfolio(models.Model):
    """
    Share an account's answers with a grantee up to a specific date.
    """
    grantee = models.ForeignKey(settings.ACCOUNT_MODEL,
        on_delete=models.PROTECT, db_index=True,
        related_name='portfolios_granted')
    account = models.ForeignKey(settings.ACCOUNT_MODEL,
        on_delete=models.PROTECT, db_index=True,
        related_name='portfolios')
    ends_at = models.DateTimeField(null=True)
    campaign = models.ForeignKey('Campaign', null=True,
        on_delete=models.PROTECT, db_index=True,
        related_name='portfolios')
    extra = get_extra_field_class()(null=True, blank=True,
        help_text=_("Extra meta data (can be stringify JSON)"))

    class Meta:
        unique_together = (('grantee', 'account', 'campaign'),)

    def __str__(self):
        return "portfolio-%s-%d" % (self.grantee, self.pk)


class PortfolioDoubleOptInQuerySet(models.QuerySet):

    def by_invoice_keys(self, invoice_keys):
        return self.filter(invoice_key__in=invoice_keys)

    def by_grantee(self, account, campaign=None,
                   start_at=None, ends_at=None, until=None):
        """
        Returns the portfolio grant/request for `account` that were
        created in the period [start_at, ends_at[ (when specified)
        and that extend beyond `until` (when specified).
        """
        #pylint:disable=too-many-arguments
        kwargs = {}
        if campaign:
            if isinstance(campaign, Campaign):
                kwargs.update({'campaign': campaign})
            else:
                kwargs.update({'campaign__slug': str(campaign)})
        if start_at:
            kwargs.update({'created_at__gte': start_at})
        if ends_at:
            kwargs.update({'created_at__lt': ends_at})
        if until:
            kwargs.update({'ends_at__gte': until})
        return self.filter(grantee=account, **kwargs)


    def pending_for(self, account, campaign=None, at_time=None):
        """
        Returns the current portfolio grant/request for `account`
        that a user must either accept or deny.
        """
        if not at_time:
            at_time = datetime_or_now()
        kwargs = {}
        if campaign:
            if isinstance(campaign, Campaign):
                kwargs.update({'campaign': campaign})
            else:
                kwargs.update({'campaign__slug': str(campaign)})
        return self.filter(
            (models.Q(ends_at__isnull=True) | models.Q(ends_at__gte=at_time)) &
            (models.Q(account=account) &
            models.Q(state=PortfolioDoubleOptIn.OPTIN_REQUEST_INITIATED)) |
            (models.Q(grantee=account) &
            models.Q(state=PortfolioDoubleOptIn.OPTIN_GRANT_INITIATED)),
            **kwargs)

    def requested(self, account, campaign=None,
                  start_at=None, ends_at=None, until=None):
        """
        Returns the portfolio requests made by `account` that were
        created in the period [start_at, ends_at[ (when specified)
        and that extend beyond `ends_at` (when specified).
        """
        #pylint:disable=too-many-arguments
        return self.by_grantee(account, campaign=campaign,
            start_at=start_at, ends_at=ends_at, until=until).filter(state__in=(
            PortfolioDoubleOptIn.OPTIN_REQUEST_INITIATED,
            PortfolioDoubleOptIn.OPTIN_REQUEST_ACCEPTED,
            PortfolioDoubleOptIn.OPTIN_REQUEST_DENIED,
            PortfolioDoubleOptIn.OPTIN_REQUEST_EXPIRED))


    def unsolicited(self, account, campaign=None,
                    start_at=None, ends_at=None, until=None):
        """
        Returns the portfolio grants where `account` is the benefiary that were
        created in the period [start_at, ends_at[ (when specified)
        and that extend beyond `ends_at` (when specified).
        """
        #pylint:disable=too-many-arguments
        return self.by_grantee(account, campaign=campaign,
            start_at=start_at, ends_at=ends_at, until=until).filter(state__in=(
            PortfolioDoubleOptIn.OPTIN_GRANT_INITIATED,
            PortfolioDoubleOptIn.OPTIN_GRANT_ACCEPTED,
            PortfolioDoubleOptIn.OPTIN_GRANT_DENIED))


    def accepted(self, account, campaign=None,
                 start_at=None, ends_at=None, until=None):
        """
        Returns the portfolio grant/request where `account` is the benefiary
        that were accepted and which had been created in the period
        [start_at, ends_at[ (when specified) and that extend beyond
        `ends_at` (when specified).
        """
        #pylint:disable=too-many-arguments
        return self.by_grantee(account, campaign=campaign,
            start_at=start_at, ends_at=ends_at, until=until).filter(state__in=(
            PortfolioDoubleOptIn.OPTIN_GRANT_ACCEPTED,
            PortfolioDoubleOptIn.OPTIN_REQUEST_ACCEPTED))


class PortfolioDoubleOptInManager(models.Manager):

    def get_queryset(self):
        return PortfolioDoubleOptInQuerySet(self.model, using=self._db)

    def by_invoice_keys(self, invoice_keys):
        return self.get_queryset().by_invoice_keys(invoice_keys)

    def by_grantee(self, account, campaign=None,
                   start_at=None, ends_at=None, until=None):
        #pylint:disable=too-many-arguments
        return self.get_queryset().by_grantee(account, campaign=campaign,
            start_at=start_at, ends_at=ends_at, until=until)

    def pending_for(self, account, campaign=None, at_time=None):
        return self.get_queryset().pending_for(account,
            campaign=campaign, at_time=at_time)

    def requested(self, account, campaign=None,
                  start_at=None, ends_at=None, until=None):
        #pylint:disable=too-many-arguments
        return self.get_queryset().requested(account, campaign=campaign,
            start_at=start_at, ends_at=ends_at, until=until)

    def unsolicited(self, account, campaign=None,
                    start_at=None, ends_at=None, until=None):
        #pylint:disable=too-many-arguments
        return self.get_queryset().unsolicited(account, campaign=campaign,
            start_at=start_at, ends_at=ends_at, until=until)

    def accepted(self, account,  campaign=None,
                 start_at=None, ends_at=None, until=None):
        #pylint:disable=too-many-arguments
        return self.get_queryset().accepted(account, campaign=campaign,
            start_at=start_at, ends_at=ends_at, until=until)


@python_2_unicode_compatible
class PortfolioDoubleOptIn(models.Model):
    """
    Intermidiary object to implement double opt-in through requests and grants.

    A double opt-in can be initiated by an account to share their answers with
    a grantee (grant), or by a account to request answers from another account.

    The non-initiating account for the double opt-in will have to accept the
    request/grant before the workflow is completed, a ``Portfolio`` is created
    and answers are shared. The non-initiating account can also deny
    the request/grant. In which case no data is shared and the double opt-in
    workflow is also considered complete.

    In case the non-initiating account does not accept or deny the request/grant
    within a specific time period (i.e. before ``ends_at``), the double opt-in
    workflow is marked expired and also considered complete.

    ``invoice_key`` is used as a identity token that will be passed back
    by the payment processor when a charge was successfully created.
    When we see ``invoice_key`` back, we create the ``Portfolio`` records.

    State definition (bits)

    +--------------------+--------------+---------+---------------+----------+
    |                    |request/grant | expired | accept/denied | completed|
    +====================+==============+=========+===============+==========+
    |grant initiated     |            1 |       0 |             0 |        0 |
    +--------------------+--------------+---------+---------------+----------+
    |grant accepted      |            1 |       0 |             1 |        1 |
    +--------------------+--------------+---------+---------------+----------+
    |grant denied        |            1 |       0 |             0 |        1 |
    +--------------------+--------------+---------+---------------+----------+
    |grant expired       |            1 |       1 |             0 |        1 |
    +--------------------+--------------+---------+---------------+----------+
    |request initiated   |            0 |       0 |             0 |        0 |
    +--------------------+--------------+---------+---------------+----------+
    |request accepted    |            0 |       0 |             1 |        1 |
    +--------------------+--------------+---------+---------------+----------+
    |request denied      |            0 |       0 |             0 |        1 |
    +--------------------+--------------+---------+---------------+----------+
    |request expired     |            0 |       1 |             0 |        1 |
    +--------------------+--------------+---------+---------------+----------+
    """
    OPTIN_GRANT_INITIATED = 8
    OPTIN_GRANT_ACCEPTED = 11
    OPTIN_GRANT_DENIED = 9
    OPTIN_GRANT_EXPIRED = 13
    OPTIN_REQUEST_INITIATED = 0
    OPTIN_REQUEST_ACCEPTED = 3
    OPTIN_REQUEST_DENIED = 1
    OPTIN_REQUEST_EXPIRED = 5

    STATES = [
        (OPTIN_GRANT_INITIATED, 'grant-initiated'),
        (OPTIN_GRANT_ACCEPTED, 'grant-accepted'),
        (OPTIN_GRANT_DENIED, 'grant-denied'),
        (OPTIN_GRANT_EXPIRED, 'grant-expired'),
        (OPTIN_REQUEST_INITIATED, 'request-initiated'),
        (OPTIN_REQUEST_ACCEPTED, 'request-accepted'),
        (OPTIN_REQUEST_DENIED, 'request-denied'),
        (OPTIN_REQUEST_EXPIRED, 'request-expired'),
    ]

    EXPECTED_SHARE = 0
    EXPECTED_CREATE = 1
    EXPECTED_UPDATE = 2

    EXPECTED_BEHAVIOR = [
        (EXPECTED_SHARE, 'share'),
        (EXPECTED_CREATE, 'create'),
        (EXPECTED_UPDATE, 'update'),
    ]

    objects = PortfolioDoubleOptInManager()

    created_at = models.DateTimeField(auto_now_add=True,
        help_text=_("Date/time at which the grant/request was created"))
    # Either we have an AccountModel or we have an e-mail to invite
    # someone to register an AccountModel.
    grantee = models.ForeignKey(settings.ACCOUNT_MODEL, null=True,
        on_delete=models.PROTECT, db_index=True,
        related_name='portfolio_double_optin_grantees')
    account = models.ForeignKey(settings.ACCOUNT_MODEL,
        on_delete=models.PROTECT, db_index=True,
        related_name='portfolio_double_optin_accounts')
    campaign = models.ForeignKey('Campaign', null=True,
        on_delete=models.PROTECT,
        related_name='portfolio_double_optins')
    ends_at = models.DateTimeField(null=True)
    state = models.PositiveSmallIntegerField(
        choices=STATES, default=OPTIN_REQUEST_INITIATED,
        help_text=_("state of the opt-in"))
    initiated_by = models.ForeignKey(settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE)
    verification_key = models.CharField(max_length=40, null=True, unique=True)
    extra = get_extra_field_class()(null=True, blank=True,
        help_text=_("Extra meta data (can be stringify JSON)"))

    # To connect with payment provider.
    invoice_key = models.CharField(max_length=40, null=True)

    def __str__(self):
        return "<PortfolioDoubleOptIn(grantee='%s', account='%s', "\
            "campaign='%s', ends_at='%s')>" % (self.grantee_id,
            self.account_id, self.campaign_id, self.ends_at)

    def create_portfolios(self, at_time=None):
        if not at_time:
            at_time = datetime_or_now()
        with transaction.atomic():
            Portfolio.objects.update_or_create(
                grantee=self.grantee, account=self.account,
                campaign=self.campaign,
                defaults={'ends_at': at_time})

    @staticmethod
    def generate_key(account):
        random_key = str(random.random()).encode('utf-8')
        salt = hashlib.sha1(random_key).hexdigest()[:5]
        verification_key = hashlib.sha1(
            (salt+str(account)).encode('utf-8')).hexdigest()
        return verification_key

    def grant_accepted(self):
        with transaction.atomic():
            self.create_portfolios()
            self.state = PortfolioDoubleOptIn.OPTIN_GRANT_ACCEPTED
            self.verification_key = None
            self.save()

    def grant_denied(self):
        self.state = PortfolioDoubleOptIn.OPTIN_GRANT_DENIED
        self.verification_key = None
        self.save()

    def grant_expired(self):
        self.state = PortfolioDoubleOptIn.OPTIN_GRANT_EXPIRED
        self.verification_key = None
        self.save()

    def request_accepted(self):
        with transaction.atomic():
            self.create_portfolios()
            self.state = PortfolioDoubleOptIn.OPTIN_REQUEST_ACCEPTED
            self.verification_key = None
            self.save()

    def request_denied(self):
        self.state = PortfolioDoubleOptIn.OPTIN_REQUEST_DENIED
        self.verification_key = None
        self.save()

    def request_expired(self):
        self.state = PortfolioDoubleOptIn.OPTIN_REQUEST_EXPIRED
        self.verification_key = None
        self.save()


def convert_to_source_unit(value, factor, scale, formula):
    """
    Convert value from a target unit to a source unit
    using `factor` and `scale`.
    """
    #pylint:disable=too-many-return-statements
    val = float(value)         # XXX hack to handle `Decimal`

    # Temperatures use a little more complex formula than linear scaling.
    if formula == "1C + 273.15":                  # Celcius to Kelvin
        return val - 273.15
    if formula == "1K - 273.15":                  # Kelvin to Celcius
        return val + 273.15
    if formula == "(1F - 32) * 5/9 + 273.15":     # Farenheit to Kelvin
        return (val - 273.15) * 9/5 + 32
    if formula == "(1K - 273.15) * 9/5 + 32":     # Kelvin to Farenheit
        return (val - 32) * 5/9 + 273.15
    if formula == "(1°C * 9/5) + 32":             # Celcius to Farenheit
        return (val - 32) * 5/9
    if formula == "(1°F - 32) * 5/9":             # Farenheit to Celsius
        return (val * 9/5) + 32

    return value / (factor * scale)


def convert_to_target_unit(value, factor, scale, formula):
    """
    Convert value from a source unit to a target unit
    using `factor` and `scale`.
    """
    #pylint:disable=too-many-return-statements
    val = float(value)         # XXX hack to handle `Decimal`

    # Temperatures use a little more complex formula than linear scaling.
    if formula == "1C + 273.15":                  # Celcius to Kelvin
        return val + 273.15
    if formula == "1K - 273.15":                  # Kelvin to Celcius
        return val - 273.15
    if formula == "(1F - 32) * 5/9 + 273.15":     # Farenheit to Kelvin
        return (val - 32) * 5/9 + 273.15
    if formula == "(1K - 273.15) * 9/5 + 32":     # Kelvin to Farenheit
        return (val - 273.15) * 9/5 + 32
    if formula == "(1°C * 9/5) + 32":             # Celcius to Farenheit
        return (val * 9/5) + 32
    if formula == "(1°F - 32) * 5/9":             # Farenheit to Celsius
        return (val - 32) * 5/9

    return val * factor * scale


def get_collected_by(campaign, start_at=None, ends_at=None,
                     prefix=None, excludes=None):
    """
    Returns users that have actually responded to a campaign, i.e. updated
    at least one answer in a sample completed in the date range
    [created_at, ends_at[.
    """
    #pylint:disable=too-many-arguments
    kwargs = {}
    kwargs.update(Answer.objects.as_sql_campaign_clause(campaign))
    if start_at:
        kwargs.update({
            'answer__created_at__gte': start_at,
            'last_login__gte': start_at,
        })
    if ends_at:
        kwargs.update({'answer__created_at__lt': ends_at})
    if prefix:
        kwargs.update({'answer__question__path__startswith': prefix})
    queryset = get_user_model().objects.filter(
        answer__sample__is_frozen=True,
        **kwargs)

    if excludes:
        queryset = queryset.exclude(answer__question__in=excludes)

    return queryset.distinct()
