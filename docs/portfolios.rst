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
