terraform {
  required_version = ">= 1.10.0, < 2.0.0"

  backend "s3" {
    key          = "interview-evidence/dev/foundation.tfstate"
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

variable "company_domain_name" {
  type    = string
  default = ""
}

variable "applicant_domain_name" {
  type    = string
  default = ""
}

variable "hosted_zone_id" {
  type    = string
  default = ""
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
      Environment        = var.environment
      ManagedBy          = "Terraform"
      DataClassification = "Confidential"
      CostCenter         = "InterviewPlatform"
    }
  }
}

provider "aws" {
  alias                       = "global"
  region                      = "us-east-1"
  skip_credentials_validation = var.local_validation
  skip_metadata_api_check     = var.local_validation
  skip_region_validation      = var.local_validation
  skip_requesting_account_id  = var.local_validation
}

locals {
  name_prefix = "iep-${var.environment}"
  tags = {
    StateRoot = "foundation"
  }
}

module "network" {
  source = "../../../modules/network"

  name_prefix          = local.name_prefix
  environment          = var.environment
  aws_region           = var.aws_region
  vpc_cidr             = "10.40.0.0/16"
  availability_zones   = ["${var.aws_region}a", "${var.aws_region}c"]
  public_subnet_cidrs  = ["10.40.0.0/24", "10.40.1.0/24"]
  private_subnet_cidrs = ["10.40.10.0/24", "10.40.11.0/24"]
  enable_nat_gateway   = false
  tags                 = local.tags
}

module "identity" {
  source = "../../../modules/identity"

  name_prefix = local.name_prefix
  environment = var.environment
  tags        = local.tags
}

module "edge" {
  source = "../../../modules/edge"

  providers = {
    aws        = aws
    aws.global = aws.global
  }

  name_prefix           = local.name_prefix
  environment           = var.environment
  company_domain_name   = var.company_domain_name
  applicant_domain_name = var.applicant_domain_name
  hosted_zone_id        = var.hosted_zone_id
  tags                  = local.tags
}

output "network" {
  value = {
    vpc_id                  = module.network.vpc_id
    public_subnet_ids       = module.network.public_subnet_ids
    private_subnet_ids      = module.network.private_subnet_ids
    security_group_ids      = module.network.security_group_ids
    private_route_table_ids = module.network.private_route_table_ids
  }
}

output "identity" {
  value = {
    company_user_pool_id        = module.identity.company_user_pool_id
    company_user_pool_client_id = module.identity.company_user_pool_client_id
  }
}

output "edge" {
  value = {
    distribution_ids     = module.edge.distribution_ids
    distribution_domains = module.edge.distribution_domains
    site_bucket_arns     = module.edge.site_bucket_arns
  }
}
