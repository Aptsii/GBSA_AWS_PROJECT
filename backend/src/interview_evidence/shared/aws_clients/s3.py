from __future__ import annotations

import asyncio
from typing import Any

from interview_evidence.shared.aws_clients.ports import (
    DeletionReceipt,
    ObjectReceipt,
    ObjectRef,
    ProtectedBytes,
)
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.tenant import (
    TenantContext,
    ensure_applicant_scope,
    ensure_company_scope,
)


class S3ObjectStorage:
    __slots__ = ("_bucket", "_client")

    def __init__(self, client: Any, *, bucket: str) -> None:
        if not bucket or len(bucket) > 63:
            raise ValueError("object storage bucket name is invalid")
        self._client = client
        self._bucket = bucket

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
            ServerSideEncryption="AES256",
        )
        import hashlib

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
