terraform {
  required_version = ">= 1.10.0, < 2.0.0"

  backend "s3" {
    key          = "interview-evidence/dev/data-ai.tfstate"
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

variable "account_id" {
  type    = string
  default = "000000000000"
}

variable "local_validation" {
  type    = bool
  default = true
}

variable "vpc_id" {
  type    = string
  default = "vpc-00000000000000000"
}

variable "private_subnet_ids" {
  type    = list(string)
  default = ["subnet-00000000000000001", "subnet-00000000000000002"]
}

variable "database_security_group_id" {
  type    = string
  default = "sg-00000000000000001"
}

variable "endpoint_security_group_id" {
  type    = string
  default = "sg-00000000000000002"
}

provider "aws" {
  region                      = var.aws_region
  skip_credentials_validation = var.local_validation
  skip_metadata_api_check     = var.local_validation
  skip_region_validation      = var.local_validation
  skip_requesting_account_id  = var.local_validation
}

locals {
  name_prefix = "iep-dev"
  tags = {
    StateRoot = "data-ai"
  }
}

module "data" {
  source = "../../../modules/data"

  name_prefix                = local.name_prefix
  environment                = "dev"
  private_subnet_ids         = var.private_subnet_ids
  database_security_group_id = var.database_security_group_id
  deletion_protection        = false
  backup_retention_days      = 7
  tags                       = local.tags
}

module "async_workflow" {
  source = "../../../modules/async-workflow"

  name_prefix = local.name_prefix
  environment = "dev"
  kms_key_arn = module.data.kms_key_arn
  tags        = local.tags
}

module "ai_search" {
  source = "../../../modules/ai-search"

  name_prefix        = local.name_prefix
  environment        = "dev"
  account_id         = var.account_id
  vpc_id             = var.vpc_id
  private_subnet_ids = var.private_subnet_ids
  security_group_ids = [var.endpoint_security_group_id]
  kms_key_arn        = module.data.kms_key_arn
  tags               = local.tags
}

module "observability" {
  source = "../../../modules/observability"

  name_prefix        = local.name_prefix
  environment        = "dev"
  account_id         = var.account_id
  kms_key_arn        = module.data.kms_key_arn
  monthly_budget_usd = 500
  tags               = local.tags
}

output "data" {
  sensitive = true
  value = {
    kms_key_arn              = module.data.kms_key_arn
    bucket_arns              = module.data.bucket_arns
    aurora_endpoint          = module.data.aurora_endpoint
    aurora_reader_endpoint   = module.data.aurora_reader_endpoint
    aurora_master_secret_arn = module.data.aurora_master_secret_arn
    application_secret_arn   = module.data.application_secret_arn
    dynamodb_table_names     = module.data.dynamodb_table_names
  }
}

output "workflow" {
  value = {
    queue_url         = module.async_workflow.job_queue_url
    queue_arn         = module.async_workflow.job_queue_arn
    event_bus_arn     = module.async_workflow.event_bus_arn
    state_machine_arn = module.async_workflow.state_machine_arn
  }
}

output "ai" {
  value = {
    collection_arn    = module.ai_search.collection_arn
    knowledge_base_id = module.ai_search.knowledge_base_id
    guardrail_id      = module.ai_search.guardrail_id
  }
}
