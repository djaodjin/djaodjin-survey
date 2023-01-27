Encoding answers in the database
================================

Quantitative measurements
-------------------------

Quantitative (numeric) measurements are recorded through the
`Records quantitative measurements API`_.

When `baseline_at` is specified, the measurement refers to
a relative value since `baseline_at`. When `baseline_at` is not
specified, the intent is to record an absolute measurement at time
`created_at`.


Absolute measurements database encoding
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Absolute measurements, for example weight of a team player at a certain date,
are recorded as an `Answer` whose `created_at` field is the date of the
measurement and a `Sample` whose `created_at` field is the date the record
was created in the database.

    .. code-block:: http

        POST /api/bobcats/filters/accounts/players/values HTTP/1.1

    .. code-block:: json

        {
              "created_at":"2023-01-01",
              "items":[{
                "slug":"steve",
                "measured":"65",
                "unit":"kg"
              }]
        }

TABLE survey_answer:

+----+------------+-------------+---------------+--------+---------------+
| id | created_at | measured    | unit          | sample | question      |
+====+============+=============+===============+========+===============+
| 1  | 2022-01-01 |          65 | kg            |     1  | weight        |
+----+------------+-------------+---------------+--------+---------------+

TABLE survey_sample:

+----+------------+--------------+----------------+-----------+
| id | created_at | account      | campaign       | is_frozen |
+====+============+==============+================+===========+
|  1 | 2023-01-27 | steve        | null           | true      |
+----+------------+--------------+----------------+-----------+


Relative measurements database encoding
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Relative measurements, like the amount of CO2 emissions for a factory
during a time period are recorded as relative measurements between
a start date (`baseline_at`) and an end date.

When no previous baseline exists (typically the first time a relative
measurement is encoded), the API records a dummy record with value zero
to encode the date at which the recording period started (i.e. baseline).

    .. code-block:: http

        POST /api/supplier-1/filters/accounts/ghg-emissions/values HTTP/1.1

    .. code-block:: json

        {
              "baseline_at":"2022-01-01",
              "created_at":"2023-01-01",
              "items":[{
                "slug":"main-factory",
                "measured":"12",
                "unit":"tons"
              }]
        }

TABLE survey_answer:

+----+------------+-------------+---------------+--------+---------------+
| id | created_at | measured    | unit          | sample | question      |
+====+============+=============+===============+========+===============+
| 1  | 2022-01-01 |           0 | tons          |     1  | ghg-emissions |
+----+------------+-------------+---------------+--------+---------------+
| 2  | 2023-01-01 |          12 | tons          |     2  | ghg-emissions |
+----+------------+-------------+---------------+--------+---------------+


TABLE survey_sample:

+----+------------+--------------+----------------+-----------+
| id | created_at | account      | campaign       | is_frozen |
+====+============+==============+================+===========+
|  1 | 2023-01-27 | main-factory | null           | true      |
+----+------------+--------------+----------------+-----------+
|  2 | 2023-01-27 | main-factory | null           | true      |
+----+------------+--------------+----------------+-----------+


When the specified baseline already has measurements recorded at that date,
there is no gap in measurements, and thus the API doesn't create an additional
dummy record to encode the baseline date.

        .. code-block:: http

             POST /api/supplier-1/filters/accounts/ghg-emissions/values HTTP/1.1

        .. code-block:: json

            {
              "baseline_at":"2023-01-01",
              "created_at":"2024-01-01",
              "items":[{
                "slug":"main-factory",
                "measured":"8",
                "unit":"tons"
              }]
            }

TABLE survey_answer:

+----+------------+-------------+---------------+--------+---------------+
| id | created_at | measured    | unit          | sample | question      |
+====+============+=============+===============+========+===============+
| 1  | 2022-01-01 |        0    | tons          |     1  | ghg-emissions |
+----+------------+-------------+---------------+--------+---------------+
| 2  | 2023-01-01 |       12    | tons          |     2  | ghg-emissions |
+----+------------+-------------+---------------+--------+---------------+
| 3  | 2024-01-01 |        8    | tons          |     3  | ghg-emissions |
+----+------------+-------------+---------------+--------+---------------+


TABLE survey_sample:

+----+------------+--------------+----------------+-----------+
| id | created_at | account      | campaign       | is_frozen |
+====+============+==============+================+===========+
|  1 | 2023-01-27 | main-factory | null           | true      |
+----+------------+--------------+----------------+-----------+
|  2 | 2023-01-27 | main-factory | null           | true      |
+----+------------+--------------+----------------+-----------+
|  3 | 2024-01-12 | main-factory | null           | true      |
+----+------------+--------------+----------------+-----------+


Qualitivative assessments
-------------------------



Reporting metrics over a time period
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

In the database, an answer about GHG Emissions of "10 Tons of CO2e in 2021"
is encoded as follow in the database:

TABLE survey_answer:

+----+------------+-------------+---------------+--------+---------------+
| id | created_at |  measured   | unit          | sample | question      |
+====+============+=============+===============+========+===============+
| 0  | 2023-01-27 |         10  | tons-period   |      1 | ghg-emissions |
+----+------------+-------------+---------------+--------+---------------+
| 1  | 2023-01-27 |  2021-01-01 | starts-at     |      1 | ghg-emissions |
+----+------------+-------------+---------------+--------+---------------+
| 2  | 2023-01-27 |  2021-12-31 | ends-at       |      1 | ghg-emissions |
+----+------------+-------------+---------------+--------+---------------+

TABLE survey_sample:

+----+------------+--------------+----------------+
| id | created_at | account      | campaign       |
+====+============+==============+================+
|  1 | 2023-01-27 | supplier 1   | sustainability |
+----+------------+--------------+----------------+


.. _Records quantitative measurements API: https://www.djaodjin.com/docs/reference/djaopsp/latest/api/#createAccountsFilterValues
