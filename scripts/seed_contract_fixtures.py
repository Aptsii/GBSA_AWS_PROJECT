#!/usr/bin/env python3
"""Seed synthetic contract fixtures into local AWS-compatible services."""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

import boto3
import httpx
from botocore.config import Config
from botocore.exceptions import ClientError

REGION = os.getenv("AWS_REGION", "ap-northeast-2")
AWS_ENDPOINT = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
DYNAMODB_ENDPOINT = os.getenv("DYNAMODB_ENDPOINT_URL", "http://localhost:8000")
OPENSEARCH_URL = os.getenv("OPENSEARCH_URL", "http://localhost:9200")

COMPANY_ID = "018f2000-0000-7000-8000-000000000100"
APPLICANT_ID = "018f2000-0000-7000-8000-000000000211"
INVITATION_ID = "018f2000-0000-7000-8000-000000000210"
BUCKET_NAME = "iep-local-contract-fixtures"
STATE_BUCKET_NAME = "iep-local-terraform-state"
QUEUE_NAME = "iep-local-contract-events"
DLQ_NAME = "iep-local-contract-events-dlq"
TABLE_NAME = "iep-local-contract-hot-view"
INDEX_NAME = "iep-local-contract-search"


def _aws_client(service: str, *, endpoint_url: str) -> Any:
    return boto3.client(
        service,
        region_name=REGION,
        endpoint_url=endpoint_url,
        config=Config(connect_timeout=3, read_timeout=5, retries={"max_attempts": 1}),
    )


def _ensure_bucket(s3: Any, bucket_name: str) -> None:
    try:
        arguments: dict[str, object] = {"Bucket": bucket_name}
        if REGION != "us-east-1":
            arguments["CreateBucketConfiguration"] = {"LocationConstraint": REGION}
        s3.create_bucket(**arguments)
    except ClientError as error:
        if error.response["Error"]["Code"] not in {
            "BucketAlreadyExists",
            "BucketAlreadyOwnedByYou",
        }:
            raise


def _seed_s3() -> str:
    s3 = _aws_client("s3", endpoint_url=AWS_ENDPOINT)
    _ensure_bucket(s3, BUCKET_NAME)
    _ensure_bucket(s3, STATE_BUCKET_NAME)
    key = f"fixtures/{COMPANY_ID}/{APPLICANT_ID}/manifest.json"
    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=key,
        Body=json.dumps(
            {
                "fixture_version": "contract-v1",
                "company_id": COMPANY_ID,
                "applicant_id": APPLICANT_ID,
                "invitation_id": INVITATION_ID,
            },
            sort_keys=True,
        ).encode(),
        ContentType="application/json",
    )
    return key


def _seed_sqs() -> tuple[str, str]:
    sqs = _aws_client("sqs", endpoint_url=AWS_ENDPOINT)
    dlq_url = sqs.create_queue(QueueName=DLQ_NAME)["QueueUrl"]
    queue_url = sqs.create_queue(QueueName=QUEUE_NAME)["QueueUrl"]
    return queue_url, dlq_url


def _seed_dynamodb() -> None:
    dynamodb = _aws_client("dynamodb", endpoint_url=DYNAMODB_ENDPOINT)
    try:
        dynamodb.create_table(
            TableName=TABLE_NAME,
            AttributeDefinitions=[
                {"AttributeName": "company_id", "AttributeType": "S"},
                {"AttributeName": "entity_id", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "company_id", "KeyType": "HASH"},
                {"AttributeName": "entity_id", "KeyType": "RANGE"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
    except ClientError as error:
        if error.response["Error"]["Code"] != "ResourceInUseException":
            raise
    for _attempt in range(50):
        if dynamodb.describe_table(TableName=TABLE_NAME)["Table"]["TableStatus"] == "ACTIVE":
            break
        time.sleep(0.1)
    else:
        raise TimeoutError("local DynamoDB fixture table did not become active")
    dynamodb.put_item(
        TableName=TABLE_NAME,
        Item={
            "company_id": {"S": COMPANY_ID},
            "entity_id": {"S": APPLICANT_ID},
            "invitation_id": {"S": INVITATION_ID},
            "fixture_version": {"S": "contract-v1"},
        },
    )


def _seed_opensearch() -> None:
    with httpx.Client(base_url=OPENSEARCH_URL, timeout=10) as client:
        created = client.put(f"/{INDEX_NAME}")
        if created.status_code not in {200, 400}:
            created.raise_for_status()
        indexed = client.put(
            f"/{INDEX_NAME}/_doc/{COMPANY_ID}:{APPLICANT_ID}",
            params={"refresh": "true"},
            json={
                "company_id": COMPANY_ID,
                "applicant_id": APPLICANT_ID,
                "invitation_id": INVITATION_ID,
                "fixture_version": "contract-v1",
            },
        )
        indexed.raise_for_status()


def main() -> int:
    object_key = _seed_s3()
    queue_url, dlq_url = _seed_sqs()
    _seed_dynamodb()
    _seed_opensearch()
    result = {
        "applicant_id": APPLICANT_ID,
        "bucket": BUCKET_NAME,
        "company_id": COMPANY_ID,
        "dynamodb_table": TABLE_NAME,
        "invitation_id": INVITATION_ID,
        "object_key": object_key,
        "opensearch_index": INDEX_NAME,
        "queue_name": queue_url.rsplit("/", 1)[-1],
        "queue_dlq_name": dlq_url.rsplit("/", 1)[-1],
        "status": "seeded",
        "terraform_state_bucket": STATE_BUCKET_NAME,
    }
    sys.stdout.write(json.dumps(result, sort_keys=True, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
