variable "host" {
  type    = string
  default = "localhost"
}

variable "port" {
  type    = number
  default = 5432
}

variable "database" {
  type    = string
  default = "warehouse"
}

variable "superuser" {
  type        = string
  default     = "postgres"
  description = "Build/admin superuser used by Terraform to create the role. NOT used by the agent."
}

variable "superuser_password" {
  type      = string
  sensitive = true
}

variable "agent_role" {
  type        = string
  default     = "agent_ro"
  description = "The read-only role the agent connects as."
}

variable "agent_password" {
  type      = string
  sensitive = true
}
