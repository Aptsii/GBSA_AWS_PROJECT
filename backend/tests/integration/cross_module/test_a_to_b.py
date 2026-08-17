from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from interview_evidence.company_management.adapters.applicant_session import (
    ApplicantSessionAdapter,
)
from interview_evidence.company_management.application.applicant_access_service import (
    ApplicantAccessService,
    consent_authorization_snapshot,
)
from interview_evidence.company_management.application.company_service import CompanyService
from interview_evidence.company_management.application.criteria_service import CriteriaService
from interview_evidence.company_management.application.hiring_service import HiringService
from interview_evidence.company_management.domain.applicant_access import ConsentPurpose
from interview_evidence.company_management.repositories.postgres import (
    CompanyManagementRepository,
    register_company_models,
)
from interview_evidence.shared.database import metadata
from interview_evidence.shared.ids import FixedClock, OpaqueId, UUID7Generator
from interview_evidence.shared.tenant import ActorType, ApplicantScope, TenantContext
from interview_evidence.submission_analysis.application.authorization import (
    SubmissionAuthorizationGate,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

NOW = datetime(2026, 8, 17, 9, 0, tzinfo=UTC)
COMPANY_ID = OpaqueId("0198b6c5-8800-7000-8000-000000000101")
COMPANY_USER_ID = OpaqueId("0198b6c5-8800-7000-8000-000000000102")


@dataclass(slots=True)
class _LiveCompanyAuthorizationContracts:
    repository: CompanyManagementRepository
    now: datetime

    def authorize_invitation(
        self, context: TenantContext, **arguments: object
    ) -> dict[str, object]:
        invitation = self.repository.get_invitation(context, str(arguments["invitation_id"]))
        required_state = str(arguments["required_state"])
        authorized = invitation.state.value == required_state and self.now < invitation.expires_at
        return {
            "company_id": str(invitation.company_id),
            "invitation_id": str(invitation.invitation_id),
            "applicant_id": str(invitation.applicant_id),
            "campaign_id": str(invitation.campaign_id),
            "state": invitation.state.value,
            "expires_at": invitation.expires_at.isoformat().replace("+00:00", "Z"),
            "authorized": authorized,
            "reason_code": None if authorized else "invitation_not_authorized",
        }

    def get_consent_authorization(
        self, context: TenantContext, **arguments: object
    ) -> dict[str, object]:
        consent = self.repository.get_latest_consent(context, str(arguments["invitation_id"]))
        assert consent is not None
        snapshot = consent_authorization_snapshot(consent)
        required_purposes = set(arguments["required_purposes"])
        purpose_codes = snapshot["purpose_codes"]
        assert isinstance(purpose_codes, list)
        snapshot["authorized"] = snapshot["authorized"] is True and required_purposes <= set(
            purpose_codes
        )
        return snapshot


def test_lane_a_invitation_and_consent_authorize_lane_b_submission() -> None:
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
        company_context = TenantContext(
            company_id=COMPANY_ID,
            actor_type=ActorType.COMPANY_USER,
            actor_id=COMPANY_USER_ID,
            request_id=ids.new(),
            trace_id="integration-a-to-b",
        )
        repository = CompanyManagementRepository(session)
        position = CompanyService(repository, clock=clock, id_generator=ids).create_position(
            company_context,
            title="백엔드 엔지니어",
            description="제출 자료를 기반으로 면접합니다.",
        )
        criteria_service = CriteriaService(repository, clock=clock, id_generator=ids)
        draft = criteria_service.create_version(
            company_context,
            position_id=position.position_id,
            criteria=[
                {
                    "code": "SYSTEM_DESIGN",
                    "name": "시스템 설계",
                    "description": "설계 판단을 설명합니다.",
                    "weight": 1,
                    "good_evidence": {"signals": ["tradeoff"]},
                    "weak_evidence": {"signals": ["generic"]},
                    "abstain_guidance": "근거가 부족하면 유보합니다.",
                    "common_questions": ["설계 판단을 설명해 주세요."],
                    "required": True,
                }
            ],
            prohibited_topics=["가족관계"],
            interview_duration_minutes=30,
            persona_definition={"name": "하루"},
        )
        criteria = criteria_service.publish_version(
            company_context,
            version_id=draft.competency_model_version_id,
            expected_version=1,
        )
        hiring = HiringService(repository, clock=clock, id_generator=ids)
        campaign = hiring.create_campaign(
            company_context,
            position_id=position.position_id,
            competency_model_version_id=criteria.competency_model_version_id,
            name="통합 채용",
            candidate_instructions="동의 후 제출해 주세요.",
        )
        campaign = hiring.publish_campaign(
            company_context,
            campaign_id=campaign.campaign_id,
            expected_version=1,
        )
        invitation = hiring.issue_invitations(
            company_context,
            campaign_id=campaign.campaign_id,
            applicants=[{"email": "candidate@example.com", "display_name": "지원자"}],
            expires_at=NOW + timedelta(days=7),
        )[0]
        _, principal = ApplicantSessionAdapter(
            repository, clock=clock, id_generator=ids
        ).exchange(hiring.get_test_delivery_token(invitation.invitation_id))
        applicant_context = principal.to_tenant_context(
            request_id=str(ids.new()), trace_id="integration-a-to-b-applicant"
        )
        access = ApplicantAccessService(repository, clock=clock, id_generator=ids)
        access.verify_identity(
            applicant_context,
            principal,
            display_name="지원자",
            verification_value="email-link-proof",
            idempotency_key="a-to-b-identity",
        )
        consent = access.record_consent(
            applicant_context,
            principal,
            policy_version="privacy-v1",
            accepted_purposes=[purpose.value for purpose in ConsentPurpose],
            consent_content_digest="a" * 64,
            idempotency_key="a-to-b-consent",
        )
        scope = ApplicantScope(
            company_id=principal.company_id,
            applicant_id=principal.applicant_id,
            invitation_id=principal.invitation_id,
        )

        authorization = SubmissionAuthorizationGate(
            _LiveCompanyAuthorizationContracts(repository, NOW)
        ).authorize(applicant_context, scope)

        assert authorization.campaign_id == campaign.campaign_id
        assert authorization.consent_record_id == consent.consent_record_id
        assert authorization.retention_days == consent.retention_days
        assert authorization.policy_version == "privacy-v1"
    finally:
        session.close()
        metadata.drop_all(engine)
        engine.dispose()
