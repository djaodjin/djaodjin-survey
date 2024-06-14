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
The expire_optins command is intended to be run as part of an automated script
run at least once a day. It will update PortfolioDoubleOptin.state for which
the expiration date (`ends_at`) is passed.

**Example cron setup**:

.. code-block:: bash

    $ cat /etc/cron.daily/expire_optins
    #!/bin/sh

    cd /var/*mysite* && python manage.py expire_optins
"""

import datetime, logging

from dateutil.relativedelta import relativedelta
from django.core.management.base import BaseCommand

from ...models import PortfolioDoubleOptIn
from ...helpers import datetime_or_now

LOGGER = logging.getLogger(__name__)


class Command(BaseCommand):
    help = """Expire grants/requests"""

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
            dest='dry_run', default=False,
            help='Do not commit updates')
        parser.add_argument('--at-time', action='store',
            dest='at_time', default=None,
            help='Specifies the time at which the command runs')

    def handle(self, *args, **options):
        #pylint:disable=broad-except
        end_period = datetime_or_now(options['at_time'])
        start_time = datetime.datetime.utcnow()
        dry_run = options['dry_run']
        if dry_run:
            LOGGER.warning("dry_run: no changes will be committed.")

        try:
            self.expire_optins(end_period, dry_run=dry_run)
        except Exception as err:
            LOGGER.exception("expire_optins: %s", err)

        end_time = datetime.datetime.utcnow()
        delta = relativedelta(end_time, start_time)
        self.stderr.write("completed in %d hours, %d minutes, %d.%d seconds\n"
            % (delta.hours, delta.minutes, delta.seconds, delta.microseconds))

    def expire_optins(self, end_period, dry_run=False):
        for optin in PortfolioDoubleOptIn.objects.filter(
                ends_at__gte=end_period,
                state__in=[
                    PortfolioDoubleOptIn.OPTIN_GRANT_INITIATED,
                    PortfolioDoubleOptIn.OPTIN_REQUEST_INITIATED
                ]):
            if optin.state == PortfolioDoubleOptIn.OPTIN_GRANT_INITIATED:
                optin.state = PortfolioDoubleOptIn.OPTIN_GRANT_EXPIRED
            elif optin.state == PortfolioDoubleOptIn.OPTIN_REQUEST_INITIATED:
                optin.state = PortfolioDoubleOptIn.OPTIN_REQUEST_EXPIRED
            if not dry_run:
                optin.save()
