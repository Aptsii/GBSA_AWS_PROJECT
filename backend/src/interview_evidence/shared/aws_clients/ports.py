"""Tenant-first AWS service ports and deterministic in-memory fakes."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from interview_evidence.shared._validation import (
    FrozenValue,
    freeze_operational_payload,
    plain_operational_payload,
    safe_code,
)
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import OpaqueId
from interview_evidence.shared.tenant import (
    ActorType,
    ApplicantScope,
    TenantContext,
    TenantScopeViolation,
    ensure_applicant_scope,
    ensure_company_scope,
)

_MEDIA_TYPE = re.compile(r"^[a-z0-9][a-z0-9!#$&^_.+-]{0,63}/[a-z0-9][a-z0-9!#$&^_.+-]{0,63}$")


@dataclass(frozen=True, slots=True, repr=False)
class ProtectedText:
    _value: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self._value, str):
            raise TypeError("protected text must be a string")

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "ProtectedText([REDACTED])"

    __str__ = __repr__


@dataclass(frozen=True, slots=True, repr=False)
class ProtectedBytes:
    _value: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self._value, bytes):
            raise TypeError("protected bytes must be bytes")

    def reveal(self) -> bytes:
        return self._value

    def __repr__(self) -> str:
        return "ProtectedBytes([REDACTED])"

    __str__ = __repr__


@dataclass(frozen=True, slots=True)
class ObjectRef:
    company_id: OpaqueId
    object_id: OpaqueId
    applicant_scope: ApplicantScope | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "company_id", OpaqueId(self.company_id))
        object.__setattr__(self, "object_id", OpaqueId(self.object_id))
        if self.applicant_scope is not None and self.applicant_scope.company_id != self.company_id:
            raise ValueError("object applicant scope must belong to the object's company")


@dataclass(frozen=True, slots=True)
class ObjectReceipt:
    reference: ObjectRef
    content_hash: str
    byte_size: int
    media_type: str


@dataclass(frozen=True, slots=True)
class DeletionReceipt:
    target_id: OpaqueId
    verified_absent: bool


def _ensure_object_access(context: TenantContext, reference: ObjectRef) -> None:
    checked = ensure_company_scope(context, reference.company_id)
    if reference.applicant_scope is not None:
        ensure_applicant_scope(checked, reference.applicant_scope)
    elif checked.actor_type is ActorType.APPLICANT:
        raise TenantScopeViolation


@runtime_checkable
class ObjectStoragePort(Protocol):
    async def put(
        self,
        context: TenantContext,
        reference: ObjectRef,
        content: ProtectedBytes,
        *,
        media_type: str,
    ) -> ObjectReceipt: ...

    async def get(self, context: TenantContext, reference: ObjectRef) -> ProtectedBytes: ...

    async def delete(self, context: TenantContext, reference: ObjectRef) -> DeletionReceipt: ...


class FakeObjectStorage:
    __slots__ = ("_objects", "_receipts")

    def __init__(self) -> None:
        self._objects: dict[tuple[OpaqueId, OpaqueId], ProtectedBytes] = {}
        self._receipts: dict[tuple[OpaqueId, OpaqueId], ObjectReceipt] = {}

    async def put(
        self,
        context: TenantContext,
        reference: ObjectRef,
        content: ProtectedBytes,
        *,
        media_type: str,
    ) -> ObjectReceipt:
        _ensure_object_access(context, reference)
        _validate_media_type(media_type)
        raw = content.reveal()
        receipt = ObjectReceipt(
            reference=reference,
            content_hash=hashlib.sha256(raw).hexdigest(),
            byte_size=len(raw),
            media_type=media_type,
        )
        key = (reference.company_id, reference.object_id)
        existing = self._receipts.get(key)
        if existing is not None and existing != receipt:
            raise SafeApplicationError(ErrorCode.CONFLICT)
        self._objects[key] = content
        self._receipts[key] = receipt
        return existing or receipt

    async def get(self, context: TenantContext, reference: ObjectRef) -> ProtectedBytes:
        _ensure_object_access(context, reference)
        try:
            key = (reference.company_id, reference.object_id)
            receipt = self._receipts[key]
            if (
                context.actor_type is ActorType.APPLICANT
                and receipt.reference.applicant_scope != reference.applicant_scope
            ):
                raise TenantScopeViolation
            return self._objects[key]
        except KeyError:
            raise SafeApplicationError(ErrorCode.RESOURCE_NOT_FOUND) from None

    async def delete(self, context: TenantContext, reference: ObjectRef) -> DeletionReceipt:
        _ensure_object_access(context, reference)
        key = (reference.company_id, reference.object_id)
        existing = self._receipts.get(key)
        if (
            existing is not None
            and context.actor_type is ActorType.APPLICANT
            and existing.reference.applicant_scope != reference.applicant_scope
        ):
            raise TenantScopeViolation
        self._objects.pop(key, None)
        self._receipts.pop(key, None)
        return DeletionReceipt(target_id=reference.object_id, verified_absent=True)

    def __repr__(self) -> str:
        return f"FakeObjectStorage(objects={len(self._objects)})"


@dataclass(frozen=True, slots=True)
class QueueMessage:
    company_id: OpaqueId
    event_id: OpaqueId
    idempotency_key: str
    payload: Mapping[str, FrozenValue]

    def __post_init__(self) -> None:
        object.__setattr__(self, "company_id", OpaqueId(self.company_id))
        object.__setattr__(self, "event_id", OpaqueId(self.event_id))
        safe_code(self.idempotency_key, field_name="idempotency_key")
        if not 16 <= len(self.idempotency_key) <= 128:
            raise ValueError("idempotency_key must contain between 16 and 128 characters")
        object.__setattr__(
            self,
            "payload",
            freeze_operational_payload(self.payload, label="queue payload"),
        )


@dataclass(frozen=True, slots=True)
class QueueReceipt:
    message_id: OpaqueId
    duplicate: bool = False


@runtime_checkable
class QueuePort(Protocol):
    async def publish(
        self, context: TenantContext, queue_name: str, message: QueueMessage
    ) -> QueueReceipt: ...


class FakeQueueClient:
    __slots__ = ("_receipts", "_request_digests")

    def __init__(self) -> None:
        self._receipts: dict[tuple[OpaqueId, str, str], QueueReceipt] = {}
        self._request_digests: dict[tuple[OpaqueId, str, str], str] = {}

    @property
    def published_count(self) -> int:
        return len(self._receipts)

    async def publish(
        self, context: TenantContext, queue_name: str, message: QueueMessage
    ) -> QueueReceipt:
        ensure_company_scope(context, message.company_id)
        safe_code(queue_name, field_name="queue_name")
        key = (message.company_id, queue_name, message.idempotency_key)
        digest = _canonical_digest(
            {
                "event_id": str(message.event_id),
                "payload": plain_operational_payload(message.payload),
            }
        )
        existing = self._receipts.get(key)
        if existing is not None:
            if self._request_digests[key] != digest:
                raise SafeApplicationError(ErrorCode.IDEMPOTENCY_CONFLICT)
            return existing
        receipt = QueueReceipt(message_id=message.event_id)
        self._receipts[key] = receipt
        self._request_digests[key] = digest
        return receipt

    def __repr__(self) -> str:
        return f"FakeQueueClient(messages={len(self._receipts)})"


@dataclass(frozen=True, slots=True)
class AIRequest:
    company_id: OpaqueId
    request_id: OpaqueId
    input: ProtectedText
    config_version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "company_id", OpaqueId(self.company_id))
        object.__setattr__(self, "request_id", OpaqueId(self.request_id))
        safe_code(self.config_version, field_name="config_version")


@dataclass(frozen=True, slots=True)
class AIResponse:
    output: ProtectedText
    model_id: str
    config_version: str

    def __post_init__(self) -> None:
        safe_code(self.model_id, field_name="model_id")
        safe_code(self.config_version, field_name="config_version")


@runtime_checkable
class AIModelPort(Protocol):
    async def generate(self, context: TenantContext, request: AIRequest) -> AIResponse: ...


class FakeAIClient:
    __slots__ = ("_responses",)

    def __init__(self, responses: Mapping[str, AIResponse]) -> None:
        self._responses = {str(OpaqueId(key)): response for key, response in responses.items()}

    async def generate(self, context: TenantContext, request: AIRequest) -> AIResponse:
        ensure_company_scope(context, request.company_id)
        try:
            return self._responses[str(request.request_id)]
        except KeyError:
            raise SafeApplicationError(ErrorCode.DEPENDENCY_UNAVAILABLE) from None

    def __repr__(self) -> str:
        return f"FakeAIClient(fixtures={len(self._responses)})"


@dataclass(frozen=True, slots=True)
class SearchDocument:
    company_id: OpaqueId
    scope: ApplicantScope
    document_id: OpaqueId
    text: ProtectedText
    source_locator: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "company_id", OpaqueId(self.company_id))
        object.__setattr__(self, "document_id", OpaqueId(self.document_id))
        if self.scope.company_id != self.company_id:
            raise ValueError("search document scope must belong to its company")
        safe_code(self.source_locator, field_name="source_locator", max_length=256)


@dataclass(frozen=True, slots=True)
class SearchQuery:
    company_id: OpaqueId
    scope: ApplicantScope
    query: ProtectedText
    limit: int = 10

    def __post_init__(self) -> None:
        object.__setattr__(self, "company_id", OpaqueId(self.company_id))
        if self.scope.company_id != self.company_id:
            raise ValueError("search query scope must belong to its company")
        if not 1 <= self.limit <= 100:
            raise ValueError("search limit must be between 1 and 100")


@dataclass(frozen=True, slots=True)
class SearchHit:
    company_id: OpaqueId
    document_id: OpaqueId
    source_locator: str
    score: float


@runtime_checkable
class SearchPort(Protocol):
    async def index(self, context: TenantContext, document: SearchDocument) -> None: ...

    async def search(self, context: TenantContext, query: SearchQuery) -> tuple[SearchHit, ...]: ...

    async def delete(
        self,
        context: TenantContext,
        *,
        scope: ApplicantScope,
        document_id: OpaqueId,
    ) -> DeletionReceipt: ...


class FakeSearchClient:
    __slots__ = ("_documents",)

    def __init__(self) -> None:
        self._documents: dict[tuple[OpaqueId, OpaqueId, OpaqueId, OpaqueId], SearchDocument] = {}

    async def index(self, context: TenantContext, document: SearchDocument) -> None:
        ensure_applicant_scope(context, document.scope)
        key = (
            document.company_id,
            document.scope.applicant_id,
            document.scope.invitation_id,
            document.document_id,
        )
        existing = self._documents.get(key)
        if existing is not None and existing != document:
            raise SafeApplicationError(ErrorCode.CONFLICT)
        self._documents[key] = document

    async def search(self, context: TenantContext, query: SearchQuery) -> tuple[SearchHit, ...]:
        ensure_applicant_scope(context, query.scope)
        query_terms = set(query.query.reveal().casefold().split())
        hits: list[SearchHit] = []
        for (company_id, applicant_id, invitation_id, _), document in self._documents.items():
            if (
                company_id != query.company_id
                or applicant_id != query.scope.applicant_id
                or invitation_id != query.scope.invitation_id
            ):
                continue
            document_terms = set(document.text.reveal().casefold().split())
            overlap = len(query_terms & document_terms)
            if overlap == 0:
                continue
            score = overlap / math.sqrt(max(1, len(query_terms) * len(document_terms)))
            hits.append(
                SearchHit(
                    company_id=company_id,
                    document_id=document.document_id,
                    source_locator=document.source_locator,
                    score=score,
                )
            )
        hits.sort(key=lambda hit: (-hit.score, str(hit.document_id)))
        return tuple(hits[: query.limit])

    async def delete(
        self,
        context: TenantContext,
        *,
        scope: ApplicantScope,
        document_id: OpaqueId,
    ) -> DeletionReceipt:
        checked_document_id = OpaqueId(document_id)
        ensure_applicant_scope(context, scope)
        matching = [
            key
            for key in self._documents
            if key[0] == scope.company_id
            and key[1] == scope.applicant_id
            and key[2] == scope.invitation_id
            and key[3] == checked_document_id
        ]
        for key in matching:
            del self._documents[key]
        return DeletionReceipt(target_id=checked_document_id, verified_absent=True)

    def __repr__(self) -> str:
        return f"FakeSearchClient(documents={len(self._documents)})"


@dataclass(frozen=True, slots=True)
class TranscriptionRequest:
    company_id: OpaqueId
    request_id: OpaqueId
    audio: ProtectedBytes
    config_version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "company_id", OpaqueId(self.company_id))
        object.__setattr__(self, "request_id", OpaqueId(self.request_id))
        safe_code(self.config_version, field_name="config_version")


@dataclass(frozen=True, slots=True)
class TranscriptionResult:
    text: ProtectedText
    confidence: float
    review_required: bool

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between zero and one")


@dataclass(frozen=True, slots=True)
class SpeechSynthesisRequest:
    company_id: OpaqueId
    request_id: OpaqueId
    text: ProtectedText
    voice_id: str
    config_version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "company_id", OpaqueId(self.company_id))
        object.__setattr__(self, "request_id", OpaqueId(self.request_id))
        safe_code(self.voice_id, field_name="voice_id")
        safe_code(self.config_version, field_name="config_version")


@dataclass(frozen=True, slots=True)
class SpeechSynthesisResult:
    audio: ProtectedBytes
    media_type: str

    def __post_init__(self) -> None:
        _validate_media_type(self.media_type)


@runtime_checkable
class SpeechPort(Protocol):
    async def transcribe(
        self, context: TenantContext, request: TranscriptionRequest
    ) -> TranscriptionResult: ...

    async def synthesize(
        self, context: TenantContext, request: SpeechSynthesisRequest
    ) -> SpeechSynthesisResult: ...


class FakeSpeechClient:
    __slots__ = ("_syntheses", "_transcriptions")

    def __init__(
        self,
        *,
        transcriptions: Mapping[str, TranscriptionResult],
        syntheses: Mapping[str, SpeechSynthesisResult],
    ) -> None:
        self._transcriptions = {
            str(OpaqueId(key)): response for key, response in transcriptions.items()
        }
        self._syntheses = {str(OpaqueId(key)): response for key, response in syntheses.items()}

    async def transcribe(
        self, context: TenantContext, request: TranscriptionRequest
    ) -> TranscriptionResult:
        ensure_company_scope(context, request.company_id)
        try:
            return self._transcriptions[str(request.request_id)]
        except KeyError:
            raise SafeApplicationError(ErrorCode.DEPENDENCY_UNAVAILABLE) from None

    async def synthesize(
        self, context: TenantContext, request: SpeechSynthesisRequest
    ) -> SpeechSynthesisResult:
        ensure_company_scope(context, request.company_id)
        try:
            return self._syntheses[str(request.request_id)]
        except KeyError:
            raise SafeApplicationError(ErrorCode.DEPENDENCY_UNAVAILABLE) from None

    def __repr__(self) -> str:
        return (
            "FakeSpeechClient("
            f"transcriptions={len(self._transcriptions)}, syntheses={len(self._syntheses)})"
        )


@dataclass(frozen=True, slots=True)
class EmailRequest:
    company_id: OpaqueId
    message_id: OpaqueId
    recipient: ProtectedText
    template_id: str
    template_variables: tuple[tuple[str, ProtectedText], ...]
    idempotency_key: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "company_id", OpaqueId(self.company_id))
        object.__setattr__(self, "message_id", OpaqueId(self.message_id))
        safe_code(self.template_id, field_name="template_id")
        safe_code(self.idempotency_key, field_name="idempotency_key")
        if not 16 <= len(self.idempotency_key) <= 128:
            raise ValueError("idempotency_key must contain between 16 and 128 characters")
        for name, value in self.template_variables:
            safe_code(name, field_name="template variable name")
            if not isinstance(value, ProtectedText):
                raise TypeError("template variable values must be protected text")


@dataclass(frozen=True, slots=True)
class EmailReceipt:
    provider_message_id: OpaqueId
    accepted: bool


@runtime_checkable
class EmailPort(Protocol):
    async def send(self, context: TenantContext, request: EmailRequest) -> EmailReceipt: ...


class FakeEmailClient:
    __slots__ = ("_digests", "_receipts")

    def __init__(self) -> None:
        self._digests: dict[tuple[OpaqueId, str], str] = {}
        self._receipts: dict[tuple[OpaqueId, str], EmailReceipt] = {}

    @property
    def sent_count(self) -> int:
        return len(self._receipts)

    async def send(self, context: TenantContext, request: EmailRequest) -> EmailReceipt:
        ensure_company_scope(context, request.company_id)
        key = (request.company_id, request.idempotency_key)
        digest = hashlib.sha256()
        digest.update(request.recipient.reveal().encode())
        digest.update(request.template_id.encode())
        for name, value in request.template_variables:
            digest.update(name.encode())
            digest.update(value.reveal().encode())
        request_digest = digest.hexdigest()
        existing = self._receipts.get(key)
        if existing is not None:
            if self._digests[key] != request_digest:
                raise SafeApplicationError(ErrorCode.IDEMPOTENCY_CONFLICT)
            return existing
        receipt = EmailReceipt(provider_message_id=request.message_id, accepted=True)
        self._digests[key] = request_digest
        self._receipts[key] = receipt
        return receipt

    def __repr__(self) -> str:
        return f"FakeEmailClient(messages={len(self._receipts)})"


def _canonical_digest(value: Mapping[str, object]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_media_type(value: str) -> str:
    if not _MEDIA_TYPE.fullmatch(value):
        raise ValueError("media_type must be a valid lower-case media type")
    return value
