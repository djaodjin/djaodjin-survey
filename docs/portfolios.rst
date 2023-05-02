Manage Access Control
=====================

Answers recorded by an account might be used in anonymized aggregated
reports for other accounts, but are only individually nominatively accessible
by the recording account. That is until these answers are explicitely shared
with another account (grantee).

While ``Portfolio`` instances record answers that have been explicitely shared,
``PortfolioDoubleOptIn`` manages the double opt-in process by which an account
grants access to their answers to a grantee account.

.. autoclass:: survey.models.Portfolio

.. autoclass:: survey.models.PortfolioDoubleOptIn

.. autodata:: survey.settings.BYPASS_SAMPLE_AVAILABLE


Request to update or share a survey response
--------------------------------------------

When an account received a request to share answers to a survey, it will
first have to determine if sharing the previous answers is acceptable or
if the account should update its answers before sharing them.

To create, update or share a response is based on the dates of last frozen
sample, the latest accessible sample by the requestor and the date the request
was created.

By definition the latest accessible sample date is always older than
the latest initiated request, so it means we have 5 cases:

+------------------------------------------+-------------------------+
| Condition                                | Expected response       |
+==========================================+=========================+
| last_frozen_sample is None               | Create                  |
+------------------------------------------+-------------------------+
| last_frozen_sample is not None and       | Share                   |
| portfolio.ends_at is None                |                         |
|                                          |                         |
+------------------------------------------+-------------------------+
| last_frozen_sample is not None and       | Update                  |
| portfolio.ends_at is not None and        |                         |
| last_frozen_sample.created_at            |                         |
|   < portfolio.ends_at                    |                         |
|   < doubleoptin.created_at               |                         |
+------------------------------------------+-------------------------+
| last_frozen_sample is not None and       | Share                   |
| portfolio.ends_at is not None and        |                         |
| portfolio.ends_at                        |                         |
|   < last_frozen_sample.created_at        |                         |
|   < doubleoptin.created_at               |                         |
+------------------------------------------+-------------------------+
| last_frozen_sample is not None and       | Share                   |
| portfolio.ends_at is not None and        |                         |
| portfolio.ends_at                        |                         |
|   < doubleoptin.created_at               |                         |
|   < last_frozen_sample.created_at        |                         |
+------------------------------------------+-------------------------+
