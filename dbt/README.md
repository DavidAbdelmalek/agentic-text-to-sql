# dbt project (Phase 2)

Kimball star schema modeled + tested with **dbt-postgres**. Built here so the repo
demonstrates dimensional-modeling rigor, not just LLM glue.

- `models/staging/` — clean the Faker seed.
- `models/marts/` — `fct_sales`, `dim_customer`, `dim_product`, `dim_date`, `dim_region`.
- `tests/` — `unique`, `not_null`, `relationships` (FK integrity), plus a few custom
  data tests. `dbt build` runs models + tests in CI on a Postgres service.

**Snowflake variant:** the same models compile under `dbt-snowflake` by swapping the
profile/target; dialect specifics are noted in model comments (see DECISIONS.md).

Populated in Phase 2.
