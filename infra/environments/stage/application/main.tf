terraform {
  required_version = ">= 1.10.0, < 2.0.0"

  backend "s3" {
    key          = "interview-evidence/stage/application.tfstate"
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

variable "vpc_id" {
  type    = string
  default = "vpc-00000000000000000"
}

variable "public_subnet_ids" {
  type    = list(string)
  default = ["subnet-00000000000000001", "subnet-00000000000000002"]
}

variable "private_subnet_ids" {
  type    = list(string)
  default = ["subnet-00000000000000003", "subnet-00000000000000004"]
}

variable "alb_security_group_id" {
  type    = string
  default = "sg-00000000000000001"
}

variable "api_security_group_id" {
  type    = string
  default = "sg-00000000000000002"
}

variable "worker_security_group_id" {
  type    = string
  default = "sg-00000000000000003"
}

variable "api_image" {
  type    = string
  default = "public.ecr.aws/docker/library/python:3.12-slim"
}

variable "worker_image" {
  type    = string
  default = "public.ecr.aws/docker/library/python:3.12-slim"
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
      Environment        = "stage"
      ManagedBy          = "Terraform"
      DataClassification = "Restricted"
      CostCenter         = "InterviewPlatform"
    }
  }
}

module "compute" {
  source = "../../../modules/compute"

  name_prefix              = "iep-stage"
  environment              = "stage"
  aws_region               = var.aws_region
  vpc_id                   = var.vpc_id
  public_subnet_ids        = var.public_subnet_ids
  private_subnet_ids       = var.private_subnet_ids
  alb_security_group_id    = var.alb_security_group_id
  api_security_group_id    = var.api_security_group_id
  worker_security_group_id = var.worker_security_group_id
  api_image                = var.api_image
  worker_image             = var.worker_image
  api_desired_count        = 2
  worker_desired_count     = 2
  environment_variables = {
    LOG_FORMAT = "json"
  }
  tags = {
    StateRoot = "application"
  }
}

output "application" {
  value = {
    cluster_arn           = module.compute.cluster_arn
    service_names         = module.compute.service_names
    repository_urls       = module.compute.repository_urls
    api_load_balancer_dns = module.compute.api_load_balancer_dns
  }
}
