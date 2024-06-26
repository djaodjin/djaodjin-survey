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

#pylint: disable=invalid-name,no-name-in-module,unused-import,import-error
#pylint: disable=no-name-in-module,unused-import
import re
from functools import WRAPPER_ASSIGNMENTS
import six

#pylint:disable=no-name-in-module,import-error
from six.moves.urllib.parse import urlparse, urlunparse
from six import StringIO

#pylint:disable=ungrouped-imports
try:
    from datetime import timezone
    import zoneinfo

    def timezone_or_utc(tzone=None):
        if tzone:
            if issubclass(type(tzone), zoneinfo.ZoneInfo):
                return tzone
            try:
                return zoneinfo.ZoneInfo(tzone)
            except zoneinfo.ZoneInfoNotFoundError:
                pass
        return timezone.utc

except ImportError:
    try:
        from datetime import timezone
        from backports import zoneinfo

        def timezone_or_utc(tzone=None):
            if tzone:
                if issubclass(type(tzone), zoneinfo.ZoneInfo):
                    return tzone
                try:
                    return zoneinfo.ZoneInfo(tzone)
                except zoneinfo.ZoneInfoNotFoundError:
                    pass
            return timezone.utc

    except ImportError:
        import pytz
        from pytz.tzinfo import DstTzInfo

        def timezone_or_utc(tzone=None):
            if tzone:
                if issubclass(type(tzone), DstTzInfo):
                    return tzone
                try:
                    return pytz.timezone(tzone)
                except pytz.UnknownTimeZoneError:
                    pass
            return pytz.utc


try:
    from django.apps import apps
    get_model = apps.get_model
except ImportError: # django < 1.8
    from django.db.models.loading import get_model


try:
    from django.template.context_processors import csrf
except ImportError: # django < 1.8
    from django.core.context_processors import csrf


try:
    from django.utils.decorators import available_attrs
except ImportError: # django < 3.0
    def available_attrs(fn):#pylint:disable=unused-argument
        return WRAPPER_ASSIGNMENTS


try:
    from django.urls import NoReverseMatch, reverse, reverse_lazy
except ImportError: # <= Django 1.10, Python<3.6
    from django.core.urlresolvers import NoReverseMatch, reverse, reverse_lazy
except ModuleNotFoundError: #pylint:disable=undefined-variable,bad-except-order
    # <= Django 1.10, Python>=3.6
    from django.core.urlresolvers import NoReverseMatch, reverse, reverse_lazy

try:
    from django.urls import include, path, re_path
except ImportError: # <= Django 2.0, Python<3.6
    from django.conf.urls import include, url as re_path

    def path(route, view, kwargs=None, name=None):
        re_route = re.sub(
                   r'<int:([a-z\_]+)>',
                   r'(?P<\1>[0-9]+)',
            re.sub(r'<path:([a-z\_]+)>',
                   r'(?P<\1>([a-zA-Z0-9\-]+/)*[a-zA-Z0-9\-]+)',
            re.sub(r'<slug:([a-z\_]+)>',
                   r'(?P<\1>[a-zA-Z0-9_\-\+\.]+)',
                   route)))
        return re_path(re_route, view, kwargs=kwargs, name=name)

try:
    from django.utils.encoding import python_2_unicode_compatible
except ImportError: # django < 3.0
    python_2_unicode_compatible = six.python_2_unicode_compatible

try:
    if six.PY3:
        from django.utils.encoding import force_str
    else:
        from django.utils.encoding import force_text as force_str
except ImportError: # django < 3.0
    from django.utils.encoding import force_text as force_str


try:
    from django.utils.module_loading import import_string
except ImportError: # django < 1.7
    from django.utils.module_loading import import_by_path as import_string


try:
    from django.utils.translation import gettext_lazy
except ImportError: # django < 3.0
    from django.utils.translation import ugettext_lazy as gettext_lazy


def is_authenticated(request):
    if callable(request.user.is_authenticated):
        return request.user.is_authenticated()
    return request.user.is_authenticated
