from __future__ import annotations

from datetime import UTC, datetime, timedelta

from interview_evidence.company_management.adapters.applicant_session import (
    ApplicantSessionAdapter,
)
from interview_evidence.company_management.application.applicant_access_service import (
    ApplicantAccessService,
    consent_authorization_snapshot,
)
from interview_evidence.company_management.application.company_service import CompanyService
from interview_evidence.company_management.application.criteria_service import (
    CriteriaService,
    criterion_version_snapshot,
)
from interview_evidence.company_management.application.deletion_targets import (
    CompanyDeletionTargets,
)
from interview_evidence.company_management.application.hiring_service import (
    HiringService,
    campaign_snapshot,
)
from interview_evidence.company_management.domain.applicant_access import (
    ConsentPurpose,
    ProcessingAuthorization,
)
from interview_evidence.company_management.repositories.postgres import (
    CompanyManagementRepository,
    InvitationRow,
    register_company_models,
)
from interview_evidence.shared.database import metadata
from interview_evidence.shared.ids import FixedClock, OpaqueId, UUID7Generator
from interview_evidence.shared.tenant import ActorType, TenantContext
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

NOW = datetime(2026, 8, 17, 9, 0, tzinfo=UTC)
COMPANY_ID = OpaqueId("0198b6c5-8800-7000-8000-000000000001")
COMPANY_USER_ID = OpaqueId("0198b6c5-8800-7000-8000-000000000002")


def _company_context(ids: UUID7Generator) -> TenantContext:
    return TenantContext(
        company_id=COMPANY_ID,
        actor_type=ActorType.COMPANY_USER,
        actor_id=COMPANY_USER_ID,
        request_id=ids.new(),
        trace_id="lane-a-quickstart",
    )


def test_lane_a_isolated_company_to_consent_journey() -> None:
    register_company_models()
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    try:
        clock = FixedClock(NOW)
        ids = UUID7Generator(clock)
        context = _company_context(ids)
        repository = CompanyManagementRepository(session)
        company_service = CompanyService(repository, clock=clock, id_generator=ids)
        criteria_service = CriteriaService(repository, clock=clock, id_generator=ids)
        hiring_service = HiringService(repository, clock=clock, id_generator=ids)
        access_service = ApplicantAccessService(repository, clock=clock, id_generator=ids)

        position = company_service.create_position(
            context,
            title="백엔드 엔지니어",
            description="테넌트 경계를 지키는 서비스를 설계합니다.",
        )
        draft = criteria_service.create_version(
            context,
            position_id=position.position_id,
            criteria=[
                {
                    "code": "BACKEND_DESIGN",
                    "name": "백엔드 설계",
                    "description": "경계와 트레이드오프를 설명합니다.",
                    "weight": 1,
                    "good_evidence": {"signals": ["tradeoff"]},
                    "weak_evidence": {"signals": ["generic"]},
                    "abstain_guidance": "답변 근거가 부족하면 유보합니다.",
                    "common_questions": ["최근 설계 판단을 설명해 주세요."],
                    "required": True,
                }
            ],
            prohibited_topics=["가족관계"],
            interview_duration_minutes=40,
            persona_definition={"name": "하루", "tone": "professional"},
        )
        version = criteria_service.publish_version(
            context,
            version_id=draft.competency_model_version_id,
            expected_version=1,
        )
        campaign = hiring_service.create_campaign(
            context,
            position_id=position.position_id,
            competency_model_version_id=version.competency_model_version_id,
            name="2026 백엔드 채용",
            candidate_instructions="동의 내용을 확인한 뒤 진행해 주세요.",
        )
        campaign = hiring_service.publish_campaign(
            context,
            campaign_id=campaign.campaign_id,
            expected_version=1,
        )
        invitation = hiring_service.issue_invitations(
            context,
            campaign_id=campaign.campaign_id,
            applicants=[{"email": "candidate@example.com", "display_name": "지원자"}],
            expires_at=NOW + timedelta(days=7),
        )[0]
        raw_token = hiring_service.get_test_delivery_token(invitation.invitation_id)

        persisted_token_hash = session.scalar(
            select(InvitationRow.token_hash).where(
                InvitationRow.invitation_id == str(invitation.invitation_id)
            )
        )
        assert persisted_token_hash is not None
        assert raw_token not in persisted_token_hash

        sessions = ApplicantSessionAdapter(
            repository,
            clock=clock,
            id_generator=ids,
        )
        _, applicant = sessions.exchange(raw_token)
        applicant_context = applicant.to_tenant_context(
            request_id=str(ids.new()),
            trace_id="lane-a-applicant",
        )
        identity = access_service.verify_identity(
            applicant_context,
            applicant,
            display_name="지원자",
            verification_value="email-link-proof",
            idempotency_key="quickstart-identity-0001",
        )
        consent = access_service.record_consent(
            applicant_context,
            applicant,
            policy_version="consent-v1",
            accepted_purposes=[purpose.value for purpose in ConsentPurpose],
            consent_content_digest="a" * 64,
            idempotency_key="quickstart-consent-0001",
        )
        consented_invitation = repository.get_invitation(
            applicant_context, invitation.invitation_id
        )
        ProcessingAuthorization.require(
            invitation=consented_invitation,
            consent=consent,
            purpose=ConsentPurpose.AI_ASSESSMENT,
            now=NOW,
        )

        assert identity["state"] == "identity_verified"
        assert criterion_version_snapshot(version)["status"] == "published"
        assert campaign_snapshot(
            campaign,
            prohibited_topics=version.prohibited_topics,
            interview_duration_minutes=version.interview_duration_minutes,
            persona_definition=version.persona_definition,
        )["competency_model_version_id"] == str(version.competency_model_version_id)
        assert consent_authorization_snapshot(consent)["authorized"] is True

        targets = CompanyDeletionTargets(
            repository,
            clock=clock,
            id_generator=ids,
        ).enumerate_invitation(context, invitation.invitation_id)
        target_items = targets["targets"]
        assert isinstance(target_items, list)
        target_types = {
            str(target["target_type"]) for target in target_items if isinstance(target, dict)
        }
        assert target_types >= {
            "invitation",
            "applicant",
            "consent_record",
        }
    finally:
        session.close()
        metadata.drop_all(engine)
        engine.dispose()
