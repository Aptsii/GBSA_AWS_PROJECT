from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from interview_evidence.company_management.adapters.applicant_session import (
    ApplicantSessionAdapter,
)
from interview_evidence.company_management.adapters.company_auth import JWTCompanyAuthenticator
from interview_evidence.company_management.api.applicant_routes import ApplicantRouteRuntime
from interview_evidence.company_management.api.company_routes import CompanyRouteRuntime
from interview_evidence.company_management.application.applicant_access_service import (
    ApplicantAccessService,
    consent_authorization_snapshot,
)
from interview_evidence.company_management.application.company_service import CompanyService
from interview_evidence.company_management.application.criteria_service import (
    CriteriaService,
    criterion_version_snapshot,
)
from interview_evidence.company_management.application.hiring_service import (
    HiringService,
    campaign_snapshot,
)
from interview_evidence.company_management.repositories.postgres import CompanyManagementRepository
from interview_evidence.shared.config import RuntimeEnvironment, Settings
from interview_evidence.shared.ids import Clock, SystemClock, UUID7Generator
from interview_evidence.shared.security.principals import CompanyAuthenticator
from interview_evidence.shared.tenant import TenantContext


class CompanyAuthorizationFacade:
    __slots__ = ("_clock", "_repository")

    def __init__(self, repository: CompanyManagementRepository, *, clock: Clock) -> None:
        self._repository = repository
        self._clock = clock

    def authorize_invitation(
        self,
        context: TenantContext,
        **arguments: object,
    ) -> dict[str, object]:
        invitation = self._repository.get_invitation(context, str(arguments["invitation_id"]))
        required_state = str(arguments["required_state"])
        authorized = (
            invitation.state.value == required_state and self._clock.now() < invitation.expires_at
        )
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
        self,
        context: TenantContext,
        **arguments: object,
    ) -> dict[str, object]:
        consent = self._repository.get_latest_consent(context, str(arguments["invitation_id"]))
        if consent is None:
            return {"authorized": False, "reason_code": "consent_missing"}
        snapshot = consent_authorization_snapshot(consent)
        required_values = arguments["required_purposes"]
        if not isinstance(required_values, list):
            raise TypeError("required_purposes must be a list")
        required = {str(value) for value in required_values}
        purposes = snapshot["purpose_codes"]
        snapshot["authorized"] = (
            snapshot["authorized"] is True
            and isinstance(purposes, list)
            and required <= set(purposes)
        )
        return snapshot

    def get_campaign_snapshot(
        self,
        context: TenantContext,
        **arguments: object,
    ) -> dict[str, object]:
        campaign = self._repository.get_campaign(context, str(arguments["campaign_id"]))
        version = self._repository.get_competency_model_version(
            context,
            campaign.competency_model_version_id,
        )
        return campaign_snapshot(
            campaign,
            prohibited_topics=version.prohibited_topics,
            interview_duration_minutes=version.interview_duration_minutes,
            persona_definition=version.persona_definition,
        )

    def get_criterion_version(
        self,
        context: TenantContext,
        **arguments: object,
    ) -> dict[str, object]:
        version = self._repository.get_competency_model_version(
            context,
            str(arguments["version_id"]),
        )
        return criterion_version_snapshot(version)


@dataclass(frozen=True, slots=True)
class CompanyRuntimeBundle:
    company: CompanyRouteRuntime
    applicant: ApplicantRouteRuntime
    authorization: CompanyAuthorizationFacade
    applicant_sessions: ApplicantSessionAdapter


def create_company_runtime_bundle(
    session: Session,
    settings: Settings,
    *,
    authenticator: CompanyAuthenticator | None = None,
    clock: Clock | None = None,
) -> CompanyRuntimeBundle:
    active_clock = clock or SystemClock()
    id_generator = UUID7Generator(active_clock)
    repository = CompanyManagementRepository(session)
    company_service = CompanyService(repository, clock=active_clock, id_generator=id_generator)
    criteria_service = CriteriaService(repository, clock=active_clock, id_generator=id_generator)
    hiring_service = HiringService(repository, clock=active_clock, id_generator=id_generator)
    access_service = ApplicantAccessService(
        repository,
        clock=active_clock,
        id_generator=id_generator,
        retention_days=settings.default_retention_days,
    )
    company_authenticator = authenticator or JWTCompanyAuthenticator(
        issuer=str(settings.company_jwt_issuer),
        audience=settings.company_jwt_audience,
        jwks_url=str(settings.company_jwks_url),
    )
    applicant_sessions = ApplicantSessionAdapter(
        repository,
        clock=active_clock,
        id_generator=id_generator,
        secret=settings.applicant_session_secret.get_secret_value(),
        ttl_seconds=settings.applicant_session_ttl_seconds,
    )
    return CompanyRuntimeBundle(
        company=CompanyRouteRuntime(
            authenticator=company_authenticator,
            company_service=company_service,
            criteria_service=criteria_service,
            hiring_service=hiring_service,
        ),
        applicant=ApplicantRouteRuntime(
            access_service=access_service,
            hiring_service=hiring_service,
            session_adapter=applicant_sessions,
            cookie_secure=settings.environment
            not in {RuntimeEnvironment.LOCAL, RuntimeEnvironment.TEST},
        ),
        authorization=CompanyAuthorizationFacade(repository, clock=active_clock),
        applicant_sessions=applicant_sessions,
    )
