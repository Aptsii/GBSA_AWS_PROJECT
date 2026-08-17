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

variable "kms_key_arn" {
  type = string
}

variable "queue_visibility_timeout_seconds" {
  type    = number
  default = 300
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

resource "aws_sqs_queue" "dead_letter" {
  name                      = "${var.name_prefix}-jobs-dlq"
  message_retention_seconds = 1209600
  kms_master_key_id         = var.kms_key_arn
  tags                      = local.common_tags
}

resource "aws_sqs_queue" "jobs" {
  name                       = "${var.name_prefix}-jobs"
  visibility_timeout_seconds = var.queue_visibility_timeout_seconds
  message_retention_seconds  = 345600
  receive_wait_time_seconds  = 20
  kms_master_key_id          = var.kms_key_arn
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dead_letter.arn
    maxReceiveCount     = 5
  })
  tags = local.common_tags
}

resource "aws_cloudwatch_event_bus" "domain" {
  name = "${var.name_prefix}-domain"
  tags = local.common_tags
}

resource "aws_cloudwatch_event_rule" "all_domain_events" {
  name           = "${var.name_prefix}-domain-events"
  event_bus_name = aws_cloudwatch_event_bus.domain.name
  event_pattern = jsonencode({
    source = [{ prefix = "interview-evidence." }]
  })
  tags = local.common_tags
}

resource "aws_cloudwatch_event_target" "jobs" {
  rule           = aws_cloudwatch_event_rule.all_domain_events.name
  event_bus_name = aws_cloudwatch_event_bus.domain.name
  target_id      = "jobs"
  arn            = aws_sqs_queue.jobs.arn

  dead_letter_config {
    arn = aws_sqs_queue.dead_letter.arn
  }
}

data "aws_iam_policy_document" "queue" {
  statement {
    sid     = "AllowEventBridgeDelivery"
    actions = ["sqs:SendMessage"]
    resources = [
      aws_sqs_queue.jobs.arn,
    ]
    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [aws_cloudwatch_event_rule.all_domain_events.arn]
    }
  }
}

resource "aws_sqs_queue_policy" "jobs" {
  queue_url = aws_sqs_queue.jobs.id
  policy    = data.aws_iam_policy_document.queue.json
}

data "aws_iam_policy_document" "step_functions_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "step_functions" {
  name               = "${var.name_prefix}-step-functions"
  assume_role_policy = data.aws_iam_policy_document.step_functions_assume.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "step_functions" {
  statement {
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.jobs.arn]
  }
}

resource "aws_iam_role_policy" "step_functions" {
  name   = "queue-dispatch"
  role   = aws_iam_role.step_functions.id
  policy = data.aws_iam_policy_document.step_functions.json
}

resource "aws_sfn_state_machine" "orchestration" {
  name     = "${var.name_prefix}-orchestration"
  role_arn = aws_iam_role.step_functions.arn
  type     = "STANDARD"

  definition = jsonencode({
    Comment = "Versioned interview evidence background orchestration"
    StartAt = "Dispatch"
    States = {
      Dispatch = {
        Type     = "Task"
        Resource = "arn:aws:states:::sqs:sendMessage"
        Parameters = {
          QueueUrl        = aws_sqs_queue.jobs.id
          "MessageBody.$" = "$"
        }
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 2
          MaxAttempts     = 4
          BackoffRate     = 2
        }]
        End = true
      }
    }
  })

  tags = local.common_tags
}

output "job_queue_url" {
  value = aws_sqs_queue.jobs.id
}

output "job_queue_arn" {
  value = aws_sqs_queue.jobs.arn
}

output "dead_letter_queue_arn" {
  value = aws_sqs_queue.dead_letter.arn
}

output "event_bus_arn" {
  value = aws_cloudwatch_event_bus.domain.arn
}

output "state_machine_arn" {
  value = aws_sfn_state_machine.orchestration.arn
}
