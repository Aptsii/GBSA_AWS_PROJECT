from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from interview_evidence.shared.aws_clients.ports import (
    AIRequest,
    AIResponse,
    EmailRequest,
    FakeAIClient,
    FakeEmailClient,
    FakeObjectStorage,
    FakeQueueClient,
    FakeSearchClient,
    FakeSpeechClient,
    ObjectRef,
    ProtectedBytes,
    ProtectedText,
    QueueMessage,
    SearchDocument,
    SearchQuery,
    SpeechSynthesisRequest,
    SpeechSynthesisResult,
    TranscriptionRequest,
    TranscriptionResult,
)
from interview_evidence.shared.errors import SafeApplicationError
from interview_evidence.shared.tenant import (
    ActorType,
    ApplicantScope,
    TenantContext,
    TenantScopeViolation,
)

COMPANY_ID = "0198a82a-0540-7000-8000-000000000001"
OTHER_COMPANY_ID = "0198a82a-0540-7000-8000-000000000002"
REQUEST_ID = "0198a82a-0540-7000-8000-000000000005"
OBJECT_ID = "0198a82a-0540-7000-8000-000000000006"
APPLICANT_ID = "0198a82a-0540-7000-8000-000000000007"
OTHER_APPLICANT_ID = "0198a82a-0540-7000-8000-000000000008"
INVITATION_ID = "0198a82a-0540-7000-8000-000000000009"
OTHER_INVITATION_ID = "0198a82a-0540-7000-8000-00000000000a"


def _context(company_id: str = COMPANY_ID) -> TenantContext:
    return TenantContext(
        company_id=company_id,
        actor_type=ActorType.SYSTEM,
        actor_id="0198a82a-0540-7000-8000-000000000003",
        request_id=REQUEST_ID,
        trace_id="trace-0001",
    )


def _applicant_context(applicant_id: str = APPLICANT_ID) -> TenantContext:
    return TenantContext(
        company_id=COMPANY_ID,
        actor_type=ActorType.APPLICANT,
        actor_id=applicant_id,
        request_id=REQUEST_ID,
        trace_id="trace-0001",
    )


def _scope(
    applicant_id: str = APPLICANT_ID,
    invitation_id: str = INVITATION_ID,
) -> ApplicantScope:
    return ApplicantScope(
        company_id=COMPANY_ID,
        applicant_id=applicant_id,
        invitation_id=invitation_id,
    )


@pytest.mark.asyncio
async def test_object_storage_is_tenant_scoped_and_secret_safe() -> None:
    storage = FakeObjectStorage()
    reference = ObjectRef(company_id=COMPANY_ID, object_id=OBJECT_ID)
    protected = ProtectedBytes(b"private applicant document")

    receipt = await storage.put(
        _context(),
        reference,
        protected,
        media_type="application/pdf",
    )

    assert receipt.byte_size == len(protected.reveal())
    assert (await storage.get(_context(), reference)).reveal() == protected.reveal()
    assert b"private applicant document" not in repr(storage).encode()
    with pytest.raises(TenantScopeViolation):
        await storage.get(_context(OTHER_COMPANY_ID), reference)
    assert (await storage.delete(_context(), reference)).verified_absent is True


@pytest.mark.asyncio
async def test_object_storage_authorizes_and_verifies_direct_upload() -> None:
    storage = FakeObjectStorage()
    reference = ObjectRef(
        company_id=COMPANY_ID,
        object_id=OBJECT_ID,
        applicant_scope=_scope(),
    )
    content = ProtectedBytes(b"signed browser upload")
    import hashlib

    digest = hashlib.sha256(content.reveal()).hexdigest()
    expires_at = datetime.now(UTC) + timedelta(minutes=15)

    intent = await storage.authorize_upload(
        _applicant_context(),
        reference,
        media_type="application/pdf",
        content_hash=digest,
        byte_size=len(content.reveal()),
        expires_at=expires_at,
    )
    await storage.put(
        _applicant_context(),
        reference,
        content,
        media_type="application/pdf",
    )
    receipt = await storage.verify_upload(
        _applicant_context(),
        reference,
        media_type="application/pdf",
        content_hash=digest,
        byte_size=len(content.reveal()),
    )

    assert intent.method == "PUT"
    assert intent.expires_at == expires_at
    assert receipt.content_hash == digest
    assert (await storage.delete(_context(), reference)).verified_absent is True


@pytest.mark.asyncio
async def test_applicant_cannot_forge_another_applicants_object_scope() -> None:
    storage = FakeObjectStorage()
    other_reference = ObjectRef(
        company_id=COMPANY_ID,
        object_id=OBJECT_ID,
        applicant_scope=_scope(OTHER_APPLICANT_ID, OTHER_INVITATION_ID),
    )
    await storage.put(
        _context(),
        other_reference,
        ProtectedBytes(b"another applicant document"),
        media_type="application/pdf",
    )

    with pytest.raises(TenantScopeViolation):
        await storage.get(_applicant_context(), other_reference)
    with pytest.raises(TenantScopeViolation):
        await storage.get(
            _applicant_context(),
            ObjectRef(
                company_id=COMPANY_ID,
                object_id=OBJECT_ID,
                applicant_scope=_scope(),
            ),
        )


