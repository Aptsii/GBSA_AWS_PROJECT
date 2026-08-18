from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from typing import Any

from interview_evidence.shared.aws_clients.ports import (
    DeletionReceipt,
    ObjectReceipt,
    ObjectRef,
    ProtectedBytes,
    SignedUploadIntent,
)
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.tenant import (
    TenantContext,
    ensure_applicant_scope,
    ensure_company_scope,
)


class S3ObjectStorage:
    __slots__ = ("_bucket", "_client", "_presign_client")

    def __init__(self, client: Any, *, bucket: str, presign_client: Any | None = None) -> None:
        if not bucket or len(bucket) > 63:
            raise ValueError("object storage bucket name is invalid")
        self._client = client
        self._presign_client = presign_client or client
        self._bucket = bucket

    async def authorize_upload(
        self,
        context: TenantContext,
        reference: ObjectRef,
        *,
        media_type: str,
        content_hash: str,
        byte_size: int,
        expires_at: datetime,
    ) -> SignedUploadIntent:
        self._authorize(context, reference)
        if byte_size < 1:
            raise ValueError("object byte size must be positive")
        if len(content_hash) != 64:
            raise ValueError("object content hash is invalid")
        expires_in = max(1, int((expires_at - datetime.now(UTC)).total_seconds()))
        parameters = {
            "Bucket": self._bucket,
            "Key": self._key(reference),
            "ContentType": media_type,
            "Metadata": {"sha256": content_hash},
            "ServerSideEncryption": "AES256",
        }
        url = await asyncio.to_thread(
            self._presign_client.generate_presigned_url,
            "put_object",
            Params=parameters,
            ExpiresIn=expires_in,
        )
        return SignedUploadIntent(
            method="PUT",
            url=url,
            required_headers={
                "content-type": media_type,
                "x-amz-meta-sha256": content_hash,
                "x-amz-server-side-encryption": "AES256",
            },
            expires_at=expires_at,
        )

    async def verify_upload(
        self,
        context: TenantContext,
        reference: ObjectRef,
        *,
        media_type: str,
        content_hash: str,
        byte_size: int,
    ) -> ObjectReceipt:
        self._authorize(context, reference)
        try:
            response = await asyncio.to_thread(
                self._client.head_object,
                Bucket=self._bucket,
                Key=self._key(reference),
            )
        except Exception as error:
            if type(error).__name__ != "ClientError":
                raise
            raise SafeApplicationError(ErrorCode.RESOURCE_NOT_FOUND) from error
        metadata = response.get("Metadata") or {}
        actual = (
            response.get("ContentType"),
            metadata.get("sha256"),
            response.get("ContentLength"),
        )
        if actual != (media_type, content_hash, byte_size):
            raise SafeApplicationError(ErrorCode.CONFLICT)
        return ObjectReceipt(
            reference=reference,
            content_hash=content_hash,
            byte_size=byte_size,
            media_type=media_type,
        )

    async def put(
        self,
        context: TenantContext,
        reference: ObjectRef,
        content: ProtectedBytes,
        *,
        media_type: str,
    ) -> ObjectReceipt:
        self._authorize(context, reference)
        raw = content.reveal()
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket,
            Key=self._key(reference),
            Body=raw,
            ContentType=media_type,
            Metadata={"sha256": hashlib.sha256(raw).hexdigest()},
            ServerSideEncryption="AES256",
        )
        return ObjectReceipt(
            reference=reference,
            content_hash=hashlib.sha256(raw).hexdigest(),
            byte_size=len(raw),
            media_type=media_type,
        )

    async def get(self, context: TenantContext, reference: ObjectRef) -> ProtectedBytes:
        self._authorize(context, reference)
        try:
            response = await asyncio.to_thread(
                self._client.get_object,
                Bucket=self._bucket,
                Key=self._key(reference),
            )
        except self._client.exceptions.NoSuchKey:
            raise SafeApplicationError(ErrorCode.RESOURCE_NOT_FOUND) from None
        return ProtectedBytes(await asyncio.to_thread(response["Body"].read))

    async def delete(self, context: TenantContext, reference: ObjectRef) -> DeletionReceipt:
        self._authorize(context, reference)
        await asyncio.to_thread(
            self._client.delete_object,
            Bucket=self._bucket,
            Key=self._key(reference),
        )
        return DeletionReceipt(target_id=reference.object_id, verified_absent=True)

    @staticmethod
    def _authorize(context: TenantContext, reference: ObjectRef) -> None:
        ensure_company_scope(context, reference.company_id)
        if reference.applicant_scope is not None:
            ensure_applicant_scope(context, reference.applicant_scope)

    @staticmethod
    def _key(reference: ObjectRef) -> str:
        if reference.applicant_scope is None:
            return f"company/{reference.company_id}/{reference.object_id}"
        scope = reference.applicant_scope
        return (
            f"applicant/{scope.company_id}/{scope.applicant_id}/"
            f"{scope.invitation_id}/{reference.object_id}"
        )
