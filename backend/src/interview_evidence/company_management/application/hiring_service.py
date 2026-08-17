from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from interview_evidence.company_management.domain.applicant_access import (
    ApplicantProfile,
    VerificationMethod,
)
from interview_evidence.company_management.domain.criteria import CompetencyModelStatus
from interview_evidence.company_management.domain.hiring import Campaign, Invitation
from interview_evidence.company_management.repositories.postgres import (
    CompanyManagementRepository,
)
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import Clock, OpaqueId, UUID7Generator
from interview_evidence.shared.tenant import TenantContext


class HiringService:
    def __init__(
        self,
        repository: CompanyManagementRepository,
        *,
        clock: Clock,
        id_generator: UUID7Generator,
    ) -> None:
        self.repository = repository
        self.clock = clock
        self.id_generator = id_generator
        self._delivery_tokens: dict[OpaqueId, str] = {}

    def create_campaign(
        self,
        context: TenantContext,
        *,
        position_id: str | OpaqueId,
        competency_model_version_id: str | OpaqueId,
        name: str,
        candidate_instructions: str,
    ) -> Campaign:
        position = self.repository.get_position(context, position_id)
        version = self.repository.get_competency_model_version(context, competency_model_version_id)
        if (
            version.status is not CompetencyModelStatus.PUBLISHED
            or version.position_id != position.position_id
        ):
            raise SafeApplicationError(ErrorCode.CONFLICT)
        campaign = Campaign(
            campaign_id=self.id_generator.new(),
            company_id=context.company_id,
            position_id=position.position_id,
            competency_model_version_id=version.competency_model_version_id,
            name=name,
            candidate_instructions=candidate_instructions,
        )
        return self.repository.add_campaign(context, campaign)

    def publish_campaign(
        self,
        context: TenantContext,
        *,
        campaign_id: str | OpaqueId,
        expected_version: int,
    ) -> Campaign:
        campaign = self.repository.get_campaign(context, campaign_id)
        if campaign.row_version != expected_version:
            raise SafeApplicationError(
                ErrorCode.STALE_VERSION,
                current_version=campaign.row_version,
            )
        return self.repository.add_campaign(context, campaign.publish(self.clock.now()))

    def issue_invitations(
        self,
        context: TenantContext,
        *,
        campaign_id: str | OpaqueId,
        applicants: Sequence[Mapping[str, Any]],
        expires_at: datetime,
    ) -> tuple[Invitation, ...]:
        campaign = self.repository.get_campaign(context, campaign_id)
        issued: list[Invitation] = []
        for applicant in applicants:
            applicant_id = self.id_generator.new()
            invitation, raw_token = Invitation.issue(
                invitation_id=self.id_generator.new(),
                company_id=campaign.company_id,
                campaign_id=campaign.campaign_id,
                applicant_id=applicant_id,
                applicant_email=str(applicant["email"]),
                expires_at=expires_at,
            )
            self.repository.add_invitation(context, invitation)
            self.repository.add_applicant_profile(
                context,
                ApplicantProfile(
                    applicant_id=applicant_id,
                    company_id=campaign.company_id,
                    invitation_id=invitation.invitation_id,
                    display_name=str(applicant["display_name"]),
                    verification_method=VerificationMethod.EMAIL_LINK,
                ),
            )
            self._delivery_tokens[invitation.invitation_id] = raw_token
            issued.append(invitation)
        self.repository.add_campaign(context, campaign.mark_invitation_issued())
        return tuple(issued)

    def list_invitations(
        self,
        context: TenantContext,
        campaign_id: str | OpaqueId,
    ) -> tuple[Invitation, ...]:
        return self.repository.list_invitations(context, campaign_id)

    def get_test_delivery_token(self, invitation_id: str | OpaqueId) -> str:
        try:
            return self._delivery_tokens[OpaqueId(invitation_id)]
        except KeyError as error:
            raise SafeApplicationError(ErrorCode.RESOURCE_NOT_FOUND) from error


def campaign_snapshot(
    campaign: Campaign,
    *,
    prohibited_topics: Sequence[str],
    interview_duration_minutes: int,
    persona_definition: Mapping[str, Any],
) -> dict[str, object]:
    return {
        "company_id": str(campaign.company_id),
        "campaign_id": str(campaign.campaign_id),
        "position_id": str(campaign.position_id),
        "competency_model_version_id": str(campaign.competency_model_version_id),
        "status": campaign.status.value,
        "prohibited_topics": list(prohibited_topics),
        "interview_duration_minutes": interview_duration_minutes,
        "persona_definition": dict(persona_definition),
    }
