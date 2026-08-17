from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    delete,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from interview_evidence.company_management.domain.applicant_access import (
    ApplicantProfile,
    ConsentPurpose,
    ConsentRecord,
    VerificationMethod,
)
from interview_evidence.company_management.domain.company import (
    Company,
    CompanyUser,
    Position,
    PositionStatus,
)
from interview_evidence.company_management.domain.criteria import (
    CompetencyModelStatus,
    CompetencyModelVersion,
    EvaluationCriterion,
)
from interview_evidence.company_management.domain.hiring import (
    Campaign,
    CampaignStatus,
    Invitation,
    InvitationState,
)
from interview_evidence.shared.database import Base
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import OpaqueId
from interview_evidence.shared.tenant import (
    TenantContext,
    TenantScopeViolation,
    ensure_company_scope,
    require_tenant_context,
)


class CompanyRow(Base):
    __tablename__ = "companies"

    company_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CompanyUserRow(Base):
    __tablename__ = "company_users"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "identity_subject",
            name="uq_company_users_company_identity_subject",
        ),
        UniqueConstraint("company_id", "email", name="uq_company_users_company_email"),
    )

    company_user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    identity_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    roles: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)


class PositionRow(Base):
    __tablename__ = "positions"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "position_id",
            name="uq_positions_company_position",
        ),
    )

    position_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class CompetencyModelVersionRow(Base):
    __tablename__ = "competency_model_versions"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "position_id",
            "version_number",
            name="uq_competency_versions_position_number",
        ),
        UniqueConstraint(
            "company_id",
            "competency_model_version_id",
            name="uq_competency_versions_company_version",
        ),
        ForeignKeyConstraint(
            ["company_id", "position_id"],
            ["positions.company_id", "positions.position_id"],
            name="fk_competency_versions_position",
        ),
    )

    competency_model_version_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    position_id: Mapped[str] = mapped_column(String(36), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    prohibited_topics: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    interview_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    persona_definition: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class EvaluationCriterionRow(Base):
    __tablename__ = "evaluation_criteria"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "competency_model_version_id",
            "code",
            name="uq_evaluation_criteria_version_code",
        ),
        ForeignKeyConstraint(
            ["company_id", "competency_model_version_id"],
            [
                "competency_model_versions.company_id",
                "competency_model_versions.competency_model_version_id",
            ],
            name="fk_evaluation_criteria_version",
        ),
    )

    criterion_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    competency_model_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    good_evidence: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    weak_evidence: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    abstain_guidance: Mapped[str] = mapped_column(Text, nullable=False)
    common_questions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False)


class CampaignRow(Base):
    __tablename__ = "campaigns"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "campaign_id",
            name="uq_campaigns_company_campaign",
        ),
        ForeignKeyConstraint(
            ["company_id", "position_id"],
            ["positions.company_id", "positions.position_id"],
            name="fk_campaigns_position",
        ),
        ForeignKeyConstraint(
            ["company_id", "competency_model_version_id"],
            [
                "competency_model_versions.company_id",
                "competency_model_versions.competency_model_version_id",
            ],
            name="fk_campaigns_competency_version",
        ),
    )

    campaign_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    position_id: Mapped[str] = mapped_column(String(36), nullable=False)
    competency_model_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    candidate_instructions: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    invitations_issued: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ApplicantProfileRow(Base):
    __tablename__ = "applicant_profiles"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "invitation_id",
            name="uq_applicant_profiles_company_invitation",
        ),
        UniqueConstraint(
            "company_id",
            "applicant_id",
            name="uq_applicant_profiles_company_applicant",
        ),
    )

    applicant_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    invitation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    verification_method: Mapped[str] = mapped_column(String(32), nullable=False)
    technology_tags: Mapped[list[str]] = mapped_column(JSON, nullable=False)


