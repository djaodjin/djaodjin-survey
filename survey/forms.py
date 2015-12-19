# Copyright (c) 2015, DjaoDjin inc.
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

#pylint: disable=no-member
#pylint: disable=super-on-old-class

import uuid

from django import forms
from django.template.defaultfilters import slugify

from survey.models import Answer, Question, Response, SurveyModel


def _create_field(question_type, text,
                  has_other=False, required=False, choices=None):
    fields = (None, None)
    if question_type == Question.TEXT:
        fields = (forms.CharField(label=text, required=required,
            widget=forms.Textarea), None)
    elif question_type == Question.RADIO:
        radio = forms.ChoiceField(label=text, required=required,
            widget=forms.RadioSelect(), choices=choices)
        if has_other:
            fields = (radio, forms.CharField(required=False,
                label="Please could you specify?",
                widget=forms.TextInput(attrs={'class':'other-input'})))
        else:
            fields = (radio, None)
    elif question_type == Question.SELECT_MULTIPLE:
        multiple = forms.MultipleChoiceField(label=text, required=required,
            widget=forms.CheckboxSelectMultiple, choices=choices)
        if has_other:
            fields = (multiple, forms.CharField(required=False,
                label="Please could you specify?",
                widget=forms.TextInput(attrs={'class':'other-input'})))
        else:
            fields = (multiple, None)
    elif question_type == Question.INTEGER:
        fields = (forms.IntegerField(label=text, required=required), None)
    return fields


class AnswerForm(forms.ModelForm):
    """
    Form used to submit an Answer to a Question as part of Response to a Survey.
    """

    class Meta:
        model = Answer
        fields = ('body',)

    def __init__(self, *args, **kwargs):
        super(AnswerForm, self).__init__(*args, **kwargs)
        if self.initial.has_key('question'):
            setattr(self.instance, 'question', self.initial['question'])
        if self.initial.has_key('response'):
            setattr(self.instance, 'response', self.initial['response'])
        question = self.instance.question
        fields = _create_field(question.question_type, question.text,
            has_other=question.has_other, required=question.required,
            choices=question.get_choices())
        self.fields['body'] = fields[0]
        if fields[1]:
            self.fields['other'] = fields[1]

    def save(self, commit=True):
        if self.instance.question.has_other and self.cleaned_data['other']:
            self.cleaned_data['body'] += self.cleaned_data['other']
        return super(AnswerForm, self).save(commit)


class QuestionForm(forms.ModelForm):

    class Meta:
        model = Question
        exclude = ['survey', 'order']

    def save(self, commit=True):
        if self.initial.has_key('survey'):
            self.instance.survey = self.initial['survey']
        if self.initial.has_key('order') and not self.instance.order:
            self.instance.order = self.initial['order']
        return super(QuestionForm, self).save(commit)

    def clean_choices(self):
        self.cleaned_data['choices'] = self.cleaned_data['choices'].strip()
        return self.cleaned_data['choices']

    def clean_correct_answer(self):
        self.cleaned_data['correct_answer'] \
            = self.cleaned_data['correct_answer'].strip()
        return self.cleaned_data['correct_answer']


class ResponseCreateForm(forms.ModelForm):

    class Meta:
        model = Response
        fields = []

    def __init__(self, *args, **kwargs):
        super(ResponseCreateForm, self).__init__(*args, **kwargs)
        for idx, question in enumerate(self.initial.get('questions', [])):
            key = 'question-%d' % (idx + 1)
            fields = _create_field(question.question_type, question.text,
                has_other=question.has_other, required=question.required,
                choices=question.get_choices())
            self.fields[key] = fields[0]
            if fields[1]:
                self.fields[key.replace('question-', 'other-')] = fields[1]

    def clean(self):
        super(ResponseCreateForm, self).clean()
        items = self.cleaned_data.items()
        for key, value in items:
            if key.startswith('other-'):
                if value:
                    self.cleaned_data[key.replace(
                        'other-', 'question-')] = value
                del self.cleaned_data[key]
        return self.cleaned_data

    def save(self, commit=True):
        if self.initial.has_key('user'):
            self.instance.user = self.initial['user']
        if self.initial.has_key('survey'):
            self.instance.survey = self.initial['survey']
        self.instance.slug = slugify(uuid.uuid4().hex)
        return super(ResponseCreateForm, self).save(commit)


class ResponseUpdateForm(forms.ModelForm):
    """
    Auto-generated ``Form`` from a list of ``Question`` in a ``SurveyModel``.
    """

    class Meta:
        model = Response
        fields = []

    def __init__(self, *args, **kwargs):
        super(ResponseUpdateForm, self).__init__(*args, **kwargs)
        for answer in self.instance.answers.order_by('index'):
            question = answer.question
            fields = _create_field(question.question_type, question.text,
                has_other=question.has_other, required=question.required,
                choices=question.get_choices())
            # XXX set value.
            self.fields['question-%d' % answer.index] = fields[0]
            if fields[1]:
                self.fields['other-%d' % answer.index] = fields[1]


class SurveyForm(forms.ModelForm):

    class Meta:
        model = SurveyModel
        fields = ['title', 'description', 'quizz_mode']

    def clean_title(self):
        """
        Creates a slug from the survey title and checks it does not yet exists.
        """
        slug = slugify(self.cleaned_data.get('title'))
        if SurveyModel.objects.filter(slug__exact=slug).exists():
            raise forms.ValidationError(
                "Title conflicts with an existing survey.")
        return self.cleaned_data['title']

    def save(self, commit=True):
        if self.initial.has_key('account'):
            self.instance.account = self.initial['account']
        self.instance.slug = slugify(self.cleaned_data.get('title'))
        return super(SurveyForm, self).save(commit)


class SendSurveyForm(forms.Form):

    from_address = forms.EmailField(
        help_text="add your email addresse to be contacted")
    to_addresses = forms.CharField(
        widget=forms.Textarea,
        help_text="add email addresses separated by new line")
    message = forms.CharField(widget=forms.Textarea,
       help_text="You can explain the aim of this survey")

