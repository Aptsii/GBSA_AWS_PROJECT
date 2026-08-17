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

variable "private_subnet_ids" {
  type = list(string)
}

variable "database_security_group_id" {
  type = string
}

variable "database_name" {
  type    = string
  default = "interview_evidence"
}

variable "database_master_username" {
  type    = string
  default = "iep_admin"
}

variable "deletion_protection" {
  type    = bool
  default = false
}

variable "backup_retention_days" {
  type    = number
  default = 7
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
    DataClassification = "Restricted"
    CostCenter         = "InterviewPlatform"
  })

  bucket_names = {
    documents = "${var.name_prefix}-documents"
    media     = "${var.name_prefix}-media"
  }
}

resource "aws_kms_key" "data" {
  description             = "${var.name_prefix} application data"
  deletion_window_in_days = var.environment == "prod" ? 30 : 7
  enable_key_rotation     = true
  tags                    = local.common_tags

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_kms_alias" "data" {
  name          = "alias/${var.name_prefix}-data"
  target_key_id = aws_kms_key.data.key_id
}

resource "aws_s3_bucket" "data" {
  for_each = local.bucket_names

  bucket = each.value
  tags   = merge(local.common_tags, { Name = each.value })
}

resource "aws_s3_bucket_public_access_block" "data" {
  for_each = aws_s3_bucket.data

  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "data" {
  for_each = aws_s3_bucket.data

  bucket = each.value.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  for_each = aws_s3_bucket.data

  bucket = each.value.id
  rule {
    bucket_key_enabled = true
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.data.arn
      sse_algorithm     = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "data" {
  for_each = aws_s3_bucket.data

  bucket = each.value.id

  rule {
    id     = "abort-incomplete-uploads"
    status = "Enabled"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }

    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}

resource "aws_dynamodb_table" "hot_context" {
  name         = "${var.name_prefix}-hot-context"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "company_id"
  range_key    = "session_key"

  attribute {
    name = "company_id"
    type = "S"
  }

  attribute {
    name = "session_key"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at_epoch"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.data.arn
  }

  tags = local.common_tags
}

resource "aws_dynamodb_table" "processed_messages" {
  name         = "${var.name_prefix}-processed-messages"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "company_id"
  range_key    = "consumer_event_id"

  attribute {
    name = "company_id"
    type = "S"
  }

  attribute {
    name = "consumer_event_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.data.arn
  }

  tags = local.common_tags
}

resource "aws_db_subnet_group" "aurora" {
  name       = "${var.name_prefix}-aurora"
  subnet_ids = var.private_subnet_ids
  tags       = local.common_tags
}

resource "aws_rds_cluster" "aurora" {
  cluster_identifier          = "${var.name_prefix}-aurora"
  engine                      = "aurora-postgresql"
  engine_mode                 = "provisioned"
  engine_version              = "16.6"
  database_name               = var.database_name
  master_username             = var.database_master_username
  manage_master_user_password = true
  db_subnet_group_name        = aws_db_subnet_group.aurora.name
  vpc_security_group_ids      = [var.database_security_group_id]
  storage_encrypted           = true
  kms_key_id                  = aws_kms_key.data.arn
  backup_retention_period     = var.backup_retention_days
  preferred_backup_window     = "18:00-19:00"
  deletion_protection         = var.deletion_protection
  skip_final_snapshot         = !var.deletion_protection
  final_snapshot_identifier   = var.deletion_protection ? "${var.name_prefix}-final" : null
  copy_tags_to_snapshot       = true

  serverlessv2_scaling_configuration {
    min_capacity = 0.5
    max_capacity = var.environment == "prod" ? 16 : 4
  }

  tags = local.common_tags
}

resource "aws_rds_cluster_instance" "aurora" {
  count = var.environment == "prod" ? 2 : 1

  identifier         = "${var.name_prefix}-aurora-${count.index + 1}"
  cluster_identifier = aws_rds_cluster.aurora.id
  instance_class     = "db.serverless"
  engine             = aws_rds_cluster.aurora.engine
  engine_version     = aws_rds_cluster.aurora.engine_version

  tags = local.common_tags
}

resource "aws_secretsmanager_secret" "application" {
  name                    = "${var.name_prefix}/application"
  kms_key_id              = aws_kms_key.data.arn
  recovery_window_in_days = var.environment == "prod" ? 30 : 7
  tags                    = local.common_tags
}

output "kms_key_arn" {
  value = aws_kms_key.data.arn
}

output "bucket_arns" {
  value = { for key, bucket in aws_s3_bucket.data : key => bucket.arn }
}

output "aurora_endpoint" {
  value = aws_rds_cluster.aurora.endpoint
}

output "aurora_reader_endpoint" {
  value = aws_rds_cluster.aurora.reader_endpoint
}

output "aurora_master_secret_arn" {
  value     = aws_rds_cluster.aurora.master_user_secret[0].secret_arn
  sensitive = true
}

output "application_secret_arn" {
  value = aws_secretsmanager_secret.application.arn
}

output "dynamodb_table_names" {
  value = {
    hot_context        = aws_dynamodb_table.hot_context.name
    processed_messages = aws_dynamodb_table.processed_messages.name
  }
}
