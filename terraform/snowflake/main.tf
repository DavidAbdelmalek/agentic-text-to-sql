# Snowflake read-only role — the cloud-warehouse mirror of the Postgres agent_ro role.
# Same safety model: the agent connects as a role that can only USAGE + SELECT, never DDL/DML.
#
# This is a DOCUMENTED VARIANT: it shows the read-only boundary ports cleanly to Snowflake
# (the data-engineering talking point). It is not applied in CI/local (no Snowflake account).
# The companion data layer ports too: dbt swaps dbt-postgres -> dbt-snowflake (see ../../dbt).
#
# Resource/attribute names track snowflake-labs/snowflake ~> 0.94. Pin + `terraform init`
# against a real account before applying.

terraform {
  required_version = ">= 1.5"
  required_providers {
    snowflake = {
      source  = "snowflake-labs/snowflake"
      version = "~> 0.94"
    }
  }
}

provider "snowflake" {
  organization_name = var.organization_name
  account_name      = var.account_name
  user              = var.admin_user
  password          = var.admin_password
  role              = "SECURITYADMIN" # role admin; NOT the role the agent uses
}

# The read-only role.
resource "snowflake_account_role" "agent_ro" {
  name    = var.agent_role
  comment = "Read-only role for the text-to-SQL agent. SELECT + USAGE only."
}

# Compute: run queries, nothing else.
resource "snowflake_grant_privileges_to_account_role" "warehouse_usage" {
  account_role_name = snowflake_account_role.agent_ro.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = var.warehouse
  }
}

resource "snowflake_grant_privileges_to_account_role" "database_usage" {
  account_role_name = snowflake_account_role.agent_ro.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = var.database
  }
}

resource "snowflake_grant_privileges_to_account_role" "schema_usage" {
  account_role_name = snowflake_account_role.agent_ro.name
  privileges        = ["USAGE"]
  on_schema {
    schema_name = "\"${var.database}\".\"${var.schema}\""
  }
}

# SELECT on every current table + view in the marts schema...
resource "snowflake_grant_privileges_to_account_role" "select_all_tables" {
  account_role_name = snowflake_account_role.agent_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    all {
      object_type_plural = "TABLES"
      in_schema          = "\"${var.database}\".\"${var.schema}\""
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "select_all_views" {
  account_role_name = snowflake_account_role.agent_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    all {
      object_type_plural = "VIEWS"
      in_schema          = "\"${var.database}\".\"${var.schema}\""
    }
  }
}

# ...and on tables/views created LATER by dbt (mirrors Postgres ALTER DEFAULT PRIVILEGES).
resource "snowflake_grant_privileges_to_account_role" "select_future_tables" {
  account_role_name = snowflake_account_role.agent_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_schema          = "\"${var.database}\".\"${var.schema}\""
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "select_future_views" {
  account_role_name = snowflake_account_role.agent_ro.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_schema          = "\"${var.database}\".\"${var.schema}\""
    }
  }
}

# Attach the role to the agent's service user. NO write/DDL privileges are granted anywhere —
# Snowflake rejects writes at the engine level, exactly like the Postgres role.
resource "snowflake_grant_account_role" "to_agent_user" {
  role_name = snowflake_account_role.agent_ro.name
  user_name = var.agent_user
}
