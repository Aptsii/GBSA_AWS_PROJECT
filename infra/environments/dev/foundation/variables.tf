variable "environment" {
  description = "Deployment environment for the isolated development tenant foundation."
  type        = string
  default     = "dev"

  validation {
    condition     = var.environment == "dev"
    error_message = "This root accepts only the dev environment."
  }
}

variable "company_tenant_identity" {
  description = "Opaque seed identifiers for the development company tenant and initial administrator."
  type = object({
    company_id       = string
    company_user_id  = string
    identity_subject = string
  })
  sensitive = true

  validation {
    condition = alltrue([
      can(regex("^[0-9a-fA-F-]{36}$", var.company_tenant_identity.company_id)),
      can(regex("^[0-9a-fA-F-]{36}$", var.company_tenant_identity.company_user_id)),
      length(trimspace(var.company_tenant_identity.identity_subject)) > 0,
    ])
    error_message = "Company and user IDs must be opaque UUIDs and the identity subject must be present."
  }
}

variable "applicant_retention_days" {
  description = "Default development retention snapshot applied when applicant consent is recorded."
  type        = number
  default     = 180

  validation {
    condition     = var.applicant_retention_days >= 1 && var.applicant_retention_days <= 3650
    error_message = "Applicant retention must be between 1 and 3650 days."
  }
}

variable "invitation_ttl_hours" {
  description = "Maximum lifetime of a development applicant invitation."
  type        = number
  default     = 168

  validation {
    condition     = var.invitation_ttl_hours >= 1 && var.invitation_ttl_hours <= 720
    error_message = "Invitation lifetime must be between 1 and 720 hours."
  }
}