class InvitationRow(Base):
    __tablename__ = "invitations"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "invitation_id",
            name="uq_invitations_company_invitation",
        ),
        UniqueConstraint("token_hash", name="uq_invitations_token_hash"),
        ForeignKeyConstraint(
            ["company_id", "campaign_id"],
            ["campaigns.company_id", "campaigns.campaign_id"],
            name="fk_invitations_campaign",
        ),
        Index("ix_invitations_company_campaign", "company_id", "campaign_id"),
    )

    invitation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), nullable=False)
    applicant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    applicant_email: Mapped[str] = mapped_column(String(320), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    token_exchanged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    identity_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_transitions: Mapped[list[list[str]]] = mapped_column(JSON, nullable=False)


class ConsentRecordRow(Base):
    __tablename__ = "consent_records"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "consent_record_id",
            name="uq_consent_records_company_consent",
        ),
    )

    consent_record_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    invitation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    applicant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    purposes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)


def register_company_models() -> None:
    """Import-side registration hook used by tests and migration checks."""


class CompanyManagementRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _scope(context: TenantContext | None, company_id: str | OpaqueId) -> TenantContext:
        return ensure_company_scope(require_tenant_context(context), company_id)

    def add_company(self, context: TenantContext, company: Company) -> Company:
        self._scope(context, company.company_id)
        self.session.merge(
            CompanyRow(
                company_id=str(company.company_id),
                name=company.name,
                status=company.status.value,
                created_at=company.created_at,
            )
        )
        self.session.flush()
        return company

    def add_company_user(self, context: TenantContext, user: CompanyUser) -> CompanyUser:
        self._scope(context, user.company_id)
        self.session.merge(
            CompanyUserRow(
                company_user_id=str(user.company_user_id),
                company_id=str(user.company_id),
                identity_subject=user.identity_subject,
                email=user.email,
                roles=sorted(user.roles),
                status=user.status.value,
            )
        )
        self.session.flush()
        return user

    def add_position(self, context: TenantContext, position: Position) -> Position:
        self._scope(context, position.company_id)
        self.session.merge(_position_row(position))
        self.session.flush()
        return position

    def get_position(self, context: TenantContext, position_id: str | OpaqueId) -> Position:
        row = self.session.get(PositionRow, str(OpaqueId(position_id)))
        if row is None:
            raise SafeApplicationError(ErrorCode.RESOURCE_NOT_FOUND)
        self._scope(context, row.company_id)
        return _position(row)

    def list_positions(self, context: TenantContext) -> tuple[Position, ...]:
        checked = require_tenant_context(context)
        rows = self.session.scalars(
            select(PositionRow)
            .where(PositionRow.company_id == str(checked.company_id))
            .order_by(PositionRow.created_at, PositionRow.position_id)
        ).all()
        return tuple(_position(row) for row in rows)

    def add_competency_model_version(
        self,
        context: TenantContext,
        version: CompetencyModelVersion,
    ) -> CompetencyModelVersion:
        self._scope(context, version.company_id)
        self.session.merge(_version_row(version))
        self.session.execute(
            delete(EvaluationCriterionRow).where(
                EvaluationCriterionRow.company_id == str(version.company_id),
                EvaluationCriterionRow.competency_model_version_id
                == str(version.competency_model_version_id),
            )
        )
        for criterion in version.criteria:
            self.session.add(_criterion_row(criterion))
        self.session.flush()
        return version

    def get_competency_model_version(
        self,
        context: TenantContext,
        version_id: str | OpaqueId,
    ) -> CompetencyModelVersion:
        row = self.session.get(CompetencyModelVersionRow, str(OpaqueId(version_id)))
        if row is None:
            raise SafeApplicationError(ErrorCode.RESOURCE_NOT_FOUND)
        self._scope(context, row.company_id)
        criteria = self.session.scalars(
            select(EvaluationCriterionRow)
            .where(
                EvaluationCriterionRow.company_id == row.company_id,
                EvaluationCriterionRow.competency_model_version_id
                == row.competency_model_version_id,
            )
            .order_by(EvaluationCriterionRow.code)
        ).all()
        return _version(row, criteria)

    def next_competency_version_number(
        self,
        context: TenantContext,
        position_id: str | OpaqueId,
    ) -> int:
        position = self.get_position(context, position_id)
        rows = self.session.scalars(
            select(CompetencyModelVersionRow.version_number).where(
                CompetencyModelVersionRow.company_id == str(position.company_id),
                CompetencyModelVersionRow.position_id == str(position.position_id),
            )
        ).all()
        return max(rows, default=0) + 1

    def add_campaign(self, context: TenantContext, campaign: Campaign) -> Campaign:
        self._scope(context, campaign.company_id)
        self.session.merge(_campaign_row(campaign))
        self.session.flush()
        return campaign

    def get_campaign(self, context: TenantContext, campaign_id: str | OpaqueId) -> Campaign:
        row = self.session.get(CampaignRow, str(OpaqueId(campaign_id)))
        if row is None:
            raise SafeApplicationError(ErrorCode.RESOURCE_NOT_FOUND)
        self._scope(context, row.company_id)
        return _campaign(row)

    def add_invitation(self, context: TenantContext, invitation: Invitation) -> Invitation:
        self._scope(context, invitation.company_id)
        self.session.merge(_invitation_row(invitation))
        self.session.flush()
        return invitation

    def get_invitation(
        self,
        context: TenantContext,
        invitation_id: str | OpaqueId,
    ) -> Invitation:
        row = self.session.get(InvitationRow, str(OpaqueId(invitation_id)))
        if row is None:
            raise SafeApplicationError(ErrorCode.RESOURCE_NOT_FOUND)
        self._scope(context, row.company_id)
        return _invitation(row)

    def get_invitation_by_token_hash(self, token_hash: str) -> Invitation:
        row = self.session.scalar(
            select(InvitationRow).where(InvitationRow.token_hash == token_hash)
        )
        if row is None:
            raise SafeApplicationError(ErrorCode.AUTHENTICATION_REQUIRED)
        return _invitation(row)

    def list_invitations(
        self,
        context: TenantContext,
        campaign_id: str | OpaqueId,
    ) -> tuple[Invitation, ...]:
        campaign = self.get_campaign(context, campaign_id)
        rows = self.session.scalars(
            select(InvitationRow)
            .where(
                InvitationRow.company_id == str(campaign.company_id),
                InvitationRow.campaign_id == str(campaign.campaign_id),
            )
            .order_by(InvitationRow.invitation_id)
        ).all()
        return tuple(_invitation(row) for row in rows)

    def add_applicant_profile(
        self,
        context: TenantContext,
        profile: ApplicantProfile,
    ) -> ApplicantProfile:
        self._scope(context, profile.company_id)
        self.session.merge(
            ApplicantProfileRow(
                applicant_id=str(profile.applicant_id),
                company_id=str(profile.company_id),
                invitation_id=str(profile.invitation_id),
                display_name=profile.display_name,
                verification_method=profile.verification_method.value,
                technology_tags=list(profile.technology_tags),
            )
        )
        self.session.flush()
        return profile

    def get_applicant_profile(
        self,
        context: TenantContext,
        applicant_id: str | OpaqueId,
    ) -> ApplicantProfile:
        row = self.session.get(ApplicantProfileRow, str(OpaqueId(applicant_id)))
        if row is None:
            raise SafeApplicationError(ErrorCode.RESOURCE_NOT_FOUND)
        self._scope(context, row.company_id)
        return _profile(row)

    def add_consent(self, context: TenantContext, consent: ConsentRecord) -> ConsentRecord:
        self._scope(context, consent.company_id)
        self.session.merge(_consent_row(consent))
        self.session.flush()
        return consent

    def get_latest_consent(
        self,
        context: TenantContext,
        invitation_id: str | OpaqueId,
    ) -> ConsentRecord | None:
        checked = require_tenant_context(context)
        checked_invitation_id = str(OpaqueId(invitation_id))
        rows = self.session.scalars(
            select(ConsentRecordRow)
            .where(ConsentRecordRow.invitation_id == checked_invitation_id)
            .order_by(ConsentRecordRow.accepted_at.desc())
        ).all()
        if not rows:
            return None
        if rows[0].company_id != str(checked.company_id):
            raise TenantScopeViolation
        return _consent(rows[0])

    def deletion_target_ids(
        self,
        context: TenantContext,
        *,
        invitation_id: str | OpaqueId,
    ) -> dict[str, tuple[OpaqueId, ...]]:
        invitation = self.get_invitation(context, invitation_id)
        consent_ids = tuple(
            OpaqueId(value)
            for value in self.session.scalars(
                select(ConsentRecordRow.consent_record_id).where(
                    ConsentRecordRow.company_id == str(invitation.company_id),
                    ConsentRecordRow.invitation_id == str(invitation.invitation_id),
                )
            ).all()
        )
        return {
            "invitation": (invitation.invitation_id,),
            "applicant": (invitation.applicant_id,),
            "consent_record": consent_ids,
        }


