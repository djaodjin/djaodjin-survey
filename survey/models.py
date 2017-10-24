# Copyright (c) 2017, DjaoDjin inc.
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
from django.utils.encoding import python_2_unicode_compatible
from django.template.defaultfilters import slugify
from django.utils.timezone import utc
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
class SurveyModel(SlugTitleMixin, models.Model):
    #pylint: disable=super-on-old-class

    slug = models.SlugField(unique=True)
    created_at = models.DateTimeField(null=True)
    ends_at = models.DateTimeField(null=True)
    title = models.CharField(max_length=150,
        help_text="Enter a survey title.")
    description = models.TextField(null=True, blank=True,
        help_text="This description will be displayed to interviewees.")
    published = models.BooleanField(default=False)
    quizz_mode = models.BooleanField(default=False,
        help_text="If checked, correct answser are required")
    account = models.ForeignKey(settings.BELONGS_MODEL, null=True)
    defaults_single_page = models.BooleanField(default=False,
        help_text="If checked, will display all questions on a single page,"\
" else there will be one question per page.")
    one_response_only = models.BooleanField(default=False,
        help_text="Only allows to answer survey once.")

    def __str__(self):
        return self.slug

    def has_questions(self):
        return Question.objects.filter(survey=self).exists()

    def days(self):
        """
        Returns the number of days the survey was available.
        """
        ends_at = created_at = datetime.datetime.now().replace(tzinfo=utc)
        if self.created_at:
            created_at = self.created_at
        if self.ends_at:
            ends_at = self.ends_at
        return (ends_at - created_at).days


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

    text = models.TextField(help_text="Enter your question here.")
    survey = models.ForeignKey(SurveyModel, related_name='questions')
    question_type = models.CharField(
        max_length=9, choices=QUESTION_TYPES, default=TEXT,
        help_text="Choose the type of answser.")
    has_other = models.BooleanField(default=False,
        help_text="If checked, allow user to enter a personnal choice."\
" (Don't forget to add an 'Other' choice at the end of your list of choices)")
    choices = models.TextField(blank=True, null=True,
        help_text="Enter choices here separated by a new line."\
" (Only for radio and select multiple)")
    rank = models.IntegerField()
    correct_answer = models.TextField(blank=True, null=True,
        help_text="Enter correct answser(s) here separated by a new line.")
    required = models.BooleanField(default=True,
        help_text="If checked, an answer is required")

    class Meta:
        unique_together = ('survey', 'rank')

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

    def __str__(self):
        return self.text


class ResponseManager(models.Manager):

    def create_for_account(self, account_name, **kwargs):
        account_lookup_kwargs = {settings.ACCOUNT_LOOKUP_FIELD: account_name}
        return self.create(account=get_account_model().objects.get(
                **account_lookup_kwargs), **kwargs)

    def get_score(self, response): #pylint: disable=no-self-use
        answers = Answer.objects.populate(response)
        nb_correct_answers = 0
        nb_questions = len(answers)
        for answer in answers:
            if answer.question.question_type == Question.RADIO:
                if answer.text in answer.question.get_correct_answer():
                    nb_correct_answers += 1
            elif answer.question.question_type == Question.SELECT_MULTIPLE:
                multiple_choices = answer.get_multiple_choices()
                if len(set(multiple_choices)
                       ^ set(answer.question.get_correct_answer())) == 0:
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
class Response(models.Model):
    """
    Response to a Survey. A Response is composed of multiple Answers
    to Questions.
    """
    objects = ResponseManager()

    slug = models.SlugField()
    created_at = models.DateTimeField(auto_now_add=True)
    survey = models.ForeignKey(SurveyModel, null=True)
    account = models.ForeignKey(settings.ACCOUNT_MODEL, null=True)
    time_spent = models.DurationField(default=datetime.timedelta,
        help_text="Total recorded time to complete the survey")
    is_frozen = models.BooleanField(default=False,
        help_text="When True, answers to that response cannot be updated.")
    extra = settings.get_extra_field_class()(null=True)

    def __str__(self):
        return self.slug

    def save(self, force_insert=False, force_update=False,
             using=None, update_fields=None):
        if not self.slug:
            self.slug = slugify(uuid.uuid4().hex)
        return super(Response, self).save(
            force_insert=force_insert, force_update=force_update,
            using=using, update_fields=update_fields)

    def get_answers_by_rank(self):
        return self.answers.all().order_by('rank') #pylint:disable=no-member


class AnswerManager(models.Manager):

    def populate(self, response):
        """
        Return a list of ``Answer`` for all questions in the survey
        associated to a *response* even when there are no such record
        in the db.
        """
        answers = self.filter(response=response)
        if response.survey:
            questions = Question.objects.filter(survey=response.survey).exclude(
                pk__in=answers.values('question'))
            answers = list(answers)
            for question in questions:
                answers += [Answer(question=question)]
        return answers


@python_2_unicode_compatible
class Answer(models.Model):
    """
    An Answer to a Question as part of Response to a Survey.
    """
    objects = AnswerManager()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    question = models.ForeignKey(Question)
    response = models.ForeignKey(Response, related_name='answers')
    rank = models.IntegerField(help_text="Position in the response list.")
    text = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ("question", "response")

    def __str__(self):
        return '%s-%d' % (self.response.slug, self.rank)

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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    rank = models.IntegerField()
    editable_filter = models.ForeignKey(
        EditableFilter, related_name='predicates')
    operator = models.CharField(max_length=255)
    operand = models.CharField(max_length=255)
    field = models.CharField(max_length=255)
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
    created_at = models.DateTimeField(auto_now_add=True)
    title = models.CharField(max_length=255)
    account = models.ForeignKey(settings.BELONGS_MODEL, null=True)
    metric = models.ForeignKey(EditableFilter, related_name='measured',
        null=True)
    cohorts = models.ManyToManyField(EditableFilter, related_name='matrices')
    cut = models.ForeignKey(EditableFilter, related_name='cuts', null=True)

    def __str__(self):
        return self.slug

