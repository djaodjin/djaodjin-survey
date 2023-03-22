Integration within a multi-app project
======================================

There are two mechanisms to help integrating djaodjin-survey within a project
composed of multiple Django applications.

- Overriding models
- Replacing default functions

For example, `djaopsp`_ is a project which ties djaodjin-survey with other
Django applications into a boilerplate Practices Sharing Platform WebApp.


Overriding models
-----------------

Question, content, account and user models can be overriden.

To replace the question model, define ``SURVEY['QUESTION_MODEL']`` and
``SURVEY['QUESTION_SERIALIZER']`` to serialize such model in API calls.

To replace the content model, define ``SURVEY['CONTENT_MODEL']``.

Accounts/profiles default to `django.contrib.auth.User`. It is often useful
for composition of Django apps to replace the account model.
This is possible by defining the settings ``SURVEY['ACCOUNT_MODEL']``.
When the ``ACCOUNT_MODEL`` has been overridden, ``SURVEY['ACCOUNT_SERIALIZER']``
should be defined and implement an account model serialization as used
in API calls.

It is often useful for composition of Django apps to override the user model.
This is possible by defining the settings ``SURVEY['AUTH_USER_MODEL']``.
When the ``AUTH_USER_MODEL`` (as returned by ``get_user_model``) has been
overridden, both ``SURVEY['USER_SERIALIZER']`` and
``SURVEY['USER_DETAIL_SERIALIZER']`` should be defined and implement a user
model serialization as used in API calls for the summary and detailed contact
information respectively.


Replacing default functions
---------------------------

.. autodata:: survey.settings.ACCESSIBLE_ACCOUNTS_CALLABLE

.. _djaopsp: https://github.com/djaodjin/djaopsp
