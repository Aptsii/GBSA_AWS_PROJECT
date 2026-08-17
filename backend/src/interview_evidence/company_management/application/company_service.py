from __future__ import annotations

from interview_evidence.company_management.domain.company import Position
from interview_evidence.company_management.repositories.postgres import (
    CompanyManagementRepository,
)
from interview_evidence.shared.ids import Clock, UUID7Generator
from interview_evidence.shared.security.principals import CompanyPrincipal
from interview_evidence.shared.tenant import TenantContext


class CompanyService:
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

    @staticmethod
    def current_user(principal: CompanyPrincipal) -> dict[str, object]:
        subject_email = principal.identity_subject.strip().lower()
        email = subject_email if "@" in subject_email else "company-user@tenant.invalid"
        return {
            "company_user_id": str(principal.company_user_id),
            "company_id": str(principal.company_id),
            "email": email,
            "status": "active",
        }

    def create_position(
        self,
        context: TenantContext,
        *,
        title: str,
        description: str,
    ) -> Position:
        position = Position(
            position_id=self.id_generator.new(),
            company_id=context.company_id,
            title=title,
            description=description,
            created_by=context.actor_id,
            created_at=self.clock.now(),
        )
        return self.repository.add_position(context, position)

    def list_positions(self, context: TenantContext) -> tuple[Position, ...]:
        return self.repository.list_positions(context)