@pytest.mark.asyncio
async def test_queue_delivery_is_idempotent_and_rejects_sensitive_payloads() -> None:
    queue = FakeQueueClient()
    message = QueueMessage(
        company_id=COMPANY_ID,
        event_id=OBJECT_ID,
        idempotency_key="queue-operation-0001",
        payload={"session_id": REQUEST_ID, "status": "ready"},
    )

    first = await queue.publish(_context(), "interview-events", message)
    duplicate = await queue.publish(_context(), "interview-events", message)

    assert first == duplicate
    assert queue.published_count == 1
    with pytest.raises(ValueError, match="prohibited"):
        QueueMessage(
            company_id=COMPANY_ID,
            event_id=OBJECT_ID,
            idempotency_key="queue-operation-0002",
            payload={"answer_text": "raw answer"},
        )
    with pytest.raises(ValueError, match=r"secret-shaped|token-shaped"):
        QueueMessage(
            company_id=COMPANY_ID,
            event_id=OBJECT_ID,
            idempotency_key="queue-operation-0002",
            payload={"status": "RAWACCESSTOKEN1234567890ABCDEFG"},
        )


@pytest.mark.asyncio
async def test_ai_speech_and_email_fakes_are_deterministic_without_secret_repr() -> None:
    ai_response = AIResponse(
        output=ProtectedText("민감한 생성 결과"),
        model_id="model-v1",
        config_version="prompt-v1",
    )
    ai = FakeAIClient({REQUEST_ID: ai_response})
    ai_request = AIRequest(
        company_id=COMPANY_ID,
        request_id=REQUEST_ID,
        input=ProtectedText("지원자 답변 원문"),
        config_version="prompt-v1",
    )
    assert await ai.generate(_context(), ai_request) == ai_response
    assert "지원자 답변 원문" not in repr(ai_request)

    speech = FakeSpeechClient(
        transcriptions={
            REQUEST_ID: TranscriptionResult(
                text=ProtectedText("음성 인식 원문"),
                confidence=0.91,
                review_required=False,
            )
        },
        syntheses={
            REQUEST_ID: SpeechSynthesisResult(
                audio=ProtectedBytes(b"audio-bytes"),
                media_type="audio/mpeg",
            )
        },
    )
    transcription = await speech.transcribe(
        _context(),
        TranscriptionRequest(
            company_id=COMPANY_ID,
            request_id=REQUEST_ID,
            audio=ProtectedBytes(b"private-audio"),
            config_version="stt-v1",
        ),
    )
    synthesis = await speech.synthesize(
        _context(),
        SpeechSynthesisRequest(
            company_id=COMPANY_ID,
            request_id=REQUEST_ID,
            text=ProtectedText("비공개 질문"),
            voice_id="ko-voice-1",
            config_version="tts-v1",
        ),
    )
    assert transcription.text.reveal() == "음성 인식 원문"
    assert synthesis.audio.reveal() == b"audio-bytes"

    email = FakeEmailClient()
    email_request = EmailRequest(
        company_id=COMPANY_ID,
        message_id=REQUEST_ID,
        recipient=ProtectedText("applicant@example.invalid"),
        template_id="invitation-v1",
        template_variables=(("invitation_link", ProtectedText("https://signed.invalid/secret")),),
        idempotency_key="email-operation-0001",
    )
    assert await email.send(_context(), email_request) == await email.send(
        _context(), email_request
    )
    assert email.sent_count == 1
    assert "applicant@example.invalid" not in repr(email_request)


@pytest.mark.asyncio
async def test_search_fake_applies_tenant_and_applicant_scope_before_ranking() -> None:
    search = FakeSearchClient()
    await search.index(
        _context(),
        SearchDocument(
            company_id=COMPANY_ID,
            scope=_scope(),
            document_id=OBJECT_ID,
            text=ProtectedText("Python FastAPI distributed tracing"),
            source_locator="submission:page:1",
        ),
    )
    await search.index(
        _context(OTHER_COMPANY_ID),
        SearchDocument(
            company_id=OTHER_COMPANY_ID,
            scope=ApplicantScope(
                company_id=OTHER_COMPANY_ID,
                applicant_id=APPLICANT_ID,
                invitation_id=INVITATION_ID,
            ),
            document_id=REQUEST_ID,
            text=ProtectedText("Python FastAPI distributed tracing"),
            source_locator="submission:page:2",
        ),
    )

    hits = await search.search(
        _context(),
        SearchQuery(
            company_id=COMPANY_ID,
            scope=_scope(),
            query=ProtectedText("FastAPI tracing"),
            limit=10,
        ),
    )

    assert [hit.document_id for hit in hits] == [OBJECT_ID]
    assert all(hit.company_id == COMPANY_ID for hit in hits)

    with pytest.raises(TenantScopeViolation):
        await search.search(
            _applicant_context(),
            SearchQuery(
                company_id=COMPANY_ID,
                scope=_scope(OTHER_APPLICANT_ID, OTHER_INVITATION_ID),
                query=ProtectedText("FastAPI tracing"),
            ),
        )


@pytest.mark.asyncio
async def test_missing_fake_fixture_is_a_safe_dependency_error() -> None:
    ai = FakeAIClient({})
    request = AIRequest(
        company_id=COMPANY_ID,
        request_id=REQUEST_ID,
        input=ProtectedText("secret"),
        config_version="prompt-v1",
    )

    with pytest.raises(SafeApplicationError):
        await ai.generate(_context(), request)
