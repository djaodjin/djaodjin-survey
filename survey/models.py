# Copyright (c) 2014, DjaoDjin inc.
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

import datetime, uuid

from django.db import models, IntegrityError
from django.template.defaultfilters import slugify
from django.utils.timezone import utc
from saas.models import Organization

from survey.compat import User


class SurveyModel(models.Model):
    #pylint: disable=super-on-old-class

    slug = models.SlugField(unique=True)
    start_date = models.DateTimeField(null=True)
    end_date = models.DateTimeField(null=True)
    name = models.CharField(max_length=150,
        help_text="Enter a survey name.")
    description = models.TextField(null=True, blank=True,
        help_text="This desciption will be displayed for interviewee.")
    published = models.BooleanField(default=False)
    quizz_mode = models.BooleanField(default=False,
        help_text="If checked, correct answser are required")
    organization = models.ForeignKey(Organization)

    def __unicode__(self):
        return self.slug

    def has_questions(self):
        return Question.objects.filter(survey=self).exists()

    def days(self):
        """
        Returns the number of days the survey was available.
        """
        end_date = start_date = datetime.datetime.now().replace(tzinfo=utc)
        if self.start_date:
            start_date = self.start_date
        if self.end_date:
            end_date = self.end_date
        return (end_date - start_date).days

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):
        #pylint: disable=catching-non-exception
        """
        Keep slug in sync with survey name.
        """
        max_length = self._meta.get_field('slug').max_length
        slug = slugify(self.name)
        self.slug = slug
        if len(self.slug) > max_length:
            self.slug = slug[:max_length]
        num = 1
        while True:
            try:
                return super(SurveyModel, self).save(
                    force_insert=force_insert, force_update=force_update,
                    using=using, update_fields=update_fields)
            except IntegrityError:
                prefix = '-%d' % num
                self.slug = '%s%s' % (slug, prefix)
                if len(self.slug) > max_length:
                    self.slug = '%s-%d' % (slug[:(max_length-len(prefix))], num)
                num = num + 1


class Question(models.Model):

    INTEGER = 'integer'
    RADIO = 'radio'
    SELECT_MULTIPLE = 'checkbox'
    TEXT = 'text'

    QUESTION_TYPES = (
            (TEXT, 'text'),
            (RADIO, 'radio'),
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
    order = models.IntegerField()
    correct_answer = models.TextField(blank=True, null=True,
        help_text="Enter correct answser(s) here separated by a new line.")
    required = models.BooleanField(default=True,
        help_text="If checked, an answer is required")

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

    def __unicode__(self):
        return self.text


class ResponseManager(models.Manager):

    def create(self, **kwargs): #pylint: disable=super-on-old-class
        return super(ResponseManager, self).create(
            slug=slugify(uuid.uuid4().hex), **kwargs)

    def get_score(self, response): #pylint: disable=no-self-use
        answers = Answer.objects.populate(response)
        nb_correct_answers = 0
        nb_questions = len(answers)
        for answer in answers:
            if answer.question.question_type == Question.RADIO:
                if answer.body in answer.question.get_correct_answer():
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


class Response(models.Model):
    """
    Response to a Survey. A Response is composed of multiple Answers
    to Questions.
    """
    objects = ResponseManager()

    slug = models.SlugField()
    created_at = models.DateTimeField(auto_now_add=True)
    survey = models.ForeignKey(SurveyModel, null=True)
    user = models.ForeignKey(User, null=True)
    is_frozen = models.BooleanField(default=False,
        help_text="When True, answers to that response cannot be updated.")

    def __unicode__(self):
        return self.slug


class AnswerManager(models.Manager):

    def populate(self, response):
        """
        Return a list of ``Answer`` for all questions in the survey
        associated to a *response* even when there are no such record
        in the db.
        """
        answers = list(self.filter(response=response))
        if response.survey:
            questions = Question.objects.filter(survey=response.survey).extra(
                where=["(survey_answer.question_id IS NULL)"])
            # XXX check this is True (1.6) JOIN these tables on these fields
            #pylint: disable=protected-access
            connection = (None, Answer._meta.db_table, (("id", "question_id"),))
            questions.query.join(connection,
                outer_if_first=True)    # as LEFT OUTER JOIN
            for question in questions:
                answers += [Answer(question=question)]
        return answers


class Answer(models.Model):
    """
    An Answer to a Question as part of Response to a Survey.
    """
    objects = AnswerManager()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    question = models.ForeignKey(Question)
    response = models.ForeignKey(Response, related_name='answers')
    index = models.IntegerField(help_text="Position in the response list.")
    body = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ("question", "response")

    def __unicode__(self):
        return '%s-%d' % (self.response.slug, self.index)

    def get_multiple_choices(self):
        text = str(self.body)
        return text.replace('[', '').replace(']', '').replace(
            'u\'', '').replace('\'', '').split(', ')
