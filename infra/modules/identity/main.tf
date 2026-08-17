terraform {
  required_version = ">= 1.10.0, < 2.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.80.0, < 7.0.0"
    }
  }
}

variable "name_prefix" {
  type = string
}

variable "environment" {
  type = string
}

variable "ses_identity" {
  type    = string
  default = ""
}

variable "document_bucket_arns" {
  type    = list(string)
  default = []
}

variable "queue_arns" {
  type    = list(string)
  default = []
}

variable "kms_key_arns" {
  type    = list(string)
  default = []
}

variable "secret_arns" {
  type    = list(string)
  default = []
}

variable "tags" {
  type    = map(string)
  default = {}
}

locals {
  common_tags = merge(var.tags, {
    Project            = "InterviewEvidencePlatform"
    Environment        = var.environment
    ManagedBy          = "Terraform"
    DataClassification = "Confidential"
    CostCenter         = "InterviewPlatform"
  })
}

resource "aws_cognito_user_pool" "company" {
  name                     = "${var.name_prefix}-company"
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  mfa_configuration        = "OPTIONAL"

  software_token_mfa_configuration {
    enabled = true
  }

  password_policy {
    minimum_length                   = 14
    require_lowercase                = true
    require_numbers                  = true
    require_symbols                  = true
    require_uppercase                = true
    temporary_password_validity_days = 1
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  user_attribute_update_settings {
    attributes_require_verification_before_update = ["email"]
  }

  deletion_protection = var.environment == "prod" ? "ACTIVE" : "INACTIVE"
  tags                = local.common_tags
}

resource "aws_cognito_user_pool_client" "company_console" {
  name         = "${var.name_prefix}-company-console"
  user_pool_id = aws_cognito_user_pool.company.id

  generate_secret                      = false
  prevent_user_existence_errors        = "ENABLED"
  enable_token_revocation              = true
  refresh_token_validity               = 12
  access_token_validity                = 15
  id_token_validity                    = 15
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["email", "openid", "profile"]
  callback_urls                        = ["https://localhost.invalid/auth/callback"]
  logout_urls                          = ["https://localhost.invalid/logout"]
  supported_identity_providers         = ["COGNITO"]

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "hours"
  }
}

resource "aws_ses_email_identity" "sender" {
  count = var.ses_identity == "" ? 0 : 1

  email = var.ses_identity
}

data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "application" {
  for_each = toset(["api", "worker"])

  name                 = "${var.name_prefix}-${each.value}-application"
  assume_role_policy   = data.aws_iam_policy_document.ecs_assume.json
  max_session_duration = 3600
  tags                 = local.common_tags
}

data "aws_iam_policy_document" "application" {
  statement {
    sid       = "ObjectAccess"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"]
    resources = concat(var.document_bucket_arns, [for arn in var.document_bucket_arns : "${arn}/*"])
  }

  statement {
    sid       = "QueueAccess"
    actions   = ["sqs:ChangeMessageVisibility", "sqs:DeleteMessage", "sqs:GetQueueAttributes", "sqs:ReceiveMessage", "sqs:SendMessage"]
    resources = var.queue_arns
  }

  statement {
    sid       = "SecretRead"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = var.secret_arns
  }

  statement {
    sid       = "DataKeyUse"
    actions   = ["kms:Decrypt", "kms:DescribeKey", "kms:Encrypt", "kms:GenerateDataKey"]
    resources = var.kms_key_arns
  }

  statement {
    sid       = "InterviewAI"
    actions   = ["bedrock:InvokeModel", "bedrock:Retrieve", "polly:SynthesizeSpeech", "transcribe:StartTranscriptionJob", "transcribe:GetTranscriptionJob"]
    resources = ["*"]
  }

  statement {
    sid       = "InvitationEmail"
    actions   = ["ses:SendEmail", "ses:SendRawEmail"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "ses:FromAddress"
      values   = var.ses_identity == "" ? ["noreply@invalid.local"] : [var.ses_identity]
    }
  }
}

resource "aws_iam_policy" "application" {
  name   = "${var.name_prefix}-application"
  policy = data.aws_iam_policy_document.application.json
  tags   = local.common_tags
}

resource "aws_iam_role_policy_attachment" "application" {
  for_each = aws_iam_role.application

  role       = each.value.name
  policy_arn = aws_iam_policy.application.arn
}

output "company_user_pool_id" {
  value = aws_cognito_user_pool.company.id
}

output "company_user_pool_client_id" {
  value = aws_cognito_user_pool_client.company_console.id
}

output "application_role_arns" {
  value = { for key, role in aws_iam_role.application : key => role.arn }
}
