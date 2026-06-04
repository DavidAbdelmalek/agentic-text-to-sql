# Terraform (Phase 7)

Provisions the local/dev stack and documents the **Snowflake read-only variant** behind
the same DB interface the agent codes against.

- `local/` — provider config for the dockerized Postgres dev environment.
- `snowflake/` — a documented read-only role variant: a Snowflake role with `USAGE` on
  warehouse/db/schema and `SELECT` on the views the agent reads, mirroring the Postgres
  `agent_ro` model (no DDL/DML grants). Shows the safety model ports cleanly to a cloud
  warehouse — the headline data-engineering talking point.

Populated in Phase 7.
