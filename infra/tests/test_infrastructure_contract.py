from __future__ import annotations

import re
from pathlib import Path

INFRA_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (INFRA_ROOT / relative_path).read_text(encoding="utf-8")


def test_reusable_modules_cover_required_aws_boundaries() -> None:
    required_resources = {
        "modules/network/main.tf": (
            "aws_vpc",
            "aws_subnet",
            "aws_vpc_endpoint",
            "aws_security_group",
        ),
        "modules/edge/main.tf": (
            "aws_cloudfront_distribution",
            "aws_cloudfront_origin_access_control",
            "aws_wafv2_web_acl",
            "aws_acm_certificate",
            "aws_route53_record",
        ),
        "modules/compute/main.tf": (
            "aws_ecr_repository",
            "aws_lb",
            "aws_ecs_service",
            "aws_appautoscaling_target",
        ),
        "modules/data/main.tf": (
            "aws_rds_cluster",
            "aws_dynamodb_table",
            "aws_s3_bucket",
            "aws_kms_key",
            "aws_secretsmanager_secret",
        ),
        "modules/async-workflow/main.tf": (
            "aws_sqs_queue",
            "aws_sfn_state_machine",
            "aws_cloudwatch_event_bus",
        ),
        "modules/ai-search/main.tf": (
            "aws_opensearchserverless_collection",
            "aws_bedrockagent_knowledge_base",
            "aws_bedrock_guardrail",
        ),
        "modules/identity/main.tf": (
            "aws_cognito_user_pool",
            "aws_ses_email_identity",
            "aws_iam_role",
        ),
        "modules/observability/main.tf": (
            "aws_cloudwatch_metric_alarm",
            "aws_xray_sampling_rule",
            "aws_cloudtrail",
            "aws_budgets_budget",
        ),
    }

    for relative_path, resources in required_resources.items():
        configuration = _read(relative_path)
        for resource in resources:
            assert f'resource "{resource}"' in configuration, (relative_path, resource)


def test_state_roots_use_distinct_encrypted_native_lockfile_backends() -> None:
    roots = (
        "environments/dev/foundation/main.tf",
        "environments/dev/data-ai/main.tf",
        "environments/dev/application/main.tf",
        "environments/stage/main.tf",
        "environments/prod/main.tf",
    )
    keys: set[str] = set()

    for relative_path in roots:
        configuration = _read(relative_path)
        backend = re.search(r'backend "s3" \{(?P<body>.*?)\n  \}', configuration, re.DOTALL)
        assert backend is not None, relative_path
        body = backend.group("body")
        assert "encrypt      = true" in body
        assert "use_lockfile = true" in body
        assert "bucket" not in body
        key = re.search(r'key\s*=\s*"(?P<key>[^"]+)"', body)
        assert key is not None
        keys.add(key.group("key"))

    assert len(keys) == len(roots)


def test_storage_is_private_encrypted_and_protected() -> None:
    edge = _read("modules/edge/main.tf")
    data = _read("modules/data/main.tf")
    production = _read("environments/prod/main.tf")

    assert "aws_s3_bucket_public_access_block" in edge
    assert "aws_s3_bucket_public_access_block" in data
    assert "block_public_policy     = true" in edge
    assert "restrict_public_buckets = true" in data
    assert 'sse_algorithm     = "aws:kms"' in data
    assert "storage_encrypted           = true" in data
    assert "publicly_accessible" not in data
    assert "deletion_protection        = true" in production


def test_application_deployments_do_not_fight_pipeline_or_autoscaling() -> None:
    compute = _read("modules/compute/main.tf")

    assert "ignore_changes = [desired_count, task_definition]" in compute
    assert "image_tag_mutability = \"IMMUTABLE\"" in compute
    assert "assign_public_ip = false" in compute


def test_terraform_contains_no_business_workflow_provisioners_or_secrets() -> None:
    terraform_files = tuple(INFRA_ROOT.rglob("*.tf"))
    prohibited = ("local-exec", "remote-exec", "provisioner \"", "BEGIN PRIVATE KEY")

    for terraform_file in terraform_files:
        configuration = terraform_file.read_text(encoding="utf-8")
        for marker in prohibited:
            assert marker not in configuration, (terraform_file, marker)
        assert not re.search(
            r'(?i)(password|secret|token)\s*=\s*"(?!\$\{|mock_|<)[^"]{8,}"',
            configuration,
        ), terraform_file
