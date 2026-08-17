terraform {
  required_version = ">= 1.10.0, < 2.0.0"

  required_providers {
    aws = {
      source                = "hashicorp/aws"
      version               = ">= 5.80.0, < 7.0.0"
      configuration_aliases = [aws.global]
    }
  }
}

variable "name_prefix" {
  type = string
}

variable "environment" {
  type = string
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

  sites = {
    company = {
      domain = var.company_domain_name
      bucket = "${var.name_prefix}-company-console"
    }
    applicant = {
      domain = var.applicant_domain_name
      bucket = "${var.name_prefix}-applicant-interview"
    }
  }

  dns_sites = {
    for key, site in local.sites : key => site
    if site.domain != "" && var.hosted_zone_id != ""
  }
}

resource "aws_s3_bucket" "site" {
  for_each = local.sites

  bucket = each.value.bucket
  tags   = merge(local.common_tags, { Name = each.value.bucket })
}

resource "aws_s3_bucket_public_access_block" "site" {
  for_each = aws_s3_bucket.site

  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "site" {
  for_each = aws_s3_bucket.site

  bucket = each.value.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "site" {
  for_each = aws_s3_bucket.site

  bucket = each.value.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_cloudfront_origin_access_control" "site" {
  provider = aws.global
  for_each = local.sites

  name                              = "${var.name_prefix}-${each.key}"
  description                       = "Private S3 origin access for ${each.key}"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_wafv2_web_acl" "edge" {
  provider = aws.global

  name  = "${var.name_prefix}-edge"
  scope = "CLOUDFRONT"

  default_action {
    allow {}
  }

  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 10

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name_prefix}-common"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${var.name_prefix}-edge"
    sampled_requests_enabled   = true
  }

  tags = local.common_tags
}

resource "aws_acm_certificate" "site" {
  provider = aws.global
  for_each = local.dns_sites

  domain_name       = each.value.domain
  validation_method = "DNS"
  tags              = local.common_tags

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "certificate_validation" {
  provider = aws.global
  for_each = aws_acm_certificate.site

  zone_id = var.hosted_zone_id
  name    = tolist(each.value.domain_validation_options)[0].resource_record_name
  type    = tolist(each.value.domain_validation_options)[0].resource_record_type
  records = [tolist(each.value.domain_validation_options)[0].resource_record_value]
  ttl     = 60
}

resource "aws_acm_certificate_validation" "site" {
  provider = aws.global
  for_each = aws_acm_certificate.site

  certificate_arn         = each.value.arn
  validation_record_fqdns = [aws_route53_record.certificate_validation[each.key].fqdn]
}

resource "aws_cloudfront_distribution" "site" {
  provider = aws.global
  for_each = local.sites

  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"
  web_acl_id          = aws_wafv2_web_acl.edge.arn
  aliases             = each.value.domain == "" ? [] : [each.value.domain]

  origin {
    domain_name              = aws_s3_bucket.site[each.key].bucket_regional_domain_name
    origin_id                = "s3-${each.key}"
    origin_access_control_id = aws_cloudfront_origin_access_control.site[each.key].id
  }

  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "s3-${each.key}"
    viewer_protocol_policy = "redirect-to-https"
    compress               = true

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    min_ttl     = 0
    default_ttl = 300
    max_ttl     = 86400
  }

  custom_error_response {
    error_code            = 403
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 0
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = each.value.domain == ""
    acm_certificate_arn = each.value.domain == "" ? null : aws_acm_certificate_validation.site[
      each.key
    ].certificate_arn
    ssl_support_method       = each.value.domain == "" ? null : "sni-only"
    minimum_protocol_version = each.value.domain == "" ? "TLSv1" : "TLSv1.2_2021"
  }

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-${each.key}" })
}

data "aws_iam_policy_document" "site" {
  for_each = local.sites

  statement {
    sid     = "AllowCloudFrontRead"
    actions = ["s3:GetObject"]
    resources = [
      "${aws_s3_bucket.site[each.key].arn}/*",
    ]
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.site[each.key].arn]
    }
  }
}

resource "aws_s3_bucket_policy" "site" {
  for_each = local.sites

  bucket = aws_s3_bucket.site[each.key].id
  policy = data.aws_iam_policy_document.site[each.key].json
}

resource "aws_route53_record" "site" {
  provider = aws.global
  for_each = local.dns_sites

  zone_id = var.hosted_zone_id
  name    = each.value.domain
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.site[each.key].domain_name
    zone_id                = aws_cloudfront_distribution.site[each.key].hosted_zone_id
    evaluate_target_health = false
  }
}

output "site_bucket_arns" {
  value = { for key, bucket in aws_s3_bucket.site : key => bucket.arn }
}

output "distribution_ids" {
  value = { for key, distribution in aws_cloudfront_distribution.site : key => distribution.id }
}

output "distribution_domains" {
  value = {
    for key, distribution in aws_cloudfront_distribution.site : key => distribution.domain_name
  }
}
