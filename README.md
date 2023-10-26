DjaoDjin survey
================

[![Documentation Status](https://readthedocs.org/projects/djaodjin-survey/badge/?version=latest)](https://djaodjin-survey.readthedocs.io/en/latest/?badge=latest)

[![PyPI version](https://badge.fury.io/py/djaodjin-survey.svg)](https://badge.fury.io/py/djaodjin-survey)


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

0.9.14

  * fixes first answer saved when multiple items passed to API

[previous release notes](changelog)


Models have been completely re-designed between version 0.1.7 and 0.2.0
