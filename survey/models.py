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

import hashlib, random, uuid

from django.db import models, transaction, IntegrityError
from django.template.defaultfilters import slugify
from rest_framework.exceptions import ValidationError

from . import settings
from .compat import (gettext_lazy as _, import_string,
    python_2_unicode_compatible)
from .utils import datetime_or_now, get_account_model, get_question_model


def get_extra_field_class():
    extra_class = settings.EXTRA_FIELD
    if extra_class is None:
        extra_class = models.TextField
    elif isinstance(extra_class, str):
        extra_class = import_string(extra_class)
    return extra_class


class SlugTitleMixin(object):
    """
    Generate a unique slug from title on ``save()`` when none is specified.
    """
    slug_field = 'slug'

    def save(self, force_insert=False, force_update=False,
             using=None, update_fields=None):
        if getattr(self, self.slug_field):
            # serializer will set created slug to '' instead of None.
            return super(SlugTitleMixin, self).save(
                force_insert=force_insert, force_update=force_update,
                using=using, update_fields=update_fields)
        max_length = self._meta.get_field(self.slug_field).max_length
        slug_base = slugify(self.title)
        if len(slug_base) > max_length:
            slug_base = slug_base[:max_length]
        setattr(self, self.slug_field, slug_base)
        for _ in range(1, 10):
            try:
                with transaction.atomic():
                    return super(SlugTitleMixin, self).save(
                        force_insert=force_insert, force_update=force_update,
                        using=using, update_fields=update_fields)
            except IntegrityError as err:
                if 'uniq' not in str(err).lower():
                    raise
                suffix = '-%s' % "".join([random.choice("abcdef0123456789")
                    for _ in range(7)])
                if len(slug_base) + len(suffix) > max_length:
                    setattr(self, self.slug_field,
                        slug_base[:(max_length - len(suffix))] + suffix)
                else:
                    setattr(self, self.slug_field, slug_base + suffix)
        raise ValidationError({'detail':
            "Unable to create a unique URL slug from title '%s'" % self.title})


@python_2_unicode_compatible
class Unit(models.Model):
    """
    Unit in which an ``Answer.measured`` value is collected.
    """

    SYSTEM_STANDARD = 0
    SYSTEM_IMPERIAL = 1
    SYSTEM_RANK = 2
    SYSTEM_ENUMERATED = 3
    SYSTEM_FREETEXT = 4
    SYSTEM_DATETIME = 5

    SYSTEMS = [
            (SYSTEM_STANDARD, 'standard'),
            (SYSTEM_IMPERIAL, 'imperial'),
            (SYSTEM_RANK, 'rank'),
            (SYSTEM_ENUMERATED, 'enum'),
            (SYSTEM_FREETEXT, 'freetext'),
            (SYSTEM_DATETIME, 'datetime'),
        ]

    NUMERICAL_SYSTEMS = [
        SYSTEM_STANDARD,
        SYSTEM_IMPERIAL,
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


@python_2_unicode_compatible
class UnitEquivalences(models.Model):
    """
    Pairs of units that can be translated one to the other.
    """
    source = models.ForeignKey(Unit, on_delete=models.CASCADE,
        related_name='source_equivalences',
        help_text=_("Source unit in the equivalence"))
    target = models.ForeignKey(Unit, on_delete=models.CASCADE,
        related_name='target_equivalences',
        help_text=_("Target unit in the equivalence"))
    content = models.TextField(null=True,
        help_text=_("Description of the equivalence function"))

    def __str__(self):
        return "%s:%s" % (self.source, self.target)


@python_2_unicode_compatible
class Choice(models.Model):
    """
    Choice for a multiple choice question.
    """
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT,
            related_name='enums')
    question = models.ForeignKey(settings.QUESTION_MODEL,
        on_delete=models.PROTECT, null=True)
    rank = models.IntegerField(
        help_text=_("used to order choice when presenting a question"))
    text = models.TextField()
    descr = models.TextField()

    class Meta:
        unique_together = ('unit', 'question', 'rank')

    def __str__(self):
        return str(self.text)


@python_2_unicode_compatible
class Content(models.Model):

    title = models.CharField(max_length=50,
        help_text=_("Short description"))
    text = models.TextField(
        help_text=_("Detailed description about the question"))

    def __str__(self):
        return slugify(self.title)


@python_2_unicode_compatible
class AbstractQuestion(SlugTitleMixin, models.Model):

    slug_field = 'path'

    TEXT = 'textarea'
    RADIO = 'radio'
    NUMBER = 'number'
    ENERGY = 'energy'
    WATER = 'water'
    WASTE = 'waste'
    GHG_EMISSIONS = 'ghg-emissions'
    GHG_EMISSIONS_SCOPE3 = 'ghg-emissions-scope3'

    UI_HINTS = (
            (TEXT, 'textarea'),
            (RADIO, 'radio'),
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
        on_delete=models.PROTECT, related_name='question')
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

