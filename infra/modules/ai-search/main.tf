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

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "security_group_ids" {
  type = list(string)
}

variable "kms_key_arn" {
  type = string
}

variable "embedding_model_arn" {
  type    = string
  default = "arn:aws:bedrock:ap-northeast-2::foundation-model/amazon.titan-embed-text-v2:0"
}

variable "additional_principal_arns" {
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
    DataClassification = "Restricted"
    CostCenter         = "InterviewPlatform"
  })

  collection_name = substr(replace("${var.name_prefix}-evidence", "_", "-"), 0, 32)
  vector_index = {
    name           = "interview-evidence-v1"
    vector_field   = "embedding"
    text_field     = "source_text"
    metadata_field = "metadata"
    dimensions     = 1024
    engine         = "faiss"
    space_type     = "l2"
  }
}

resource "aws_opensearchserverless_security_policy" "encryption" {
  name = "${local.collection_name}-enc"
  type = "encryption"
  policy = jsonencode({
    Rules = [{
      Resource     = ["collection/${local.collection_name}"]
      ResourceType = "collection"
    }]
    AWSOwnedKey = false
    KmsARN      = var.kms_key_arn
  })
}

resource "aws_opensearchserverless_vpc_endpoint" "this" {
  name               = "${local.collection_name}-vpce"
  vpc_id             = var.vpc_id
  subnet_ids         = var.private_subnet_ids
  security_group_ids = var.security_group_ids
}

resource "aws_opensearchserverless_security_policy" "network" {
  name = "${local.collection_name}-net"
  type = "network"
  policy = jsonencode([{
    Description = "Private application and Bedrock Knowledge Base access"
    Rules = [
      {
        Resource     = ["collection/${local.collection_name}"]
        ResourceType = "collection"
      },
      {
        Resource     = ["collection/${local.collection_name}"]
        ResourceType = "dashboard"
      },
    ]
    AllowFromPublic = false
    SourceVPCEs     = [aws_opensearchserverless_vpc_endpoint.this.id]
    SourceServices  = ["bedrock.amazonaws.com"]
  }])
}

resource "aws_opensearchserverless_collection" "evidence" {
  name        = local.collection_name
  description = "Tenant-prefiltered submission retrieval collection"
  type        = "VECTORSEARCH"
  tags        = local.common_tags

  depends_on = [
    aws_opensearchserverless_security_policy.encryption,
    aws_opensearchserverless_security_policy.network,
  ]
}

data "aws_iam_policy_document" "bedrock_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["bedrock.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [var.account_id]
    }
  }
}

resource "aws_iam_role" "knowledge_base" {
  name               = "${var.name_prefix}-bedrock-kb"
  assume_role_policy = data.aws_iam_policy_document.bedrock_assume.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "knowledge_base" {
  statement {
    actions   = ["bedrock:InvokeModel"]
    resources = [var.embedding_model_arn]
  }

  statement {
    actions = ["aoss:APIAccessAll"]
    resources = [
      aws_opensearchserverless_collection.evidence.arn,
    ]
  }

  statement {
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [var.kms_key_arn]
  }
}

resource "aws_iam_role_policy" "knowledge_base" {
  name   = "knowledge-base-access"
  role   = aws_iam_role.knowledge_base.id
  policy = data.aws_iam_policy_document.knowledge_base.json
}

resource "aws_opensearchserverless_access_policy" "evidence" {
  name = "${local.collection_name}-data"
  type = "data"
  policy = jsonencode([{
    Description = "Application and Bedrock access with tenant filters enforced by the application"
    Rules = [
      {
        ResourceType = "collection"
        Resource     = ["collection/${local.collection_name}"]
        Permission   = ["aoss:DescribeCollectionItems", "aoss:CreateCollectionItems", "aoss:UpdateCollectionItems"]
      },
      {
        ResourceType = "index"
        Resource     = ["index/${local.collection_name}/*"]
        Permission   = ["aoss:CreateIndex", "aoss:DescribeIndex", "aoss:ReadDocument", "aoss:UpdateIndex", "aoss:WriteDocument", "aoss:DeleteDocument"]
      },
    ]
    Principal = concat([aws_iam_role.knowledge_base.arn], var.additional_principal_arns)
  }])
}

resource "terraform_data" "vector_index_contract" {
  input = local.vector_index
}

resource "aws_bedrockagent_knowledge_base" "evidence" {
  name     = "${var.name_prefix}-evidence"
  role_arn = aws_iam_role.knowledge_base.arn

  knowledge_base_configuration {
    type = "VECTOR"
    vector_knowledge_base_configuration {
      embedding_model_arn = var.embedding_model_arn
    }
  }

  storage_configuration {
    type = "OPENSEARCH_SERVERLESS"
    opensearch_serverless_configuration {
      collection_arn    = aws_opensearchserverless_collection.evidence.arn
      vector_index_name = local.vector_index.name
      field_mapping {
        vector_field   = local.vector_index.vector_field
        text_field     = local.vector_index.text_field
        metadata_field = local.vector_index.metadata_field
      }
    }
  }

  tags = local.common_tags

  depends_on = [
    aws_iam_role_policy.knowledge_base,
    aws_opensearchserverless_access_policy.evidence,
    terraform_data.vector_index_contract,
  ]
}

resource "aws_bedrock_guardrail" "interview" {
  name                      = "${var.name_prefix}-interview"
  description               = "Blocks prohibited and sensitive interview content"
  blocked_input_messaging   = "요청을 안전하게 처리할 수 없습니다."
  blocked_outputs_messaging = "안전 기준에 따라 응답을 생성하지 않았습니다."

  content_policy_config {
    filters_config {
      input_strength  = "HIGH"
      output_strength = "HIGH"
      type            = "HATE"
    }
    filters_config {
      input_strength  = "HIGH"
      output_strength = "HIGH"
      type            = "SEXUAL"
    }
    filters_config {
      input_strength  = "HIGH"
      output_strength = "HIGH"
      type            = "VIOLENCE"
    }
  }

  sensitive_information_policy_config {
    pii_entities_config {
      action = "BLOCK"
      type   = "AWS_ACCESS_KEY"
    }
    pii_entities_config {
      action = "ANONYMIZE"
      type   = "EMAIL"
    }
  }

  tags = local.common_tags
}

output "collection_arn" {
  value = aws_opensearchserverless_collection.evidence.arn
}

output "collection_endpoint" {
  value = aws_opensearchserverless_collection.evidence.collection_endpoint
}

output "knowledge_base_id" {
  value = aws_bedrockagent_knowledge_base.evidence.id
}

output "guardrail_id" {
  value = aws_bedrock_guardrail.interview.guardrail_id
}

output "vector_index_mapping" {
  value = local.vector_index
}
