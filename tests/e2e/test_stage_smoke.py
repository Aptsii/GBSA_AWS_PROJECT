"""Authenticated stage smoke from CloudFront through tenant-scoped AWS services."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import boto3  # type: ignore[import-untyped]
import httpx
import pytest

_ENABLE_VARIABLE = "IEP_RUN_STAGE_SMOKE"
_CONFIG_VARIABLE = "IEP_STAGE_SMOKE_CONFIG"
_TOKEN_VARIABLE = "IEP_STAGE_COMPANY_BEARER"


def test_stage_smoke_config_requires_authenticated_business_fixture() -> None:
    field_names = {field.name for field in fields(StageSmokeConfig)}

    assert {
        "company_id",
        "position_id",
        "applicant_id",
        "invitation_id",
        "s3_object_key",
        "dynamodb_session_key",
        "bedrock_knowledge_base_id",
        "retrieval_query",
    } <= field_names


def _example_config() -> StageSmokeConfig:
    return StageSmokeConfig(
        company_url="https://company.stage.example.invalid",
        applicant_url="https://applicant.stage.example.invalid",
        api_url="https://api.stage.example.invalid",
        region="ap-northeast-2",
        s3_bucket="iep-stage-submissions",
        dynamodb_table="iep-stage-hot-context",
        sqs_queue_url="https://sqs.ap-northeast-2.amazonaws.com/123456789012/iep-stage",
        aurora_cluster_id="iep-stage-aurora",
        kms_key_id="alias/iep-stage-data",
        secret_id="iep-stage/application",
        aoss_collection_id="collection-stage",
        bedrock_guardrail_id="guardrail-stage",
        ecs_cluster="iep-stage",
        api_service="iep-stage-api",
        worker_service="iep-stage-worker",
        waf_web_acl_name="iep-stage-edge",
        waf_web_acl_id="waf-stage",
        company_id="0198b6c5-8800-7000-8000-000000000001",
        position_id="0198b6c5-8800-7000-8000-000000000002",
        applicant_id="0198b6c5-8800-7000-8000-000000000003",
        invitation_id="0198b6c5-8800-7000-8000-000000000004",
        s3_object_key="stage-smoke/fixture.json",
        dynamodb_session_key="stage-smoke-session",
        bedrock_knowledge_base_id="KBSTAGE123",
        retrieval_query="복구 설계 판단",
    )


def test_authenticated_business_journey_uses_cloudfront_api_and_tenant_scope() -> None:
    config = _example_config()

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer stage-token"
        headers = {"via": "1.1 example.cloudfront.net (CloudFront)"}
        if request.url.path == "/v1/me":
            return httpx.Response(200, headers=headers, json={"company_id": config.company_id})
        if request.url.path == "/v1/positions":
            return httpx.Response(
                200,
                headers=headers,
                json={"items": [{"position_id": config.position_id}]},
            )
        return httpx.Response(404, headers=headers)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        _assert_authenticated_business_journey(client, config, "stage-token")


def test_business_data_and_ai_use_the_same_tenant_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _example_config()
    retrieval_arguments: dict[str, object] = {}

    class Body:
        def read(self) -> bytes:
            return json.dumps(
                {
                    "company_id": config.company_id,
                    "applicant_id": config.applicant_id,
                    "invitation_id": config.invitation_id,
                }
            ).encode()

    class S3:
        def get_object(self, **_: object) -> dict[str, object]:
            return {"Body": Body()}

    class DynamoDB:
        def get_item(self, **_: object) -> dict[str, object]:
            return {
                "Item": {
                    "company_id": {"S": config.company_id},
                    "applicant_id": {"S": config.applicant_id},
                    "invitation_id": {"S": config.invitation_id},
                }
            }

    class Bedrock:
        def retrieve(self, **arguments: object) -> dict[str, object]:
            retrieval_arguments.update(arguments)
            return {
                "retrievalResults": [
                    {
                        "metadata": {
                            "company_id": config.company_id,
                            "applicant_id": config.applicant_id,
                            "invitation_id": config.invitation_id,
                        }
                    }
                ]
            }

    clients = {"s3": S3(), "dynamodb": DynamoDB(), "bedrock-agent-runtime": Bedrock()}
    monkeypatch.setattr(boto3, "client", lambda service, **_: clients[service])

    _assert_business_data_and_ai(config)

    assert retrieval_arguments["knowledgeBaseId"] == config.bedrock_knowledge_base_id
    configuration = retrieval_arguments["retrievalConfiguration"]
    assert isinstance(configuration, dict)
    filters = configuration["vectorSearchConfiguration"]["filter"]["andAll"]
    assert filters == [
        {"equals": {"key": "company_id", "value": config.company_id}},
        {"equals": {"key": "applicant_id", "value": config.applicant_id}},
    ]


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
    company_id: str
    position_id: str
    applicant_id: str
    invitation_id: str
    s3_object_key: str
    dynamodb_session_key: str
    bedrock_knowledge_base_id: str
    retrieval_query: str

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
        for identifier in (
            config.company_id,
            config.position_id,
            config.applicant_id,
            config.invitation_id,
            config.s3_object_key,
            config.dynamodb_session_key,
            config.bedrock_knowledge_base_id,
            config.retrieval_query,
        ):
            if not isinstance(identifier, str) or not identifier.strip():
                raise ValueError("stage smoke business fixture values must be present")
        return config


def _assert_cloudfront_path(response: httpx.Response) -> None:
    cloudfront_path = " ".join(
        (
            response.headers.get("via", ""),
            response.headers.get("x-cache", ""),
            response.headers.get("x-amz-cf-id", ""),
        )
    ).casefold()
    assert "cloudfront" in cloudfront_path or response.headers.get("x-amz-cf-id")


def _cloudfront_spa(client: httpx.Client, url: str) -> None:
    response = client.get(url)
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    _assert_cloudfront_path(response)


def _stage_bearer() -> str:
    bearer = os.getenv(_TOKEN_VARIABLE)
    if bearer is None or not bearer.strip() or any(character.isspace() for character in bearer):
        raise ValueError(f"{_TOKEN_VARIABLE} must contain the stage company bearer token")
    return bearer


def _assert_authenticated_business_journey(
    client: httpx.Client,
    config: StageSmokeConfig,
    bearer: str,
) -> None:
    headers = {"Authorization": f"Bearer {bearer}"}
    api_base = config.api_url.rstrip("/")
    current_user = client.get(f"{api_base}/v1/me", headers=headers)
    assert current_user.status_code == 200
    _assert_cloudfront_path(current_user)
    current_user_payload = current_user.json()
    assert current_user_payload["company_id"] == config.company_id

    positions = client.get(f"{api_base}/v1/positions", headers=headers, params={"limit": 100})
    assert positions.status_code == 200
    _assert_cloudfront_path(positions)
    position_payload = positions.json()
    assert any(
        item.get("position_id") == config.position_id
        for item in position_payload.get("items", [])
        if isinstance(item, dict)
    )


def _assert_business_data_and_ai(config: StageSmokeConfig) -> None:
    s3 = boto3.client("s3", region_name=config.region)
    response = s3.get_object(Bucket=config.s3_bucket, Key=config.s3_object_key)
    fixture = json.loads(response["Body"].read())
    assert fixture["company_id"] == config.company_id
    assert fixture["applicant_id"] == config.applicant_id
    assert fixture["invitation_id"] == config.invitation_id

    dynamodb = boto3.client("dynamodb", region_name=config.region)
    item = dynamodb.get_item(
        TableName=config.dynamodb_table,
        Key={
            "company_id": {"S": config.company_id},
            "session_key": {"S": config.dynamodb_session_key},
        },
        ConsistentRead=True,
    ).get("Item")
    assert item is not None
    assert item["company_id"]["S"] == config.company_id
    assert item["applicant_id"]["S"] == config.applicant_id
    assert item["invitation_id"]["S"] == config.invitation_id

    bedrock = boto3.client("bedrock-agent-runtime", region_name=config.region)
    retrieval = bedrock.retrieve(
        knowledgeBaseId=config.bedrock_knowledge_base_id,
        retrievalQuery={"text": config.retrieval_query},
        retrievalConfiguration={
            "vectorSearchConfiguration": {
                "numberOfResults": 5,
                "filter": {
                    "andAll": [
                        {
                            "equals": {
                                "key": "company_id",
                                "value": config.company_id,
                            }
                        },
                        {
                            "equals": {
                                "key": "applicant_id",
                                "value": config.applicant_id,
                            }
                        },
                    ]
                },
            }
        },
    )
    results = retrieval.get("retrievalResults", [])
    assert results
    assert any(
        result.get("metadata", {}).get("company_id") == config.company_id
        and result.get("metadata", {}).get("applicant_id") == config.applicant_id
        and result.get("metadata", {}).get("invitation_id") == config.invitation_id
        for result in results
    )


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
    cluster = rds.describe_db_clusters(DBClusterIdentifier=config.aurora_cluster_id)["DBClusters"][
        0
    ]
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
    bearer = _stage_bearer()
    with httpx.Client(timeout=20, follow_redirects=True) as client:
        _cloudfront_spa(client, config.company_url)
        _cloudfront_spa(client, config.applicant_url)
        _assert_authenticated_business_journey(client, config, bearer)
        ready = client.get(f"{config.api_url.rstrip('/')}/health/ready")
        assert ready.status_code == 200
        assert ready.json() == {"status": "ready"}
        _assert_cloudfront_path(ready)

    identity = boto3.client("sts", region_name=config.region).get_caller_identity()
    assert identity.get("Account") and identity.get("Arn")
    _assert_business_data_and_ai(config)
    _assert_ecs_ready(config)
    _assert_data_services_private_and_ready(config)
    _assert_ai_and_edge_controls(config)
