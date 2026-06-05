# Provisions the read-only agent role + grants on the local/dev Postgres, declaratively.
# This is the production-grade alternative to docker/initdb/02-create-readonly-role.sh:
# the security boundary (a role that can only SELECT/EXPLAIN) expressed as code, reviewable
# and reproducible. The same shape ports to Snowflake (see ../snowflake).
#
# Apply against a Postgres that does NOT already have the role (e.g. a fresh volume with the
# init script removed), or import the existing role. The docker init stays the zero-config
# default for `make up`; this module is the IaC demonstration.

terraform {
  required_version = ">= 1.5"
  required_providers {
    postgresql = {
      source  = "cyrilgdn/postgresql"
      version = "~> 1.22"
    }
  }
}

provider "postgresql" {
  host            = var.host
  port            = var.port
  database        = var.database
  username        = var.superuser
  password        = var.superuser_password
  sslmode         = "disable" # local dev only; use "require" for real environments
  connect_timeout = 15
}

# LOGIN role: no superuser, cannot create databases or roles. The hard read-only boundary.
resource "postgresql_role" "agent_ro" {
  name            = var.agent_role
  login           = true
  password        = var.agent_password
  superuser       = false
  create_database = false
  create_role     = false
  inherit         = false
}

resource "postgresql_grant" "connect" {
  database    = var.database
  role        = postgresql_role.agent_ro.name
  object_type = "database"
  privileges  = ["CONNECT"]
}

resource "postgresql_grant" "schema_usage" {
  database    = var.database
  schema      = "public"
  role        = postgresql_role.agent_ro.name
  object_type = "schema"
  privileges  = ["USAGE"]
}

# SELECT on existing tables/views in public...
resource "postgresql_grant" "select_tables" {
  database    = var.database
  schema      = "public"
  role        = postgresql_role.agent_ro.name
  object_type = "table"
  privileges  = ["SELECT"]
}

# ...and on tables created LATER by dbt, via default privileges (no re-grant step).
resource "postgresql_default_privileges" "future_select" {
  database    = var.database
  schema      = "public"
  role        = postgresql_role.agent_ro.name
  owner       = var.superuser
  object_type = "table"
  privileges  = ["SELECT"]
}
