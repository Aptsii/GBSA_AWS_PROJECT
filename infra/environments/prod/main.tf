terraform {
  required_version = ">= 1.10.0, < 2.0.0"

  backend "s3" {
    key          = "interview-evidence/prod/platform.tfstate"
    region       = "ap-northeast-2"
    encrypt      = true
    use_lockfile = true
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.80.0, < 7.0.0"
    }
  }
}

variable "aws_region" {
  type    = string
  default = "ap-northeast-2"
}

variable "local_validation" {
  type    = bool
  default = true
}

variable "pipeline_principal_arn" {
  type    = string
  default = "arn:aws:iam::000000000000:root"
}

variable "private_subnet_ids" {
  type    = list(string)
  default = ["subnet-00000000000000001", "subnet-00000000000000002"]
}

variable "database_security_group_id" {
  type    = string
  default = "sg-00000000000000001"
}

provider "aws" {
  region                      = var.aws_region
  skip_credentials_validation = var.local_validation
  skip_metadata_api_check     = var.local_validation
  skip_region_validation      = var.local_validation
  skip_requesting_account_id  = var.local_validation

  default_tags {
    tags = {
      Project            = "InterviewEvidencePlatform"
      Environment        = "prod"
      ManagedBy          = "Terraform"
      DataClassification = "Restricted"
      CostCenter         = "InterviewPlatform"
    }
  }
}

data "aws_iam_policy_document" "deployment_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "AWS"
      identifiers = [var.pipeline_principal_arn]
    }
  }
}

resource "aws_iam_role" "deployment" {
  name                 = "iep-prod-deployment"
  assume_role_policy   = data.aws_iam_policy_document.deployment_assume.json
  max_session_duration = 3600

  tags = {
    StateRoot = "prod"
  }
}

data "aws_iam_policy_document" "deployment" {
  statement {
    actions = [
      "cloudformation:GetTemplateSummary",
      "dynamodb:DescribeTable",
      "ec2:Describe*",
      "ecs:Describe*",
      "iam:GetRole",
      "kms:DescribeKey",
      "rds:Describe*",
      "s3:GetBucketLocation",
      "s3:ListBucket",
      "secretsmanager:DescribeSecret",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "deployment" {
  name   = "reviewed-plan-read"
  role   = aws_iam_role.deployment.id
  policy = data.aws_iam_policy_document.deployment.json
}

module "data" {
  source = "../../modules/data"

  name_prefix                = "iep-prod"
  environment                = "prod"
  private_subnet_ids         = var.private_subnet_ids
  database_security_group_id = var.database_security_group_id
  deletion_protection        = true
  backup_retention_days      = 35
  tags = {
    StateRoot = "prod"
  }
}

output "deployment_role_arn" {
  value = aws_iam_role.deployment.arn
}

output "data_boundary" {
  sensitive = true
  value = {
    kms_key_arn              = module.data.kms_key_arn
    bucket_arns              = module.data.bucket_arns
    aurora_endpoint          = module.data.aurora_endpoint
    aurora_master_secret_arn = module.data.aurora_master_secret_arn
    dynamodb_table_names     = module.data.dynamodb_table_names
  }
}
