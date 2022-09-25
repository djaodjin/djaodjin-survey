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

import datetime, logging
from importlib import import_module

from django.apps import apps as django_apps
from django.conf import settings as django_settings
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.core.exceptions import ImproperlyConfigured
from django.db import connections
from django.db.utils import DEFAULT_DB_ALIAS
from django.http.request import split_domain_port, validate_host
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.timezone import utc
from pytz import timezone, UnknownTimeZoneError
from pytz.tzinfo import DstTzInfo

from . import settings
from .compat import six, urlparse, urlunparse


LOGGER = logging.getLogger(__name__)


def as_timestamp(dtime_at=None):
    if not dtime_at:
        dtime_at = datetime_or_now()
    return int((
        dtime_at - datetime.datetime(1970, 1, 1, tzinfo=utc)).total_seconds())


def datetime_or_now(dtime_at=None):
    as_datetime = dtime_at
    if isinstance(dtime_at, six.string_types):
        as_datetime = parse_datetime(dtime_at)
        if not as_datetime:
            as_date = parse_date(dtime_at)
            if as_date:
                as_datetime = datetime.datetime.combine(
                    as_date, datetime.time.min)
    if not as_datetime:
        as_datetime = datetime.datetime.utcnow().replace(tzinfo=utc)
    if as_datetime.tzinfo is None:
        as_datetime = as_datetime.replace(tzinfo=utc)
    return as_datetime


def is_sqlite3(db_key=None):
    if db_key is None:
        db_key = DEFAULT_DB_ALIAS
    return connections.databases[db_key]['ENGINE'].endswith('sqlite3')


def parse_tz(tzone):
    if issubclass(type(tzone), DstTzInfo):
        return tzone
    if tzone:
        try:
            return timezone(tzone)
        except UnknownTimeZoneError:
            pass
    return None


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


def get_content_model():
    """
    Returns the ``Content`` model that is active in this project.
    """
    try:
        return django_apps.get_model(settings.CONTENT_MODEL)
    except ValueError:
        raise ImproperlyConfigured(
            "CONTENT_MODEL must be of the form 'app_label.model_name'")
    except LookupError:
        raise ImproperlyConfigured("CONTENT_MODEL refers to model '%s'"\
" that has not been installed" % settings.CONTENT_MODEL)


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
    Returns the ``QuestionDetailSerializer`` model that is active
    in this project.
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


def validate_redirect(request):
    """
    Get the REDIRECT_FIELD_NAME and validates it is a URL on allowed hosts.
    """
    return validate_redirect_url(request.GET.get(REDIRECT_FIELD_NAME, None))


def validate_redirect_url(next_url):
    """
    Returns the next_url path if next_url matches allowed hosts.
    """
    if not next_url:
        return None
    parts = urlparse(next_url)
    if parts.netloc:
        domain, _ = split_domain_port(parts.netloc)
        allowed_hosts = (['*'] if django_settings.DEBUG
            else django_settings.ALLOWED_HOSTS)
        if not (domain and validate_host(domain, allowed_hosts)):
            return None
    return urlunparse(("", "", parts.path,
        parts.params, parts.query, parts.fragment))


def update_context_urls(context, urls):
    if 'urls' in context:
        for key, val in six.iteritems(urls):
            if key in context['urls']:
                if isinstance(val, dict):
                    context['urls'][key].update(val)
                else:
                    # Because organization_create url is added in this mixin
                    # and in ``OrganizationRedirectView``.
                    context['urls'][key] = val
            else:
                context['urls'].update({key: val})
    else:
        context.update({'urls': urls})
    return context
