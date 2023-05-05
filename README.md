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

0.9.7

  * prevents extra data to leak through API under unexpected conditions
  * uses prefix to filter questions in benchmarks API

[previous release notes](changelog)


Models have been completely re-designed between version 0.1.7 and 0.2.0
