# Copyright (c) 2023, DjaoDjin inc.
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
"""
This file contains functions useful throughout the whole project which do
not require to import `django` modules.

See utils.py for functions useful throughout the whole project which depend
on importing Django models.
"""
import datetime, json

from dateutil.relativedelta import relativedelta, SU
from pytz import timezone, utc, UnknownTimeZoneError
from pytz.tzinfo import DstTzInfo

from .compat import six

def period_less_than(left, right, period='yearly'):
    if period == 'monthly':
        return left.year < right.year or (
            left.year == right.year and left.month < right.month)
    return left.year < right.year


def construct_monthly_periods(first_date, last_date, years=0, tzone=None):
    at_time = first_date
    tzinfo = parse_tz(tzone)
    if not tzinfo:
        tzinfo = utc
    months_ends_at = []
    while at_time < last_date:
        ends_at = datetime.datetime(
            year=at_time.year, month=at_time.month, day=1)
        if tzinfo:
            # we are interested in 00:00 local time, if we don't have
            # local time zone, fall back to 00:00 utc time
            # in case we have local timezone, replace utc with it
            ends_at = tzinfo.localize(ends_at.replace(tzinfo=None))
        years_shifted = ends_at + relativedelta(years=years)
        months_ends_at += [years_shifted]
        at_time += relativedelta(months=1)
    return months_ends_at


def _construct_weekly_period(at_time, years=0, tzone=None):
    # discarding time, keeping utc tzinfo (00:00:00 utc)
    today = at_time.replace(hour=0, minute=0, second=0, microsecond=0)
    tzinfo = parse_tz(tzone)
    if tzinfo:
        # we are interested in 00:00 local time, if we don't have
        # local time zone, fall back to 00:00 utc time
        # in case we have local timezone, replace utc with it
        today = tzinfo.localize(today.replace(tzinfo=None))
    if today.weekday() == SU:
        sunday = today
    else:
        sunday = today + relativedelta(weekday=SU)

    week_of_year = sunday.isocalendar()
    # Implementation note: `%G` was introduced in Python3.6
    years_shifted_sunday = datetime.datetime.strptime('%d %d %d' % (
        week_of_year[0] + years, week_of_year[1], week_of_year[2]),
        '%G %V %u').replace(tzinfo=sunday.tzinfo)

    last_sunday = years_shifted_sunday + relativedelta(weeks=-1, weekday=SU)
    return last_sunday, years_shifted_sunday


def construct_weekly_periods(first_date, last_date, years=0, tzone=None):
    at_time = first_date
    week_ends_at = []
    while at_time < last_date:
        _, ends_at = _construct_weekly_period(at_time, years=years, tzone=tzone)
        week_ends_at += [ends_at]
        at_time += relativedelta(weeks=1)
    return week_ends_at


def construct_yearly_periods(first_date, last_date, tzone=None):
    """
    Attention! This function will create yearly periods centered around
    `first_date` - i.e. if first_date in Aug 31st, all dates within
    the returned periods will land on Aug 31st.
    """
    at_time = first_date
    tzinfo = parse_tz(tzone)
    if not tzinfo:
        tzinfo = utc
    period_ends_at = []
    while at_time <= last_date:
        ends_at = datetime.datetime(year=at_time.year, month=1, day=1)
        if tzinfo:
            # we are interested in 00:00 local time, if we don't have
            # local time zone, fall back to 00:00 utc time
            # in case we have local timezone, replace utc with it
            ends_at = tzinfo.localize(ends_at.replace(tzinfo=None))
        period_ends_at += [ends_at]
        at_time += relativedelta(years=1)
    return period_ends_at


def extra_as_internal(obj):
    if not hasattr(obj, 'extra'):
        return {}
    if isinstance(obj.extra, six.string_types):
        try:
            obj.extra = json.loads(obj.extra)
        except (TypeError, ValueError):
            pass
    return obj.extra


def get_extra(obj, attr_name, default=None):
    if not hasattr(obj, 'extra'):
        return default
    if isinstance(obj.extra, six.string_types):
        try:
            obj.extra = json.loads(obj.extra)
        except (TypeError, ValueError):
            return default
    return obj.extra.get(attr_name, default) if obj.extra else default


def parse_tz(tzone):
    if issubclass(type(tzone), DstTzInfo):
        return tzone
    if tzone:
        try:
            return timezone(tzone)
        except UnknownTimeZoneError:
            pass
    return None


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
