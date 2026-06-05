output "agent_role" {
  value       = postgresql_role.agent_ro.name
  description = "The provisioned read-only role name."
}

output "agent_dsn" {
  value       = "postgresql://${var.agent_role}:****@${var.host}:${var.port}/${var.database}"
  description = "Shape of the DSN the agent uses (password masked)."
}