def _position_row(position: Position) -> PositionRow:
    return PositionRow(
        position_id=str(position.position_id),
        company_id=str(position.company_id),
        title=position.title,
        description=position.description,
        status=position.status.value,
        created_by=str(position.created_by),
        created_at=position.created_at,
        row_version=position.row_version,
    )


def _position(row: PositionRow) -> Position:
    return Position(
        position_id=OpaqueId(row.position_id),
        company_id=OpaqueId(row.company_id),
        title=row.title,
        description=row.description,
        status=PositionStatus(row.status),
        created_by=OpaqueId(row.created_by),
        created_at=_database_instant(row.created_at),
        row_version=row.row_version,
    )


def _version_row(version: CompetencyModelVersion) -> CompetencyModelVersionRow:
    return CompetencyModelVersionRow(
        competency_model_version_id=str(version.competency_model_version_id),
        company_id=str(version.company_id),
        position_id=str(version.position_id),
        version_number=version.version_number,
        status=version.status.value,
        prohibited_topics=list(version.prohibited_topics),
        interview_duration_minutes=version.interview_duration_minutes,
        persona_definition=dict(version.persona_definition),
        published_at=version.published_at,
        row_version=version.row_version,
    )


def _criterion_row(criterion: EvaluationCriterion) -> EvaluationCriterionRow:
    return EvaluationCriterionRow(
        criterion_id=str(criterion.criterion_id),
        company_id=str(criterion.company_id),
        competency_model_version_id=str(criterion.competency_model_version_id),
        code=criterion.code,
        name=criterion.name,
        description=criterion.description,
        weight=criterion.weight,
        good_evidence=dict(criterion.good_evidence),
        weak_evidence=dict(criterion.weak_evidence),
        abstain_guidance=criterion.abstain_guidance,
        common_questions=list(criterion.common_questions),
        required=criterion.required,
    )