# XXX Before migration:
#    pass
# XXX After migration
    class Meta(AbstractQuestion.Meta):
        swappable = 'QUESTION_MODEL'

    def __str__(self):
        return str(self.path)


@python_2_unicode_compatible
class Campaign(SlugTitleMixin, models.Model):

    slug = models.SlugField(unique=True,
        help_text=_("Unique identifier that can be used in a URL"))
    created_at = models.DateTimeField(auto_now_add=True)
    title = models.CharField(max_length=150,
        help_text=_("Enter a campaign title."))
    description = models.TextField(null=True, blank=True,
        help_text=_("This description will be displayed to interviewees."))
    account = models.ForeignKey(settings.BELONGS_MODEL,
        on_delete=models.PROTECT, null=True)
    active = models.BooleanField(default=False,
        help_text=_("Whether the campaign is available or not"))
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
    extra = get_extra_field_class()(null=True)

    def __str__(self):
        return str(self.slug)

    def has_questions(self):
        return self.questions.exists()

    def get_questions(self, prefix=None):
        if prefix:
            return self.questions.filter(prefx=prefix)
        return self.questions.all()


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

    def get_latest_frozen_by_accounts(self, campaign,
                                      before=None, excludes=None):
        """
        Returns the most recent frozen assessment before an optionally specified
        date, indexed by account.

        All accounts in ``excludes`` are not added to the index. This is
        typically used to filter out 'testing' accounts
        """
        #pylint:disable=no-self-use
        if excludes:
            if isinstance(excludes, list):
                excludes = ','.join([
                    str(account_id) for account_id in excludes])
            filter_out_testing = (
                "AND survey_sample.account_id NOT IN (%s)" % str(excludes))
        else:
            filter_out_testing = ""
        before_clause = ("AND created_at < '%s'" % before.isoformat()
            if before else "")
        sql_query = """SELECT
    survey_sample.account_id AS account_id,
    survey_sample.id AS id,
    survey_sample.created_at AS created_at
FROM survey_sample
INNER JOIN (
    SELECT
        account_id,
        MAX(created_at) AS last_updated_at
    FROM survey_sample
    WHERE survey_sample.campaign_id = %(campaign_id)d AND
          survey_sample.is_frozen
          %(before_clause)s
          %(filter_out_testing)s
    GROUP BY account_id) AS last_updates
ON survey_sample.account_id = last_updates.account_id AND
   survey_sample.created_at = last_updates.last_updated_at
WHERE survey_sample.is_frozen
""" % {'campaign_id': campaign.pk,
       'before_clause': before_clause,
       'filter_out_testing': filter_out_testing}
        return self.raw(sql_query)

    def get_score(self, sample): #pylint: disable=no-self-use
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
    created_at = models.DateTimeField(auto_now_add=True,
        help_text="Date/time of creation (in ISO format)")
    updated_at = models.DateTimeField(auto_now_add=True,
        help_text="Date/time of last update (in ISO format)")
    campaign = models.ForeignKey(Campaign, null=True, on_delete=models.PROTECT)
    account = models.ForeignKey(settings.ACCOUNT_MODEL,
        null=True, on_delete=models.PROTECT, related_name='samples')
    is_frozen = models.BooleanField(default=False,
        help_text="When True, answers to that sample cannot be updated.")
    extra = get_extra_field_class()(null=True)

    def __str__(self):
        return str(self.slug)

    @property
    def time_spent(self):
        return self.updated_at - self.created_at

    @property
    def nb_answers(self):
        if not hasattr(self, '_nb_answers'):
            self._nb_answers = Answer.objects.filter(
                sample=self,
                question__default_unit=models.F('unit_id')).count()
        return self._nb_answers

    @property
    def nb_required_answers(self):
        if not hasattr(self, '_nb_required_answers'):
            self._nb_required_answers = Answer.objects.filter(
                sample=self,
                question__default_unit=models.F('unit_id'),
                question__enumeratedquestions__required=True,
                question__enumeratedquestions__campaign=self.campaign).count()
        return self._nb_required_answers

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
                rank=models.F('question__enumeratedquestions__rank'))
        return queryset


