# Copyright (c) 2021, DjaoDjin inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
# THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
# PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
# CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS;
# OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
# WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR
# OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
# ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""
Convenience module for access of survey app settings, which enforces
default settings when the main settings module does not contain
the appropriate settings.
"""
from django.conf import settings

_SETTINGS = {
    'ACCESSIBLE_ACCOUNTS_CALLABLE': None,
    'ENGAGED_ACCOUNTS_CALLABLE': None,
    'ACCOUNT_LOOKUP_FIELD': 'username',
    'ACCOUNT_MODEL': getattr(
        settings, 'AUTH_USER_MODEL', 'django.contrib.auth.models.User'),
    'ACCOUNT_SERIALIZER': 'survey.api.serializers.AccountSerializer',
    'ACCOUNT_URL_KWARG': 'organization',
    'AUTH_USER_MODEL': getattr(
        settings, 'AUTH_USER_MODEL', 'django.contrib.auth.models.User'),
    'BELONGS_LOOKUP_FIELD': None,
    'BELONGS_MODEL': None,
    'BELONGS_SERIALIZER': None,
    'BYPASS_SAMPLE_AVAILABLE': False,
    'CONTENT_MODEL': 'survey.Content',
    'CONVERT_TO_QUESTION_SYSTEM': True,
    'CORRECT_MARKER': '(correct)',
    'DEFAULT_FROM_EMAIL': getattr(settings, 'DEFAULT_FROM_EMAIL', None),
    'DENORMALIZE_FOR_PRECISION': True,
    'EXTRA_FIELD': None,
    'FORCE_ONLY_QUESTION_UNIT': False,
    'QUESTION_MODEL': 'survey.Question',
    'QUESTION_SERIALIZER': 'survey.api.serializers.QuestionDetailSerializer',
    'SEARCH_FIELDS_PARAM': 'q_f',
    'USER_SERIALIZER': 'survey.api.serializers_overrides.UserSerializer',
    'USER_DETAIL_SERIALIZER': 'survey.api.serializers_overrides.UserSerializer',
}
_SETTINGS.update(getattr(settings, 'SURVEY', {}))

#: overrides the implementation of `survey.utils.get_accessible_accounts`
#: This function must return an iterable over a set of unique ``ACCOUNT_MODEL``.
ACCESSIBLE_ACCOUNTS_CALLABLE = _SETTINGS.get('ACCESSIBLE_ACCOUNTS_CALLABLE')
ENGAGED_ACCOUNTS_CALLABLE = _SETTINGS.get('ENGAGED_ACCOUNTS_CALLABLE')
ACCOUNT_LOOKUP_FIELD = _SETTINGS.get('ACCOUNT_LOOKUP_FIELD')
ACCOUNT_MODEL = _SETTINGS.get('ACCOUNT_MODEL')
ACCOUNT_SERIALIZER = _SETTINGS.get('ACCOUNT_SERIALIZER')
ACCOUNT_URL_KWARG = _SETTINGS.get('ACCOUNT_URL_KWARG')
AUTH_USER_MODEL = _SETTINGS.get('AUTH_USER_MODEL')
BELONGS_LOOKUP_FIELD = (_SETTINGS.get('BELONGS_LOOKUP_FIELD')
    if _SETTINGS.get('BELONGS_LOOKUP_FIELD')
    else _SETTINGS.get('ACCOUNT_LOOKUP_FIELD'))
BELONGS_MODEL = (_SETTINGS.get('BELONGS_MODEL')
    if _SETTINGS.get('BELONGS_MODEL') else _SETTINGS.get('ACCOUNT_MODEL'))
BELONGS_SERIALIZER = (_SETTINGS.get('BELONGS_SERIALIZER')
    if _SETTINGS.get('BELONGS_SERIALIZER')
    else _SETTINGS.get('ACCOUNT_SERIALIZER'))
#: When set to `True` the application will bypass access control and an http
#: request user will have access to all samples.
#: Outside very simple projects, this flag will most likely be used only
#: for debugging purposes.
BYPASS_SAMPLE_AVAILABLE = _SETTINGS.get('BYPASS_SAMPLE_AVAILABLE')
#: When set to `True` storing measure in the database will attempt to convert
#: numerical unit to the question default unit. When set to `False`,
#: no convertion is attempted and the measure is stored with the unit passed
#: as argument. defaults to `True`.
CONVERT_TO_QUESTION_SYSTEM = _SETTINGS.get('CONVERT_TO_QUESTION_SYSTEM')
CONTENT_MODEL = _SETTINGS.get('CONTENT_MODEL')
CORRECT_MARKER = _SETTINGS.get('CORRECT_MARKER')
DEFAULT_FROM_EMAIL = _SETTINGS.get('DEFAULT_FROM_EMAIL')
#: When set to `True` and the measure collected falls out of the natural
#: range to store an integer in the database (ex: 3.2kg), attempts to retain
#: collected precision by using a scaled unit (ex: tons or grams) will be made.
#: defaults to `True`.
DENORMALIZE_FOR_PRECISION = _SETTINGS.get('DENORMALIZE_FOR_PRECISION')
EXTRA_FIELD = _SETTINGS.get('EXTRA_FIELD')
#: When set to `True`, the measure stored in the database are guarenteed
#: to be in the question's default_unit. defaults to `False`.
FORCE_ONLY_QUESTION_UNIT = _SETTINGS.get('FORCE_ONLY_QUESTION_UNIT')
QUESTION_MODEL = _SETTINGS.get('QUESTION_MODEL')
QUESTION_SERIALIZER = _SETTINGS.get('QUESTION_SERIALIZER')
SEARCH_FIELDS_PARAM = _SETTINGS.get('SEARCH_FIELDS_PARAM')
USER_SERIALIZER = _SETTINGS.get('USER_SERIALIZER')
USER_DETAIL_SERIALIZER = _SETTINGS.get('USER_DETAIL_SERIALIZER')

DB_PATH_SEP = '/'
URL_PATH_SEP = '/'
SLUG_RE = r'[a-zA-Z0-9_\-\+\.]+'