def _version(
    row: CompetencyModelVersionRow,
    criteria: Sequence[EvaluationCriterionRow],
) -> CompetencyModelVersion:
    return CompetencyModelVersion(
        competency_model_version_id=OpaqueId(row.competency_model_version_id),
        company_id=OpaqueId(row.company_id),
        position_id=OpaqueId(row.position_id),
        version_number=row.version_number,
        criteria=tuple(
            EvaluationCriterion(
                criterion_id=OpaqueId(item.criterion_id),
                company_id=OpaqueId(item.company_id),
                competency_model_version_id=OpaqueId(item.competency_model_version_id),
                code=item.code,
                name=item.name,
                description=item.description,
                weight=item.weight,
                good_evidence=item.good_evidence,
                weak_evidence=item.weak_evidence,
                abstain_guidance=item.abstain_guidance,
                common_questions=tuple(item.common_questions),
                required=item.required,
            )
            for item in criteria
        ),
        prohibited_topics=tuple(row.prohibited_topics),
        interview_duration_minutes=row.interview_duration_minutes,
        persona_definition=row.persona_definition,
        status=CompetencyModelStatus(row.status),
        published_at=_optional_database_instant(row.published_at),
        row_version=row.row_version,
    )


def _campaign_row(campaign: Campaign) -> CampaignRow:
    return CampaignRow(
        campaign_id=str(campaign.campaign_id),
        company_id=str(campaign.company_id),
        position_id=str(campaign.position_id),
        competency_model_version_id=str(campaign.competency_model_version_id),
        name=campaign.name,
        candidate_instructions=campaign.candidate_instructions,
        status=campaign.status.value,
        published_at=campaign.published_at,
        closed_at=campaign.closed_at,
        row_version=campaign.row_version,
        invitations_issued=campaign.invitations_issued,
    )


