"""Read-only stage smoke from CloudFront through AWS application services."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import boto3
import httpx
import pytest

_ENABLE_VARIABLE = "IEP_RUN_STAGE_SMOKE"
_CONFIG_VARIABLE = "IEP_STAGE_SMOKE_CONFIG"


@dataclass(frozen=True, slots=True)
class StageSmokeConfig:
    company_url: str
    applicant_url: str
    api_url: str
    region: str
    s3_bucket: str
    dynamodb_table: str
    sqs_queue_url: str
    aurora_cluster_id: str
    kms_key_id: str
    secret_id: str
    aoss_collection_id: str
    bedrock_guardrail_id: str
    ecs_cluster: str
    api_service: str
    worker_service: str
    waf_web_acl_name: str
    waf_web_acl_id: str

    @classmethod
    def load(cls) -> StageSmokeConfig:
        config_path = os.getenv(_CONFIG_VARIABLE)
        if not config_path:
            raise ValueError(f"{_CONFIG_VARIABLE} must point to the stage smoke JSON file")
        payload = json.loads(Path(config_path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("stage smoke configuration must be a JSON object")
        required = {field.name for field in fields(cls)}
        missing = sorted(required - payload.keys())
        if missing:
            raise ValueError(f"stage smoke configuration is missing: {', '.join(missing)}")
        config = cls(**{name: payload[name] for name in required})
        for url in (config.company_url, config.applicant_url, config.api_url):
            parsed = urlparse(url)
            if parsed.scheme != "https" or not parsed.netloc or parsed.username is not None:
                raise ValueError("stage smoke URLs must be credential-free HTTPS URLs")
        return config


def _cloudfront_spa(client: httpx.Client, url: str) -> None:
    response = client.get(url)
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    cloudfront_path = " ".join(
        (
            response.headers.get("via", ""),
            response.headers.get("x-cache", ""),
            response.headers.get("x-amz-cf-id", ""),
        )
    ).casefold()
    assert "cloudfront" in cloudfront_path or response.headers.get("x-amz-cf-id")


def _assert_ecs_ready(config: StageSmokeConfig) -> None:
    ecs = boto3.client("ecs", region_name=config.region)
    response = ecs.describe_services(
        cluster=config.ecs_cluster,
        services=[config.api_service, config.worker_service],
    )
    assert not response.get("failures")
    services = response.get("services", [])
    assert len(services) == 2
    for service in services:
        assert service["status"] == "ACTIVE"
        assert service["desiredCount"] >= 1
        assert service["runningCount"] >= service["desiredCount"]


def _assert_data_services_private_and_ready(config: StageSmokeConfig) -> None:
    s3 = boto3.client("s3", region_name=config.region)
    s3.head_bucket(Bucket=config.s3_bucket)
    public_block = s3.get_public_access_block(Bucket=config.s3_bucket)[
        "PublicAccessBlockConfiguration"
    ]
    assert all(
        public_block[name]
        for name in (
            "BlockPublicAcls",
            "IgnorePublicAcls",
            "BlockPublicPolicy",
            "RestrictPublicBuckets",
        )
    )

    dynamodb = boto3.client("dynamodb", region_name=config.region)
    table = dynamodb.describe_table(TableName=config.dynamodb_table)["Table"]
    assert table["TableStatus"] == "ACTIVE"
    assert table.get("SSEDescription", {}).get("Status") == "ENABLED"

    sqs = boto3.client("sqs", region_name=config.region)
    queue = sqs.get_queue_attributes(
        QueueUrl=config.sqs_queue_url,
        AttributeNames=["QueueArn", "KmsMasterKeyId"],
    )["Attributes"]
    assert queue.get("QueueArn")
    assert queue.get("KmsMasterKeyId")

    rds = boto3.client("rds", region_name=config.region)
    cluster = rds.describe_db_clusters(DBClusterIdentifier=config.aurora_cluster_id)[
        "DBClusters"
    ][0]
    assert cluster["Status"] == "available"
    assert cluster["StorageEncrypted"] is True
    instance_ids = [member["DBInstanceIdentifier"] for member in cluster["DBClusterMembers"]]
    assert instance_ids
    instances = rds.describe_db_instances(
        Filters=[{"Name": "db-instance-id", "Values": instance_ids}]
    )["DBInstances"]
    assert instances and all(instance["PubliclyAccessible"] is False for instance in instances)

    kms = boto3.client("kms", region_name=config.region)
    assert kms.describe_key(KeyId=config.kms_key_id)["KeyMetadata"]["Enabled"] is True

    secrets = boto3.client("secretsmanager", region_name=config.region)
    secret = secrets.describe_secret(SecretId=config.secret_id)
    assert secret.get("ARN")
    assert secret.get("KmsKeyId")


def _assert_ai_and_edge_controls(config: StageSmokeConfig) -> None:
    aoss = boto3.client("opensearchserverless", region_name=config.region)
    collections = aoss.batch_get_collection(ids=[config.aoss_collection_id]).get(
        "collectionDetails", []
    )
    assert len(collections) == 1
    assert collections[0]["status"] == "ACTIVE"
    assert collections[0].get("collectionEndpoint")

    bedrock = boto3.client("bedrock", region_name=config.region)
    guardrail = bedrock.get_guardrail(
        guardrailIdentifier=config.bedrock_guardrail_id,
        guardrailVersion="DRAFT",
    )
    assert guardrail["status"] == "READY"

    waf = boto3.client("wafv2", region_name="us-east-1")
    web_acl: dict[str, Any] = waf.get_web_acl(
        Name=config.waf_web_acl_name,
        Scope="CLOUDFRONT",
        Id=config.waf_web_acl_id,
    )["WebACL"]
    assert web_acl["Id"] == config.waf_web_acl_id
    assert web_acl.get("VisibilityConfig", {}).get("CloudWatchMetricsEnabled") is True


def test_stage_cloudfront_to_aws_service_smoke() -> None:
    if os.getenv(_ENABLE_VARIABLE) != "1":
        pytest.skip(f"set {_ENABLE_VARIABLE}=1 with {_CONFIG_VARIABLE} to run stage smoke")

    config = StageSmokeConfig.load()
    with httpx.Client(timeout=20, follow_redirects=True) as client:
        _cloudfront_spa(client, config.company_url)
        _cloudfront_spa(client, config.applicant_url)
        ready = client.get(f"{config.api_url.rstrip('/')}/health/ready")
        assert ready.status_code == 200
        assert ready.json() == {"status": "ready"}

    identity = boto3.client("sts", region_name=config.region).get_caller_identity()
    assert identity.get("Account") and identity.get("Arn")
    _assert_ecs_ready(config)
    _assert_data_services_private_and_ready(config)
    _assert_ai_and_edge_controls(config)
