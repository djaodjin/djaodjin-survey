DjaoDjin survey
================

The Django app implements a simple survey app. Surveys can also be run
in quizz mode.


Five minutes evaluation
=======================

The source code is bundled with a sample django project.

    $ virtualenv *virtual_env_dir*
    $ cd *virtual_env_dir*
    $ source bin/activate
    $ pip install -r testsite/requirements.txt
    $ make initdb
    $ python manage.py runserver

    # Visit url at http://localhost:8000/
    # You can use username: donny, password: yoyo to test the manager options.

Releases
========

0.4.0

  * Makes djaodjin-resources-vue a UMB module
  * Filters portfolios
  * Adds get_latest_completed_by_accounts

[previous release notes](changelog)


Models have been completely re-designed between version 0.1.7 and 0.2.0