def _campaign(row: CampaignRow) -> Campaign:
    return Campaign(
        campaign_id=OpaqueId(row.campaign_id),
        company_id=OpaqueId(row.company_id),
        position_id=OpaqueId(row.position_id),
        competency_model_version_id=OpaqueId(row.competency_model_version_id),
        name=row.name,
        candidate_instructions=row.candidate_instructions,
        status=CampaignStatus(row.status),
        published_at=_optional_database_instant(row.published_at),
        closed_at=_optional_database_instant(row.closed_at),
        row_version=row.row_version,
        invitations_issued=row.invitations_issued,
    )


def _invitation_row(invitation: Invitation) -> InvitationRow:
    return InvitationRow(
        invitation_id=str(invitation.invitation_id),
        company_id=str(invitation.company_id),
        campaign_id=str(invitation.campaign_id),
        applicant_id=str(invitation.applicant_id),
        applicant_email=invitation.applicant_email,
        token_hash=invitation.token_hash,
        expires_at=invitation.expires_at,
        state=invitation.state.value,
        row_version=invitation.row_version,
        token_exchanged_at=invitation.token_exchanged_at,
        identity_verified_at=invitation.identity_verified_at,
        applied_transitions=[
            [idempotency_key, state.value]
            for idempotency_key, state in invitation.applied_transitions
        ],
    )


def _invitation(row: InvitationRow) -> Invitation:
    return Invitation(
        invitation_id=OpaqueId(row.invitation_id),
        company_id=OpaqueId(row.company_id),
        campaign_id=OpaqueId(row.campaign_id),
        applicant_id=OpaqueId(row.applicant_id),
        applicant_email=row.applicant_email,
        token_hash=row.token_hash,
        expires_at=_database_instant(row.expires_at),
        state=InvitationState(row.state),
        row_version=row.row_version,
        token_exchanged_at=_optional_database_instant(row.token_exchanged_at),
        identity_verified_at=_optional_database_instant(row.identity_verified_at),
        applied_transitions=tuple(
            (item[0], InvitationState(item[1])) for item in row.applied_transitions
        ),
    )


def _profile(row: ApplicantProfileRow) -> ApplicantProfile:
    return ApplicantProfile(
        applicant_id=OpaqueId(row.applicant_id),
        company_id=OpaqueId(row.company_id),
        invitation_id=OpaqueId(row.invitation_id),
        display_name=row.display_name,
        verification_method=VerificationMethod(row.verification_method),
        technology_tags=tuple(row.technology_tags),
    )


def _consent_row(consent: ConsentRecord) -> ConsentRecordRow:
    return ConsentRecordRow(
        consent_record_id=str(consent.consent_record_id),
        company_id=str(consent.company_id),
        invitation_id=str(consent.invitation_id),
        applicant_id=str(consent.applicant_id),
        policy_version=consent.policy_version,
        purposes=sorted(purpose.value for purpose in consent.purposes),
        retention_days=consent.retention_days,
        accepted_at=consent.accepted_at,
        withdrawn_at=consent.withdrawn_at,
        evidence_digest=consent.evidence_digest,
    )


def _consent(row: ConsentRecordRow) -> ConsentRecord:
    return ConsentRecord(
        consent_record_id=OpaqueId(row.consent_record_id),
        company_id=OpaqueId(row.company_id),
        invitation_id=OpaqueId(row.invitation_id),
        applicant_id=OpaqueId(row.applicant_id),
        policy_version=row.policy_version,
        purposes=frozenset(ConsentPurpose(value) for value in row.purposes),
        retention_days=row.retention_days,
        accepted_at=_database_instant(row.accepted_at),
        withdrawn_at=_optional_database_instant(row.withdrawn_at),
        evidence_digest=row.evidence_digest,
    )


def _database_instant(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _optional_database_instant(value: datetime | None) -> datetime | None:
    return _database_instant(value) if value is not None else None
