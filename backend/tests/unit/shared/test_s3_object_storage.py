from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from interview_evidence.shared.aws_clients.ports import ObjectRef
from interview_evidence.shared.aws_clients.s3 import S3ObjectStorage
from interview_evidence.shared.tenant import ActorType, ApplicantScope, TenantContext


class StubS3Client:
    exceptions = SimpleNamespace(NoSuchKey=KeyError)

    def __init__(self) -> None:
        self.presign_calls: list[dict[str, object]] = []
        self.head_response: dict[str, object] = {}

    def generate_presigned_url(self, operation: str, **arguments: object) -> str:
        self.presign_calls.append({"operation": operation, **arguments})
        return "http://localhost:4566/signed-put"

    def head_object(self, **arguments: object) -> dict[str, object]:
        del arguments
        return self.head_response


@pytest.mark.asyncio
async def test_s3_signed_put_uses_browser_client_and_verifies_metadata() -> None:
    internal = StubS3Client()
    browser = StubS3Client()
    storage = S3ObjectStorage(
        internal,
        bucket="iep-local-contract-fixtures",
        presign_client=browser,
    )
    scope = ApplicantScope(
        company_id="0198a82a-0540-7000-8000-000000000001",
        applicant_id="0198a82a-0540-7000-8000-000000000007",
        invitation_id="0198a82a-0540-7000-8000-000000000009",
    )
    context = TenantContext(
        company_id=scope.company_id,
        actor_type=ActorType.APPLICANT,
        actor_id=scope.applicant_id,
        request_id="0198a82a-0540-7000-8000-000000000005",
        trace_id="trace-0001",
    )
    reference = ObjectRef(
        company_id=scope.company_id,
        object_id="0198a82a-0540-7000-8000-000000000006",
        applicant_scope=scope,
    )
    content = b"browser upload"
    digest = hashlib.sha256(content).hexdigest()
    expires_at = datetime.now(UTC) + timedelta(minutes=15)

    intent = await storage.authorize_upload(
        context,
        reference,
        media_type="application/pdf",
        content_hash=digest,
        byte_size=len(content),
        expires_at=expires_at,
    )
    internal.head_response = {
        "ContentLength": len(content),
        "ContentType": "application/pdf",
        "Metadata": {"sha256": digest},
    }
    receipt = await storage.verify_upload(
        context,
        reference,
        media_type="application/pdf",
        content_hash=digest,
        byte_size=len(content),
    )

    assert intent.url == "http://localhost:4566/signed-put"
    assert intent.required_headers["x-amz-meta-sha256"] == digest
    assert browser.presign_calls[0]["operation"] == "put_object"
    assert receipt.byte_size == len(content)
