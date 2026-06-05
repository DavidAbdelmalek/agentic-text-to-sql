variable "organization_name" {
  type = string
}

variable "account_name" {
  type = string
}

variable "admin_user" {
  type        = string
  description = "Admin user Terraform authenticates as (SECURITYADMIN). NOT the agent."
}

variable "admin_password" {
  type      = string
  sensitive = true
}

variable "warehouse" {
  type    = string
  default = "WH_TTSQL"
}

variable "database" {
  type    = string
  default = "WAREHOUSE"
}

variable "schema" {
  type        = string
  default     = "PUBLIC"
  description = "Schema holding the dbt marts the agent reads."
}

variable "agent_role" {
  type    = string
  default = "AGENT_RO"
}

variable "agent_user" {
  type        = string
  description = "Existing Snowflake service user the agent logs in as; gets AGENT_RO."
}
