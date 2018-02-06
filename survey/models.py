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

import datetime, random, uuid

from django.db import models, transaction, IntegrityError
from django.template.defaultfilters import slugify
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext_lazy as _
from rest_framework.exceptions import ValidationError

from . import settings
from .utils import get_account_model


class SlugTitleMixin(object):
    """
    Generate a unique slug from title on ``save()`` when none is specified.
    """
    def save(self, force_insert=False, force_update=False,
             using=None, update_fields=None):
        if self.slug: #pylint:disable=access-member-before-definition
            # serializer will set created slug to '' instead of None.
            return super(SlugTitleMixin, self).save(
                force_insert=force_insert, force_update=force_update,
                using=using, update_fields=update_fields)
        max_length = self._meta.get_field('slug').max_length
        slug_base = slugify(self.title)
        if len(slug_base) > max_length:
            slug_base = slug_base[:max_length]
        self.slug = slug_base
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
                    self.slug = slug_base[:(max_length - len(suffix))] + suffix
                else:
                    self.slug = slug_base + suffix
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

    SYSTEMS = [
            (SYSTEM_STANDARD, 'standard'),
            (SYSTEM_IMPERIAL, 'imperial'),
            (SYSTEM_RANK, 'rank'),
            (SYSTEM_ENUMERATED, 'enum'),
        ]

    slug = models.SlugField(unique=True, db_index=True)
    title = models.CharField(max_length=50)
    system = models.PositiveSmallIntegerField(
        choices=SYSTEMS, default=SYSTEM_STANDARD)

    def __str__(self):
        return self.slug


@python_2_unicode_compatible
class Choice(models.Model):
    """
    Choice for a multiple choice question.
    """
    unit = models.ForeignKey(Unit)
    rank = models.IntegerField(
        help_text=_("used to order choice when presenting a question"))
    text = models.TextField()

    class Meta:
        unique_together = ('unit', 'rank')

    def __str__(self):
        return self.text


@python_2_unicode_compatible
class Metric(models.Model):
    """
    Metric on a ``Question``.
    """
    slug = models.SlugField(unique=True, db_index=True)
    title = models.CharField(max_length=50)
    unit = models.ForeignKey(Unit)

    def __str__(self):
        return self.slug


@python_2_unicode_compatible
class Question(models.Model):

    INTEGER = 'integer'
    RADIO = 'radio'
    DROPDOWN = 'select'
    SELECT_MULTIPLE = 'checkbox'
    TEXT = 'text'

    QUESTION_TYPES = (
            (TEXT, 'text'),
            (RADIO, 'radio'),
            (DROPDOWN, 'dropdown'),
            (SELECT_MULTIPLE, 'Select Multiple'),
            (INTEGER, 'integer'),
    )

    path = models.CharField(max_length=1024, unique=True, db_index=True)
    title = models.CharField(max_length=50)
    text = models.TextField(
        help_text=_("Detailed description about the question"))
    question_type = models.CharField(
        max_length=9, choices=QUESTION_TYPES, default=TEXT,
        help_text=_("Choose the type of answser."))
    correct_answer = models.ForeignKey(Choice, null=True)
    default_metric = models.ForeignKey(Metric)
    extra = settings.get_extra_field_class()(null=True)

    def __str__(self):
        return self.path

    def get_choices(self):
        choices_list = []
        if self.choices:
            #pylint: disable=no-member
            for choice in self.choices.split('\n'):
                choice = choice.strip()
                choices_list += [(choice, choice)]
        return choices_list

    def get_correct_answer(self):
        correct_answer_list = []
        if self.correct_answer:
            #pylint: disable=no-member
            correct_answer_list = [
                asw.strip() for asw in self.correct_answer.split('\n')]
        return correct_answer_list


@python_2_unicode_compatible
class Campaign(SlugTitleMixin, models.Model):
    #pylint: disable=super-on-old-class

    slug = models.SlugField(unique=True)
    created_at = models.DateTimeField(null=True)
    title = models.CharField(max_length=150,
        help_text=_("Enter a survey title."))
    description = models.TextField(null=True, blank=True,
        help_text=_("This description will be displayed to interviewees."))
    account = models.ForeignKey(settings.BELONGS_MODEL, null=True)
    active = models.BooleanField(default=False)
    quizz_mode = models.BooleanField(default=False,
        help_text=_("If checked, correct answser are required"))
    defaults_single_page = models.BooleanField(default=False,
        help_text=_("If checked, will display all questions on a single page,"\
" else there will be one question per page."))
    one_response_only = models.BooleanField(default=False,
        help_text=_("Only allows to answer survey once."))
    questions = models.ManyToManyField(Question,
        through='survey.EnumeratedQuestions', related_name='campaigns')
    extra = settings.get_extra_field_class()(null=True)

    def __str__(self):
        return self.slug

    def has_questions(self):
        return self.questions.exists()


