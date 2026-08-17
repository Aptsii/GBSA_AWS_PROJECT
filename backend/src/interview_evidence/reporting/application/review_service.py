from __future__ import annotations

from interview_evidence.reporting.domain.review import HumanReview, ReviewType
from interview_evidence.shared.ids import OpaqueId, UUID7Generator
from interview_evidence.shared.tenant import ActorType, TenantContext, ensure_company_scope


class ReviewService:
    def __init__(self) -> None:
        self._ids = UUID7Generator()
        self._reviews: dict[tuple[OpaqueId, OpaqueId], list[HumanReview]] = {}
        self._keys: dict[tuple[OpaqueId, str], HumanReview] = {}

    def append(
        self,
        context: TenantContext,
        *,
        report_id: str | OpaqueId,
        target_id: str | OpaqueId,
        review_type: str,
        value: dict[str, object],
        reason: str | None,
        idempotency_key: str,
    ) -> HumanReview:
        ensure_company_scope(context, context.company_id)
        key = (context.company_id, idempotency_key)
        if key in self._keys:
            return self._keys[key]
        review = HumanReview(
            self._ids.new(),
            context.company_id,
            OpaqueId(report_id),
            context.actor_id,
            ReviewType(review_type),
            OpaqueId(target_id),
            value,
            reason,
            self._ids._clock.now(),
        )
        self._reviews.setdefault((context.company_id, OpaqueId(report_id)), []).append(review)
        self._keys[key] = review
        return review

    def history(self, context: TenantContext, report_id: str | OpaqueId) -> tuple[HumanReview, ...]:
        ensure_company_scope(context, context.company_id)
        return tuple(self._reviews.get((context.company_id, OpaqueId(report_id)), ()))

    def final_decision(
        self,
        context: TenantContext,
        *,
        invitation_id: str | OpaqueId,
        decision: str,
        reason: str,
        idempotency_key: str,
    ) -> HumanReview:
        if context.actor_type is not ActorType.COMPANY_USER:
            raise PermissionError("final decision must be human-authored")
        if decision not in {"advance", "reject", "hold", "withdrawn"}:
            raise ValueError("decision is invalid")
        return self.append(
            context,
            report_id=invitation_id,
            target_id=invitation_id,
            review_type="final_decision",
            value={"decision": decision},
            reason=reason,
            idempotency_key=idempotency_key,
        )
