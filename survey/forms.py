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

#pylint: disable=no-member

import uuid

from django import forms
from django.template.defaultfilters import slugify

from .compat import six
from .models import Answer, Campaign, EnumeratedQuestions, Sample
from .utils import get_question_model


def _create_field(ui_hint, text,
                  has_other=False, required=False, choices=None):
    fields = (None, None)
    question_model = get_question_model()
    if ui_hint == question_model.TEXT:
        fields = (forms.CharField(label=text, required=required,
            widget=forms.Textarea), None)
    elif ui_hint == question_model.RADIO:
        radio = forms.ChoiceField(label=text, required=required,
            widget=forms.RadioSelect(), choices=choices)
        if has_other:
            fields = (radio, forms.CharField(required=False,
                label="Please could you specify?",
                widget=forms.TextInput(attrs={'class':'other-input'})))
        else:
            fields = (radio, None)
    elif ui_hint == question_model.DROPDOWN:
        radio = forms.ChoiceField(label=text, required=required,
            widget=forms.Select(), choices=choices)
        if has_other:
            fields = (radio, forms.CharField(required=False,
                label="Please could you specify?",
                widget=forms.TextInput(attrs={'class':'other-input'})))
        else:
            fields = (radio, None)
    elif ui_hint == question_model.SELECT_MULTIPLE:
        multiple = forms.MultipleChoiceField(label=text, required=required,
            widget=forms.CheckboxSelectMultiple, choices=choices)
        if has_other:
            fields = (multiple, forms.CharField(required=False,
                label="Please could you specify?",
                widget=forms.TextInput(attrs={'class':'other-input'})))
        else:
            fields = (multiple, None)
    elif ui_hint == question_model.NUMBER:
        fields = (forms.IntegerField(label=text, required=required), None)
    return fields


class AnswerForm(forms.ModelForm):
    """
    Form used to submit an Answer to a Question as part of Sample to a Campaign.
    """
    class Meta:
        model = Answer
        fields = []

    def __init__(self, *args, **kwargs):
        super(AnswerForm, self).__init__(*args, **kwargs)
        if self.instance.question:
            question = self.instance.question
        elif 'question' in kwargs.get('initial', {}):
            question = kwargs['initial']['question']
        required = True
        if self.instance.sample and self.instance.sample.campaign:
            campaign_attrs = EnumeratedQuestions.objects.filter(
                campaign=self.instance.sample.campaign,
                question=question).first()
            if campaign_attrs:
                required = campaign_attrs.required
        fields = _create_field(question.ui_hint, question.text,
            required=required, choices=question.choices)
        self.fields['text'] = fields[0]

    def save(self, commit=True):
        # We same in the view.
        pass


class QuestionForm(forms.ModelForm):

    title = forms.CharField(label="Title", required=False)
    text = forms.CharField(label="Text", required=False)

    class Meta:
        model = get_question_model()
        fields = ('path', 'default_unit', 'extra')

    def clean_choices(self):
        self.cleaned_data['choices'] = self.cleaned_data['choices'].strip()
        return self.cleaned_data['choices']


class SampleCreateForm(forms.ModelForm):

    class Meta:
        model = Sample
        fields = []

    def __init__(self, *args, **kwargs):
        super(SampleCreateForm, self).__init__(*args, **kwargs)
        for idx, question in enumerate(self.initial.get('questions', [])):
            key = 'question-%d' % (idx + 1)
            required = True
            campaign_attrs = EnumeratedQuestions.objects.filter(
                campaign=self.instance.campaign,
                question=question).first()
            if campaign_attrs:
                required = campaign_attrs.required
            fields = _create_field(question.ui_hint, question.text,
                required=required, choices=question.choices)
            self.fields[key] = fields[0]
            if fields[1]:
                self.fields[key.replace('question-', 'other-')] = fields[1]

    def clean(self):
        super(SampleCreateForm, self).clean()
        items = six.iteritems(self.cleaned_data)
        for key, value in items:
            if key.startswith('other-'):
                if value:
                    self.cleaned_data[key.replace(
                        'other-', 'question-')] = value
                del self.cleaned_data[key]
        return self.cleaned_data

    def save(self, commit=True):
        if 'account' in self.initial:
            self.instance.account = self.initial['account']
        if 'campaign' in self.initial:
            self.instance.campaign = self.initial['campaign']
        self.instance.slug = slugify(uuid.uuid4().hex)
        return super(SampleCreateForm, self).save(commit)


class SampleUpdateForm(forms.ModelForm):
    """
    Auto-generated ``Form`` from a list of ``Question`` in a ``Campaign``.
    """

    class Meta:
        model = Sample
        fields = []

    def __init__(self, *args, **kwargs):
        super(SampleUpdateForm, self).__init__(*args, **kwargs)
        for idx, answer in enumerate(self.instance.get_answers_by_rank()):
            question = answer.question
            required = True
            rank = idx
            campaign_attrs = EnumeratedQuestions.objects.filter(
                campaign=self.instance.campaign,
                question=question).first()
            if campaign_attrs:
                required = campaign_attrs.required
                rank = campaign_attrs.rank
            fields = _create_field(question.ui_hint, question.text,
                required=required, choices=question.choices)
            # XXX set value.
            self.fields['question-%d' % rank] = fields[0]
            if fields[1]:
                self.fields['other-%d' % rank] = fields[1]


class CampaignForm(forms.ModelForm):

    class Meta:
        model = Campaign
        fields = ['title', 'description', 'quizz_mode']

    def clean_title(self):
        """
        Creates a slug from the campaign title and
        checks it does not yet exists.
        """
        slug = slugify(self.cleaned_data.get('title'))
        if Campaign.objects.filter(slug__exact=slug).exists():
            raise forms.ValidationError(
                "Title conflicts with an existing campaign.")
        return self.cleaned_data['title']

    def save(self, commit=True):
        if 'account' in self.initial:
            self.instance.account = self.initial['account']
        self.instance.slug = slugify(self.cleaned_data.get('title'))
        return super(CampaignForm, self).save(commit)


class SendCampaignForm(forms.Form):

    from_address = forms.EmailField(
        help_text="add your email addresse to be contacted")
    to_addresses = forms.CharField(
        widget=forms.Textarea,
        help_text="add email addresses separated by new line")
    message = forms.CharField(widget=forms.Textarea,
       help_text="You can explain the aim of this campaign")
