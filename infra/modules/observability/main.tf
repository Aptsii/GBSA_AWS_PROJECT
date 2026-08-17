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

variable "account_id" {
  type = string
}

variable "monthly_budget_usd" {
  type    = number
  default = 500
}

variable "alarm_email" {
  type    = string
  default = ""
}

variable "kms_key_arn" {
  type = string
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

resource "aws_cloudwatch_log_group" "application" {
  for_each = toset(["api", "worker", "audit"])

  name              = "/iep/${var.environment}/${each.value}"
  retention_in_days = var.environment == "prod" ? 365 : 30
  kms_key_id        = var.kms_key_arn
  tags              = local.common_tags
}

resource "aws_xray_sampling_rule" "interview" {
  rule_name      = "${var.name_prefix}-interview"
  priority       = 1000
  version        = 1
  reservoir_size = 1
  fixed_rate     = 0.1
  url_path       = "*"
  host           = "*"
  http_method    = "*"
  service_type   = "*"
  service_name   = "interview-evidence-*"
  resource_arn   = "*"

  attributes = {
    environment = var.environment
  }
}

resource "aws_sns_topic" "alarms" {
  name              = "${var.name_prefix}-alarms"
  kms_master_key_id = var.kms_key_arn
  tags              = local.common_tags
}

resource "aws_sns_topic_subscription" "email" {
  count = var.alarm_email == "" ? 0 : 1

  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

resource "aws_cloudwatch_metric_alarm" "queue_age" {
  alarm_name          = "${var.name_prefix}-queue-age"
  alarm_description   = "Background queue age exceeds the interview recovery objective"
  namespace           = "InterviewEvidence"
  metric_name         = "QueueAgeSeconds"
  unit                = "Seconds"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 5
  threshold           = 300
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  ok_actions          = [aws_sns_topic.alarms.arn]
  tags                = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "deletion_residue" {
  alarm_name          = "${var.name_prefix}-deletion-residue"
  alarm_description   = "Deletion targets remain after the verification window"
  namespace           = "InterviewEvidence"
  metric_name         = "DeletionResidueCount"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  tags                = local.common_tags
}

resource "aws_s3_bucket" "audit" {
  bucket        = "${var.name_prefix}-audit"
  force_destroy = false
  tags          = merge(local.common_tags, { DataClassification = "Restricted" })
}

resource "aws_s3_bucket_public_access_block" "audit" {
  bucket                  = aws_s3_bucket.audit.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "audit" {
  bucket = aws_s3_bucket.audit.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "audit" {
  bucket = aws_s3_bucket.audit.id
  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = var.kms_key_arn
      sse_algorithm     = "aws:kms"
    }
  }
}

data "aws_iam_policy_document" "audit" {
  statement {
    sid       = "AWSCloudTrailAclCheck"
    actions   = ["s3:GetBucketAcl"]
    resources = [aws_s3_bucket.audit.arn]
    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }
  }

  statement {
    sid       = "AWSCloudTrailWrite"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.audit.arn}/AWSLogs/${var.account_id}/*"]
    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "s3:x-amz-acl"
      values   = ["bucket-owner-full-control"]
    }
  }
}

resource "aws_s3_bucket_policy" "audit" {
  bucket = aws_s3_bucket.audit.id
  policy = data.aws_iam_policy_document.audit.json
}

resource "aws_cloudtrail" "audit" {
  name                          = "${var.name_prefix}-audit"
  s3_bucket_name                = aws_s3_bucket.audit.id
  kms_key_id                    = var.kms_key_arn
  include_global_service_events = true
  is_multi_region_trail         = true
  enable_log_file_validation    = true
  tags                          = local.common_tags

  depends_on = [aws_s3_bucket_policy.audit]
}

resource "aws_budgets_budget" "monthly" {
  name         = "${var.name_prefix}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "TagKeyValue"
    values = ["user:Environment$${var.environment}"]
  }

  dynamic "notification" {
    for_each = var.alarm_email == "" ? [] : [var.alarm_email]
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = 80
      threshold_type             = "PERCENTAGE"
      notification_type          = "FORECASTED"
      subscriber_email_addresses = [notification.value]
    }
  }

  tags = local.common_tags
}

output "alarm_topic_arn" {
  value = aws_sns_topic.alarms.arn
}

output "audit_trail_arn" {
  value = aws_cloudtrail.audit.arn
}

output "log_group_names" {
  value = { for key, group in aws_cloudwatch_log_group.application : key => group.name }
}
