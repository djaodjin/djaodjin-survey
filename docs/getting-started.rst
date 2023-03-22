Getting Started
===============

Installation and configuration
------------------------------

First download and install the latest version of djaodjin-survey into your
Python virtual environment.

.. code-block:: shell

    $ pip install djaodjin-survey


Edit your project urls.py to add the djaojdin-survey urls

.. code-block:: python

   urlpatterns += [
       url(r'^', include('survey.urls')),
   ]


Edit your project settings.py to add survey into the ``INSTALLED_APPS``
and a SURVEY configuration block

.. code-block:: python

    INSTALLED_APPS = (
        ...
        'survey'
    )

    SURVEY = {
        'ACCOUNT_MODEL': 'django.contrib.auth.models.User'
    }

In most cases, you will want to override the account model (
see :doc:`Integration within a multi-app project <extensions>`).

The latest versions of django-restframework implement paginators disconnected
from parameters in  views (i.e. no more paginate_by). You will thus need
to define ``PAGE_SIZE`` in your settings.py

.. code-block:: python

    REST_FRAMEWORK = {
        'PAGE_SIZE': 25,
        'DEFAULT_PAGINATION_CLASS':
            'rest_framework.pagination.PageNumberPagination',
    }
