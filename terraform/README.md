# Terraform — the read-only role as code

The agent's security boundary is a database role that can only `SELECT`/`EXPLAIN`. This
directory provisions that role **declaratively**, and shows it ports from local Postgres to
Snowflake unchanged in spirit — the "this safety model works on our cloud warehouse" answer.

## `postgres/` — local/dev
The production-grade alternative to `docker/initdb/02-create-readonly-role.sh`: a
`cyrilgdn/postgresql` provider config that creates `agent_ro` (login, no superuser/createdb/
createrole), grants `CONNECT` + `USAGE` + `SELECT`, and sets **default privileges** so dbt's
future tables stay readable with no re-grant.

```bash
cd terraform/postgres
cp terraform.tfvars.example terraform.tfvars   # fill passwords
terraform init && terraform plan
terraform apply        # against a Postgres WITHOUT the role (fresh volume / init script removed)
```
The docker init script remains the zero-config default for `make up`; this module is the IaC
demonstration. (Run one or the other, not both — the role can't be created twice.)

## `snowflake/` — documented cloud variant
A `snowflake-labs/snowflake` config that mirrors the model: an `AGENT_RO` account role with
`USAGE` on warehouse/database/schema and `SELECT` on all current **and future** tables/views,
attached to the agent's service user — and **no** write/DDL grants anywhere. Snowflake rejects
writes at the engine level exactly like the Postgres role.

Not applied in CI/local (no Snowflake account); pin the provider and `terraform init` against a
real account to use it. The data layer ports alongside it: dbt swaps `dbt-postgres` →
`dbt-snowflake` (same models), and the agent's `AGENT_DATABASE_URL` becomes a Snowflake DSN
behind the same `ReadOnlyClient` interface.

## Why IaC for a role?
The read-only boundary is the system's most important control (see `docs/DECISIONS.md` D2).
Expressing it as reviewed, version-controlled, reproducible code — instead of a one-off
`GRANT` someone ran by hand — is the difference between a claim and a guarantee.