@python_2_unicode_compatible
class EnumeratedQuestions(models.Model):

    campaign = models.ForeignKey(Campaign)
    question = models.ForeignKey(Question)
    rank = models.IntegerField(
        help_text=_("used to order questions when presenting a campaign."))
    required = models.BooleanField(default=True,
        help_text=_("If checked, an answer is required"))

    class Meta:
        unique_together = ('campaign', 'question', 'rank')

    def __str__(self):
        return self.question.path


class SampleManager(models.Manager):

    def create_for_account(self, account_name, **kwargs):
        account_lookup_kwargs = {settings.ACCOUNT_LOOKUP_FIELD: account_name}
        return self.create(account=get_account_model().objects.get(
                **account_lookup_kwargs), **kwargs)

    def get_score(self, sample): #pylint: disable=no-self-use
        answers = Answer.objects.populate(sample)
        nb_correct_answers = 0
        nb_questions = len(answers)
        for answer in answers:
            if answer.question.question_type == Question.RADIO:
                if answer.text in answer.question.get_correct_answer():
                    nb_correct_answers += 1
            elif answer.question.question_type == Question.SELECT_MULTIPLE:
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

    slug = models.SlugField()
    created_at = models.DateTimeField(auto_now_add=True)
    survey = models.ForeignKey(Campaign, null=True)
    account = models.ForeignKey(settings.ACCOUNT_MODEL, null=True)
    time_spent = models.DurationField(default=datetime.timedelta,
        help_text="Total recorded time to complete the survey")
    is_frozen = models.BooleanField(default=False,
        help_text="When True, answers to that sample cannot be updated.")
    extra = settings.get_extra_field_class()(null=True)

    def __str__(self):
        return self.slug

    def save(self, force_insert=False, force_update=False,
             using=None, update_fields=None):
        if not self.slug:
            self.slug = slugify(uuid.uuid4().hex)
        return super(Sample, self).save(
            force_insert=force_insert, force_update=force_update,
            using=using, update_fields=update_fields)

    def get_answers_by_rank(self):
        return self.answers.all().order_by('rank') #pylint:disable=no-member


class AnswerManager(models.Manager):

    def populate(self, sample):
        """
        Return a list of ``Answer`` for all questions in the survey
        associated to a *sample* even when there are no such record
        in the db.
        """
        answers = self.filter(sample=sample)
        if sample.survey:
            questions = Question.objects.filter(survey=sample.survey).exclude(
                pk__in=answers.values('question'))
            answers = list(answers)
            for question in questions:
                answers += [Answer(question=question)]
        return answers


@python_2_unicode_compatible
class Answer(models.Model):
    """
    An Answer to a Question as part of Sample to a Campaign.
    """
    objects = AnswerManager()

    created_at = models.DateTimeField(auto_now_add=True)
    question = models.ForeignKey(Question)
    metric = models.ForeignKey(Metric)
    measured = models.IntegerField(null=True)
    collected_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True)
    # Optional fields when the answer is part of a survey campaign.
    sample = models.ForeignKey(Sample, related_name='answers')
    rank = models.IntegerField(default=0,
        help_text=_("used to order answers when presenting a sample."))

    class Meta:
        unique_together = ("question", "sample")

    def __str__(self):
        return '%s-%d' % (self.sample.slug, self.rank)

    @property
    def as_text_value(self):
        return Choice.objects.get(pk=self.measured).text

    def get_multiple_choices(self):
        text = str(self.text)
        return text.replace('[', '').replace(']', '').replace(
            'u\'', '').replace('\'', '').split(', ')


@python_2_unicode_compatible
class EditableFilter(SlugTitleMixin, models.Model):
    """
    A model type and list of predicates to create a subset of the
    of the rows of a model type
    """

    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=255)
    tags = models.CharField(max_length=255)

    def __str__(self):
        return self.slug

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
        EditableFilter, related_name='predicates')
    operator = models.CharField(max_length=255)
    operand = models.CharField(max_length=255)
    field = models.CharField(max_length=255) # field on a Question.
    selector = models.CharField(max_length=255)

    def __str__(self):
        return '%s-%d' % (self.portfolio.slug, self.rank)

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
class Matrix(SlugTitleMixin, models.Model):
    """
    Represent a set of cohorts against a metric.
    """

    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True,
        help_text=_("Long form description of the matrix"))
    account = models.ForeignKey(settings.BELONGS_MODEL, null=True)
    metric = models.ForeignKey(EditableFilter, related_name='measured',
        null=True)
    cohorts = models.ManyToManyField(EditableFilter, related_name='matrices')
    cut = models.ForeignKey(EditableFilter, related_name='cuts', null=True)
    extra = settings.get_extra_field_class()(null=True)

    def __str__(self):
        return self.slug