class AnswerManager(models.Manager):

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
    objects = AnswerManager()

    created_at = models.DateTimeField()
    question = models.ForeignKey(settings.QUESTION_MODEL,
        on_delete=models.PROTECT)
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT)
    measured = models.IntegerField(null=True)
    denominator = models.IntegerField(null=True, default=1)
    collected_by = models.ForeignKey(settings.AUTH_USER_MODEL,
        null=True, on_delete=models.PROTECT)
    # XXX Optional fields when the answer is part of a campaign.
    sample = models.ForeignKey(Sample, on_delete=models.CASCADE,
        related_name='answers')

    class Meta:
        unique_together = ('sample', 'question', 'unit')

    def __str__(self):
        if self.sample_id:
            return '%s-%d' % (self.sample.slug, self.rank)
        return self.question.content.slug

    @property
    def as_text_value(self):
        if self.unit.system in Unit.NUMERICAL_SYSTEMS:
            return self.measured
        return Choice.objects.get(pk=self.measured).text

    @property
    def rank(self):
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
class EditableFilter(SlugTitleMixin, models.Model):
    """
    A model type and list of predicates to create a subset of the
    of the rows of a model type
    """

    slug = models.SlugField(unique=True,
        help_text="Unique identifier for the sample. It can be used in a URL.")
    title = models.CharField(max_length=255,
        help_text="Title for the filter")
    account = models.ForeignKey(settings.BELONGS_MODEL,
        on_delete=models.PROTECT, null=True)
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
        return '%s-%d' % (self.portfolio.slug, int(self.rank))

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
    account = models.ForeignKey(settings.ACCOUNT_MODEL,
        on_delete=models.CASCADE, related_name='filters')

    class Meta:
        unique_together = ('editable_filter', 'rank')

    def __str__(self):
        return '%s-%d' % (self.editable_filter.slug, int(self.rank))


@python_2_unicode_compatible
class Matrix(SlugTitleMixin, models.Model):
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
    extra = get_extra_field_class()(null=True)

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

    class Meta:
        unique_together = (('grantee', 'account', 'campaign'),)

    def __str__(self):
        return "portfolio-%s-%d" % (self.grantee, self.pk)


class PortfolioDoubleOptInManager(models.Manager):

    def by_invoice_keys(self, invoice_keys):
        return self.filter(invoice_key__in=invoice_keys)

    def get_requested_by(self, account, ends_at=None):
        kwargs = {}
        if ends_at:
            kwargs.update({'ends_at__lt': ends_at})
        return self.filter(grantee=account, grant_key__isnull=True, **kwargs)

    def get_requested_on(self, account, ends_at=None):
        kwargs = {}
        if ends_at:
            kwargs.update({'ends_at__lt': ends_at})
        return self.filter(account=account, grant_key__isnull=True, **kwargs)

    def unsolicited(self, account, ends_at=None):
        kwargs = {}
        if ends_at:
            kwargs.update({'ends_at__lt': ends_at})
        return self.filter(grantee=account, request_key__isnull=True, **kwargs)

    def accepted(self, account, ends_at=None):
        """
        Returns a ``QuerySet`` of portfolios that were accepted by
        their respective accounts but which haven't been invoiced yet.
        """
        kwargs = {}
        if ends_at:
            kwargs.update({'ends_at__lt': ends_at})
        return self.filter(grantee=account, request_key__isnull=False,
            grant_key=PortfolioDoubleOptIn.ACCEPTED, invoice_key__isnull=True,
            **kwargs)


@python_2_unicode_compatible
class PortfolioDoubleOptIn(models.Model):
    """
    Intermidiary object to implement double opt-in through requests and grants.

    When ``grantee`` is null, we must have a valid e-mail address to send
    the grant to.

    ``invoice_key`` is used as a identity token that will be passed back
    by the payment processor when a charge was successfully created.
    When we see ``invoice_key`` back, we create the ``Portfolio`` records.

    State definition (bits)
                         request/grant | accept/denied | completed
    grant initiated                  1               0           0
    grant accepted                   1               1           1
    grant denied                     1               0           1
    request initiated                0               0           0
    request accepted                 0               1           1
    request denied                   0               0           1
    """
    OPTIN_GRANT_INITIATED = 4
    OPTIN_GRANT_ACCEPTED = 7
    OPTIN_GRANT_DENIED = 5
    OPTIN_REQUEST_INITIATED = 0
    OPTIN_REQUEST_ACCEPTED = 1
    OPTIN_REQUEST_DENIED = 3

    STATES = [
        (OPTIN_GRANT_INITIATED, 'grant-initiated'),
        (OPTIN_GRANT_ACCEPTED, 'grant-accepted'),
        (OPTIN_GRANT_DENIED, 'grant-denied'),
        (OPTIN_REQUEST_INITIATED, 'request-initiated'),
        (OPTIN_REQUEST_ACCEPTED, 'request-accepted'),
        (OPTIN_REQUEST_DENIED, 'request-denied'),
    ]

    objects = PortfolioDoubleOptInManager()

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

    # To connect with payment provider.
    invoice_key = models.CharField(max_length=40, null=True)

    def __str__(self):
        return "<PortfolioDoubleOptIn(grantee='%s', account='%s', "\
            "campaign='%s', ends_at='%s')>" % (self.grantee_id,
            self.account_id, self.campaign_id, self.ends_at)

    def create_portfolios(self):
        with transaction.atomic():
            Portfolio.objects.update_or_create(
                grantee=self.grantee, account=self.account,
                campaign=self.campaign,
                defaults={'ends_at': self.ends_at})

    @staticmethod
    def generate_key(account):
        random_key = str(random.random()).encode('utf-8')
        salt = hashlib.sha1(random_key).hexdigest()[:5]
        verification_key = hashlib.sha1(
            (salt+str(account)).encode('utf-8')).hexdigest()
        return verification_key
