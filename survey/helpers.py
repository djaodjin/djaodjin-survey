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
import datetime, json, random

from dateutil.relativedelta import relativedelta, SU
from django.db import transaction, IntegrityError
from django.template.defaultfilters import slugify
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework.exceptions import ValidationError

from .compat import timezone_or_utc, six

HOURLY = 'hourly'
DAILY = 'daily'
WEEKLY = 'weekly'
MONTHLY = 'monthly'
YEARLY = 'yearly'


class SlugifyFieldMixin(object):
    """
    Generate a unique slug from title on ``save()`` when none is specified.
    """
    slug_field = 'slug'
    slugify_field = 'title'

    def save(self, force_insert=False, force_update=False,
             using=None, update_fields=None):
        if getattr(self, self.slug_field):
            # serializer will set created slug to '' instead of None.
            return super(SlugifyFieldMixin, self).save(
                force_insert=force_insert, force_update=force_update,
                using=using, update_fields=update_fields)
        max_length = self._meta.get_field(self.slug_field).max_length
        slugified_value = getattr(self, self.slugify_field)
        slug_base = slugify(slugified_value)
        if len(slug_base) > max_length:
            slug_base = slug_base[:max_length]
        setattr(self, self.slug_field, slug_base)
        for _ in range(1, 10):
            try:
                with transaction.atomic():
                    return super(SlugifyFieldMixin, self).save(
                        force_insert=force_insert, force_update=force_update,
                        using=using, update_fields=update_fields)
            except IntegrityError as err:
                if 'uniq' not in str(err).lower():
                    raise
                suffix = '-%s' % "".join([random.choice("abcdef0123456789")
                    for _ in range(7)])
                if len(slug_base) + len(suffix) > max_length:
                    setattr(self, self.slug_field,
                        slug_base[:(max_length - len(suffix))] + suffix)
                else:
                    setattr(self, self.slug_field, slug_base + suffix)
        raise ValidationError({'detail':
            "Unable to create a unique URL slug from %s '%s'" % (
                self.slugify_field, slugified_value)})


def as_timestamp(dtime_at=None):
    if not dtime_at:
        dtime_at = datetime_or_now()
    return int((
        dtime_at - datetime.datetime(1970, 1, 1,
            tzinfo=timezone_or_utc())).total_seconds())


def datetime_or_now(dtime_at=None, tzinfo=None):
    tzinfo = timezone_or_utc(tzinfo)
    as_datetime = dtime_at
    if isinstance(dtime_at, six.string_types):
        as_datetime = parse_datetime(dtime_at)
        if not as_datetime:
            as_date = parse_date(dtime_at)
            if as_date:
                as_datetime = datetime.datetime.combine(
                    as_date, datetime.time.min)
    elif (not isinstance(dtime_at, datetime.datetime) and
          isinstance(dtime_at, datetime.date)):
        as_datetime = datetime.datetime.combine(
            dtime_at, datetime.time.min)
    if not as_datetime:
        as_datetime = datetime.datetime.now(tz=tzinfo)
    if (as_datetime.tzinfo is None or
        as_datetime.tzinfo.utcoffset(as_datetime) is None):
        as_datetime = as_datetime.replace(tzinfo=tzinfo)
    return as_datetime


def period_less_than(left, right, period_type=YEARLY):
    if period_type == MONTHLY:
        return left.year < right.year or (
            left.year == right.year and left.month < right.month)
    return left.year < right.year


def construct_monthly_periods(first_date, last_date, years=0, tzone=None):
    at_time = first_date
    tzinfo = timezone_or_utc(tzone)
    months_ends_at = []
    while at_time < last_date:
        # we are interested in 00:00 local time, if we don't have
        # local time zone, fall back to 00:00 utc time
        # in case we have local timezone, replace utc with it
        ends_at = datetime.datetime(
            year=at_time.year, month=at_time.month, day=1, tzinfo=tzinfo)
        years_shifted = ends_at + relativedelta(years=years)
        months_ends_at += [years_shifted]
        at_time += relativedelta(months=1)
    return months_ends_at


def _construct_weekly_period(at_time, years=0, tzone=None):
    # discarding time, keeping utc tzinfo (00:00:00 utc)
    today = at_time.replace(hour=0, minute=0, second=0, microsecond=0)
    tzinfo = timezone_or_utc(tzone)
    # we are interested in 00:00 local time, if we don't have
    # local time zone, fall back to 00:00 utc time
    # in case we have local timezone, replace utc with it
    today = today.replace(tzinfo=tzinfo)
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
    tzinfo = timezone_or_utc(tzone)
    period_ends_at = []
    while at_time <= last_date:
        # we are interested in 00:00 local time, if we don't have
        # local time zone, fall back to 00:00 utc time
        # in case we have local timezone, replace utc with it
        ends_at = datetime.datetime(year=at_time.year, month=1, day=1,
            tzinfo=tzinfo)
        period_ends_at += [ends_at]
        at_time += relativedelta(years=1)
    return period_ends_at


def construct_periods(first_date, last_date, period_type=None, tzone=None):
    if period_type == YEARLY:
        return construct_yearly_periods(first_date, last_date, tzone=tzone)
    if period_type == MONTHLY:
        return construct_monthly_periods(first_date, last_date, tzone=tzone)
    if period_type == WEEKLY:
        return construct_weekly_periods(first_date, last_date, tzone=tzone)
    return [first_date, last_date]


def convert_dates_to_utc(dates):
    return [date.astimezone(timezone_or_utc()) for date in dates]


def extra_as_internal(obj):
    try:
        if not obj.extra:
            return {}
        if isinstance(obj.extra, six.string_types):
            try:
                obj.extra = json.loads(obj.extra)
            except (TypeError, ValueError):
                pass
        return obj.extra
    except AttributeError:
        pass
    try:
        extra = obj.get('extra', {})
        if not extra:
            return {}
        if isinstance(extra, six.string_types):
            try:
                obj.update({'extra': json.loads(extra)})
            except (TypeError, ValueError):
                pass
        return obj.get('extra', {})
    except AttributeError:
        pass
    return {}


def get_extra(obj, attr_name, default=None):
    if not hasattr(obj, 'extra'):
        return default
    if isinstance(obj.extra, six.string_types):
        try:
            obj.extra = json.loads(obj.extra)
        except (TypeError, ValueError):
            return default
    return obj.extra.get(attr_name, default) if obj.extra else default


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
