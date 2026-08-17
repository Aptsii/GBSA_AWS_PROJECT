from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import timedelta

from interview_evidence.shared.aws_clients.ports import (
    ObjectRef,
    ObjectStoragePort,
    ProtectedBytes,
)
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import Clock, OpaqueId, UUID7Generator
from interview_evidence.shared.tenant import ApplicantScope, TenantContext, ensure_applicant_scope


@dataclass(slots=True)
class UploadIntentRecord:
    upload_id: OpaqueId
    scope: ApplicantScope
    source_type: str
    filename: str
    media_type: str
    expected_byte_size: int
    expected_sha256: str
    object_ref: ObjectRef
    expires_at: object
    uploaded: bool = False


class SubmissionObjectStorage:
    __slots__ = ("_clock", "_id_generator", "_intents", "_storage")

    def __init__(
        self,
        storage: ObjectStoragePort,
        *,
        clock: Clock,
        id_generator: UUID7Generator,
    ) -> None:
        self._storage = storage
        self._clock = clock
        self._id_generator = id_generator
        self._intents: dict[tuple[OpaqueId, OpaqueId], UploadIntentRecord] = {}

    def create_intent(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        *,
        source_type: str,
        filename: str,
        media_type: str,
        byte_size: int,
        sha256: str,
    ) -> dict[str, object]:
        ensure_applicant_scope(context, scope)
        upload_id = self._id_generator.new()
        object_id = self._id_generator.new()
        expires_at = self._clock.now() + timedelta(minutes=15)
        record = UploadIntentRecord(
            upload_id=upload_id,
            scope=scope,
            source_type=source_type,
            filename=filename,
            media_type=media_type,
            expected_byte_size=byte_size,
            expected_sha256=sha256,
            object_ref=ObjectRef(
                company_id=scope.company_id,
                object_id=object_id,
                applicant_scope=scope,
            ),
            expires_at=expires_at,
        )
        self._intents[(scope.company_id, upload_id)] = record
        return {
            "upload_id": str(upload_id),
            "method": "PUT",
            "url": f"https://uploads.invalid/{upload_id}",
            "required_headers": {
                "content-type": media_type,
                "x-content-sha256": sha256,
            },
            "expires_at": expires_at,
        }

    def intent(
        self, context: TenantContext, scope: ApplicantScope, upload_id: str | OpaqueId
    ) -> UploadIntentRecord:
        ensure_applicant_scope(context, scope)
        checked_id = OpaqueId(upload_id)
        record = self._intents.get((scope.company_id, checked_id))
        if record is None:
            if any(item_id == checked_id for _, item_id in self._intents):
                raise SafeApplicationError(ErrorCode.TENANT_SCOPE_DENIED)
            raise SafeApplicationError(ErrorCode.RESOURCE_NOT_FOUND)
        if record.scope != scope:
            raise SafeApplicationError(ErrorCode.TENANT_SCOPE_DENIED)
        return record

    async def _put(
        self, context: TenantContext, record: UploadIntentRecord, content: ProtectedBytes
    ) -> None:
        await self._storage.put(
            context,
            record.object_ref,
            content,
            media_type=record.media_type,
        )

    def accept_upload(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        *,
        upload_id: str | OpaqueId,
        content: ProtectedBytes,
        media_type: str,
    ) -> None:
        import asyncio

        record = self.intent(context, scope, upload_id)
        raw = content.reveal()
        if self._clock.now() > record.expires_at:
            raise SafeApplicationError(ErrorCode.AUTHENTICATION_EXPIRED)
        if media_type != record.media_type:
            raise SafeApplicationError(ErrorCode.INVALID_REQUEST)
        if len(raw) != record.expected_byte_size:
            raise SafeApplicationError(ErrorCode.INVALID_REQUEST)
        if hashlib.sha256(raw).hexdigest() != record.expected_sha256:
            raise SafeApplicationError(ErrorCode.INVALID_REQUEST)
        asyncio.run(self._put(context, record, content))
        record.uploaded = True

    async def _get(self, context: TenantContext, record: UploadIntentRecord) -> ProtectedBytes:
        return await self._storage.get(context, record.object_ref)

    def read_upload(
        self, context: TenantContext, scope: ApplicantScope, upload_id: str | OpaqueId
    ) -> ProtectedBytes:
        import asyncio

        record = self.intent(context, scope, upload_id)
        if not record.uploaded:
            raise SafeApplicationError(ErrorCode.CONFLICT)
        return asyncio.run(self._get(context, record))

    def upload_ids(self, context: TenantContext, scope: ApplicantScope) -> tuple[OpaqueId, ...]:
        ensure_applicant_scope(context, scope)
        return tuple(
            upload_id
            for (company_id, upload_id), record in self._intents.items()
            if company_id == scope.company_id and record.scope == scope
        )

    async def _delete(self, context: TenantContext, record: UploadIntentRecord) -> bool:
        receipt = await self._storage.delete(context, record.object_ref)
        return receipt.verified_absent

    def delete_upload(
        self, context: TenantContext, scope: ApplicantScope, upload_id: str | OpaqueId
    ) -> bool:
        import asyncio

        record = self.intent(context, scope, upload_id)
        verified = asyncio.run(self._delete(context, record))
        if verified:
            self._intents.pop((scope.company_id, record.upload_id), None)
        return verified
