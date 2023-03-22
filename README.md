DjaoDjin survey
================

The Django app implements a simple survey app.

Full documentation for the project is available at
[Read-the-Docs](http://djaodjin-survey.readthedocs.org/)


Five minutes evaluation
=======================

The source code is bundled with a sample django project.

    $ virtualenv *virtual_env_dir*
    $ cd *virtual_env_dir*
    $ source bin/activate
    $ pip install -r testsite/requirements.txt
    $ python manage.py migrate --run-syncdb --noinput
    $ python manage.py loaddata testsite/fixtures/default-db.json

    $ python manage.py runserver

    # Visit url at http://localhost:8000/
    # You can use username: donny, password: yoyo to test the manager options.

Releases
========

Tested with

- **Python:** 3.7, **Django:** 3.2 ([LTS](https://www.djangoproject.com/download/)), **Django Rest Framework:** 3.12
- **Python:** 3.10, **Django:** 4.1 (latest), **Django Rest Framework:** 3.12
- **Python:** 2.7, **Django:** 1.11 (legacy), **Django Rest Framework:** 3.9.4

0.9.0

  * adds compare API
  * adds ACCESSIBLE_ACCOUNTS_CALLABLE
  * uses comma to separate multiple terms in search
  * moves update_context_urls from survey.utils to survey.helpers
  * defines URL_PATH_SEP and DB_PATH_SEP in settings.py instead of mixins
  * moves get_collected_by from survey.queries to survey.models
  * replaces queries.get_frozen_answers by Answer.objects.get_frozen_answers
  * replaces queries.get_completed_assessments_at_by by Sample.objects.get_completed_assessments_at_by

[previous release notes](changelog)


Models have been completely re-designed between version 0.1.7 and 0.2.0
