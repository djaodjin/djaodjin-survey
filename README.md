DjaoDjin survey
================

The Django app implements a simple survey app.

Full documentation for the project is available at
[Read-the-Docs](http://djaodjin-survey.readthedocs.org/)


Five minutes evaluation
=======================

The source code is bundled with a sample django project.

    $ python3 -m venv .venv
    $ source .venv/bin/activate
    $ pip install -r testsite/requirements.txt
    $ python manage.py migrate --run-syncdb --noinput
    $ python manage.py loaddata testsite/fixtures/default-db.json

    $ python manage.py runserver

    # Visit url at http://localhost:8000/
    # You can use username: donny, password: yoyo to test the manager options.

Releases
========

Tested with

- **Python:** 3.7, **Django:** 3.2 ([LTS](https://www.djangoproject.com/download/))
- **Python:** 3.10, **Django:** 4.2 (latest)
- **Python:** 2.7, **Django:** 1.11 (legacy) - use testsite/requirements-legacy.txt

0.9.9

  * defaults portfolio request to not expire (definitely not expire at creation)
  * fixes logic to decide when to expect an update to an assessment

[previous release notes](changelog)


Models have been completely re-designed between version 0.1.7 and 0.2.0
