from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import delete, select

from interview_evidence.company_management.repositories.postgres import (
    ApplicantProfileRow,
    CompanyManagementRepository,
    ConsentRecordRow,
    InvitationRow,
)
from interview_evidence.shared.ids import Clock, OpaqueId, UUID7Generator
from interview_evidence.shared.messaging.outbox import AggregateRef, OutboxEvent
from interview_evidence.shared.persistence import AuditEventRow
from interview_evidence.shared.tenant import TenantContext, ensure_company_scope


class CompanyDeletionTargets:
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

    def enumerate_invitation(
        self,
        context: TenantContext,
        invitation_id: str | OpaqueId,
    ) -> dict[str, object]:
        invitation = self.repository.get_invitation(context, invitation_id)
        owned = self.repository.deletion_target_ids(
            context,
            invitation_id=invitation.invitation_id,
        )
        audit_ids = tuple(
            OpaqueId(value)
            for value in self.repository.session.scalars(
                select(AuditEventRow.audit_event_id).where(
                    AuditEventRow.company_id == str(invitation.company_id),
                    AuditEventRow.resource_id.in_(
                        [str(invitation.invitation_id), str(invitation.applicant_id)]
                    ),
                )
            ).all()
        )
        targets = _targets(
            invitation=owned["invitation"],
            applicant=owned["applicant"],
            consent_record=owned["consent_record"],
            audit_event=audit_ids,
        )
        return {
            "company_id": str(invitation.company_id),
            "scope_type": "invitation",
            "scope_id": str(invitation.invitation_id),
            "owner_lane": "A",
            "targets": targets,
        }

    def delete_and_verify(
        self,
        context: TenantContext,
        *,
        deletion_request_id: str | OpaqueId,
        target: dict[str, object],
    ) -> dict[str, object]:
        ensure_company_scope(context, context.company_id)
        target_id = OpaqueId(str(target["target_id"]))
        target_type = str(target["target_type"])
        if target_type == "consent_record":
            self.repository.session.execute(
                delete(ConsentRecordRow).where(
                    ConsentRecordRow.company_id == str(context.company_id),
                    ConsentRecordRow.consent_record_id == str(target_id),
                )
            )
            remaining = self.repository.session.scalar(
                select(ConsentRecordRow.consent_record_id).where(
                    ConsentRecordRow.company_id == str(context.company_id),
                    ConsentRecordRow.consent_record_id == str(target_id),
                )
            )
        elif target_type == "audit_event":
            self.repository.session.execute(
                delete(AuditEventRow).where(
                    AuditEventRow.company_id == str(context.company_id),
                    AuditEventRow.audit_event_id == str(target_id),
                )
            )
            remaining = self.repository.session.scalar(
                select(AuditEventRow.audit_event_id).where(
                    AuditEventRow.company_id == str(context.company_id),
                    AuditEventRow.audit_event_id == str(target_id),
                )
            )
        elif target_type == "applicant":
            self.repository.session.execute(
                delete(ApplicantProfileRow).where(
                    ApplicantProfileRow.company_id == str(context.company_id),
                    ApplicantProfileRow.applicant_id == str(target_id),
                )
            )
            remaining = self.repository.session.scalar(
                select(ApplicantProfileRow.applicant_id).where(
                    ApplicantProfileRow.company_id == str(context.company_id),
                    ApplicantProfileRow.applicant_id == str(target_id),
                )
            )
        else:
            self.repository.session.execute(
                delete(InvitationRow).where(
                    InvitationRow.company_id == str(context.company_id),
                    InvitationRow.invitation_id == str(target_id),
                )
            )
            remaining = self.repository.session.scalar(
                select(InvitationRow.invitation_id).where(
                    InvitationRow.company_id == str(context.company_id),
                    InvitationRow.invitation_id == str(target_id),
                )
            )
        self.repository.session.flush()
        return {
            "company_id": str(context.company_id),
            "deletion_request_id": str(OpaqueId(deletion_request_id)),
            "target_id": str(target_id),
            "owner_lane": "A",
            "status": "verified_absent" if remaining is None else "failed",
            "attempts": 1,
            "verified_at": (
                self.clock.now().isoformat().replace("+00:00", "Z") if remaining is None else None
            ),
            "error_code": None if remaining is None else "TARGET_REMAINS",
        }

    def retention_expired_event(
        self,
        context: TenantContext,
        *,
        invitation_id: str | OpaqueId,
        applicant_id: str | OpaqueId,
        policy_snapshot_id: str | OpaqueId,
        aggregate_version: int,
        idempotency_key: str,
        correlation_id: str | OpaqueId,
    ) -> OutboxEvent:
        checked = ensure_company_scope(context, context.company_id)
        expired_at = self.clock.now()
        return OutboxEvent(
            event_id=self.id_generator.new(),
            company_id=checked.company_id,
            event_type="retention.expired",
            event_version=1,
            aggregate=AggregateRef(
                aggregate_type="invitation",
                aggregate_id=OpaqueId(invitation_id),
                version=aggregate_version,
            ),
            idempotency_key=idempotency_key,
            occurred_at=expired_at,
            trace_id=context.trace_id,
            correlation_id=OpaqueId(correlation_id),
            causation_id=None,
            payload={
                "invitation_id": str(OpaqueId(invitation_id)),
                "applicant_id": str(OpaqueId(applicant_id)),
                "policy_snapshot_id": str(OpaqueId(policy_snapshot_id)),
                "expired_at": expired_at.isoformat().replace("+00:00", "Z"),
            },
        )


def _targets(**groups: Iterable[OpaqueId]) -> list[dict[str, object]]:
    targets: list[dict[str, object]] = []
    for target_type, identifiers in groups.items():
        for identifier in identifiers:
            targets.append(
                {
                    "target_id": str(identifier),
                    "target_type": target_type,
                    "store": "aurora",
                    "target_version": 1,
                }
            )
    targets.sort(key=lambda target: (str(target["target_type"]), str(target["target_id"])))
    return targets
