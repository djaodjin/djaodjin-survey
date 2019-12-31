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

import datetime
from importlib import import_module

from django.core.exceptions import ImproperlyConfigured
from django.apps import apps as django_apps
from django.utils import six
from django.utils.dateparse import parse_datetime
from django.utils.timezone import utc

from . import settings


def datetime_or_now(dtime_at=None):
    if not dtime_at:
        return datetime.datetime.utcnow().replace(tzinfo=utc)
    if isinstance(dtime_at, six.string_types):
        dtime_at = parse_datetime(dtime_at)
    if dtime_at.tzinfo is None:
        dtime_at = dtime_at.replace(tzinfo=utc)
    return dtime_at


def get_account_model():
    """
    Returns the ``Account`` model that is active in this project.
    """
    try:
        return django_apps.get_model(settings.ACCOUNT_MODEL)
    except ValueError:
        raise ImproperlyConfigured(
            "ACCOUNT_MODEL must be of the form 'app_label.model_name'")
    except LookupError:
        raise ImproperlyConfigured("ACCOUNT_MODEL refers to model '%s'"\
" that has not been installed" % settings.ACCOUNT_MODEL)


def get_account_serializer():
    """
    Returns the ``AccountSerializer`` model that is active in this project.
    """
    path = settings.ACCOUNT_SERIALIZER
    dot_pos = path.rfind('.')
    module, attr = path[:dot_pos], path[dot_pos + 1:]
    try:
        mod = import_module(module)
    except (ImportError, ValueError) as err:
        raise ImproperlyConfigured(
            "Error importing class '%s' defined by ACCOUNT_SERIALIZER (%s)"
            % (path, err))
    try:
        cls = getattr(mod, attr)
    except AttributeError:
        raise ImproperlyConfigured('Module "%s" does not define a "%s"'\
' check the value of ACCOUNT_SERIALIZER' % (module, attr))
    return cls


def get_belongs_model():
    """
    Returns the ``Account`` model that owns campaigns and matrices.
    """
    try:
        return django_apps.get_model(settings.BELONGS_MODEL)
    except ValueError:
        raise ImproperlyConfigured(
            "BELONGS_MODEL must be of the form 'app_label.model_name'")
    except LookupError:
        raise ImproperlyConfigured("BELONGS_MODEL refers to model '%s'"\
" that has not been installed" % settings.BELONGS_MODEL)


def get_question_model():
    """
    Returns the ``Question`` model that is active in this project.
    """
    try:
        return django_apps.get_model(settings.QUESTION_MODEL)
    except ValueError:
        raise ImproperlyConfigured(
            "QUESTION_MODEL must be of the form 'app_label.model_name'")
    except LookupError:
        raise ImproperlyConfigured("QUESTION_MODEL refers to model '%s'"\
" that has not been installed" % settings.QUESTION_MODEL)


def get_question_serializer():
    """
    Returns the ``QuestionSerializer`` model that is active in this project.
    """
    path = settings.QUESTION_SERIALIZER
    dot_pos = path.rfind('.')
    module, attr = path[:dot_pos], path[dot_pos + 1:]
    try:
        mod = import_module(module)
    except (ImportError, ValueError) as err:
        raise ImproperlyConfigured(
            "Error importing class '%s' defined by QUESTION_SERIALIZER (%s)"
            % (path, err))
    try:
        cls = getattr(mod, attr)
    except AttributeError:
        raise ImproperlyConfigured('Module "%s" does not define a "%s"'\
' check the value of QUESTION_SERIALIZER' % (module, attr))
    return cls
