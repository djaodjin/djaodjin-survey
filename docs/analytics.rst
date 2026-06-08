Analytics
=========

.. image:: survey-benchmarks.*

The core of algorithm to select and aggregate answers based on questions,
accounts and dates is implemented in:

.. automethod:: survey.api.matrix.BenchmarkMixin.get_questions_by_key

Overriding `get_accounts` is the main customization point of the algorithm.
All benchmarks API views (see `Guide to Benchmarks API`_) are implemented
by deriving from `BenchmarkAPIView` combined with one of the following mixins:

.. automethod:: survey.api.matrix.BenchmarkMixin.get_accounts

.. automethod:: survey.api.matrix.AccessiblesAccountsMixin.get_accounts

.. automethod:: survey.api.matrix.EngagedAccountsMixin.get_accounts

.. automethod:: survey.api.matrix.EditableFilterAccountsMixin.get_accounts

Aggregates and answers (when nomminative profiles are shown) are retrieved
through `survey.queries.sql_benchmarks_counts` and
`survey.queries.sql_benchmarks_samples` respectively.


.. _Guide to Benchmarks API: https://www.djaodjin.com/docs/guides/djaopsp/compare/
