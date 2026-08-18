from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import Clock, OpaqueId, UUID7Generator
from interview_evidence.shared.tenant import ApplicantScope, TenantContext, ensure_applicant_scope
from interview_evidence.submission_analysis.adapters.object_storage import SubmissionObjectStorage
from interview_evidence.submission_analysis.application.authorization import (
    SubmissionAuthorizationGate,
)
from interview_evidence.submission_analysis.application.submission_validator import (
    SubmissionValidator,
)
from interview_evidence.submission_analysis.domain.submission import (
    SourceType,
    Submission,
    SubmissionStatus,
)
from interview_evidence.submission_analysis.repositories.postgres import (
    SubmissionAnalysisRepository,
)


@dataclass(frozen=True, slots=True)
class SafeAuditProjection:
    action: str
    company_id: OpaqueId
    applicant_id: OpaqueId
    resource_id: OpaqueId


class SubmissionApplicationService:
    __slots__ = (
        "_audit_events",
        "_authorization",
        "_clock",
        "_digests",
        "_id_generator",
        "_object_storage",
        "_repository",
        "_responses",
        "_validator",
    )

    def __init__(
        self,
        *,
        repository: SubmissionAnalysisRepository,
        authorization: SubmissionAuthorizationGate,
        object_storage: SubmissionObjectStorage,
        validator: SubmissionValidator,
        clock: Clock,
        id_generator: UUID7Generator,
    ) -> None:
        self._repository = repository
        self._authorization = authorization
        self._object_storage = object_storage
        self._validator = validator
        self._clock = clock
        self._id_generator = id_generator
        self._digests: dict[tuple[OpaqueId, str], str] = {}
        self._responses: dict[tuple[OpaqueId, str], dict[str, object]] = {}
        self._audit_events: list[SafeAuditProjection] = []

    @property
    def audit_events(self) -> tuple[SafeAuditProjection, ...]:
        return tuple(self._audit_events)

    def create_upload_intent(self, **arguments: object) -> dict[str, object]:
        context = arguments["context"]
        scope = arguments["scope"]
        if not isinstance(context, TenantContext) or not isinstance(scope, ApplicantScope):
            raise TypeError("tenant context and applicant scope are required")
        byte_size = arguments["byte_size"]
        if not isinstance(byte_size, int):
            raise TypeError("byte_size must be an integer")
        self._authorization.authorize(context, scope)
        checked = self._validator.validate_upload(
            source_type=str(arguments["source_type"]),
            filename=str(arguments["filename"]),
            media_type=str(arguments["media_type"]),
            byte_size=byte_size,
            sha256=str(arguments["sha256"]),
        )
        idempotency_key = str(arguments["idempotency_key"])
        digest = self._digest(
            {
                "source_type": checked.source_type.value,
                "filename": checked.filename,
                "media_type": checked.media_type,
                "byte_size": checked.byte_size,
                "sha256": checked.sha256,
            }
        )
        replay = self._replay(scope, idempotency_key, digest)
        if replay is not None:
            return replay
        response = self._object_storage.create_intent(
            context,
            scope,
            source_type=checked.source_type.value,
            filename=checked.filename,
            media_type=checked.media_type,
            byte_size=checked.byte_size,
            sha256=checked.sha256,
        )
        self._record(scope, idempotency_key, digest, response)
        self._audit_events.append(
            SafeAuditProjection(
                action="submission.upload_intent_created",
                company_id=scope.company_id,
                applicant_id=scope.applicant_id,
                resource_id=OpaqueId(str(response["upload_id"])),
            )
        )
        return response

    def register_submission(self, **arguments: object) -> dict[str, object]:
        context = arguments["context"]
        scope = arguments["scope"]
        if not isinstance(context, TenantContext) or not isinstance(scope, ApplicantScope):
            raise TypeError("tenant context and applicant scope are required")
        self._authorization.authorize(context, scope)
        source_type = SourceType(str(arguments["source_type"]))
        idempotency_key = str(arguments["idempotency_key"])
        replay_payload = {
            "source_type": source_type.value,
            "upload_id": arguments.get("upload_id"),
            "public_url": arguments.get("public_url"),
            "candidate_identity_inputs": arguments.get("candidate_identity_inputs"),
        }
        digest = self._digest(replay_payload)
        replay = self._replay(scope, idempotency_key, digest)
        if replay is not None:
            return replay
        if source_type in {SourceType.COVER_LETTER, SourceType.RESUME, SourceType.PDF}:
            upload_id = str(arguments["upload_id"])
            intent = self._object_storage.verify_upload(context, scope, upload_id)
            source_uri = f"upload:{upload_id}"
            original_filename = intent.filename
            content_hash = intent.expected_sha256
            byte_size = intent.expected_byte_size
            media_type = intent.media_type
        else:
            public_url = self._validator.validate_public_url(
                str(arguments["public_url"]),
                git_only=source_type is SourceType.PUBLIC_GIT,
            )
            source_uri = public_url
            original_filename = None
            content_hash = None
            byte_size = None
            media_type = None
        submission = Submission(
            submission_id=self._id_generator.new(),
            scope=scope,
            source_type=source_type,
            source_uri=source_uri,
            original_filename=original_filename,
            content_hash=content_hash,
            byte_size=byte_size,
            media_type=media_type,
            status=SubmissionStatus.RECEIVED,
            created_at=self._clock.now(),
        )
        self._repository.add_submission(context, submission)
        response = submission.view()
        self._record(scope, idempotency_key, digest, response)
        self._audit_events.append(
            SafeAuditProjection(
                action="submission.registered",
                company_id=scope.company_id,
                applicant_id=scope.applicant_id,
                resource_id=submission.submission_id,
            )
        )
        return response

    def list_submissions(self, **arguments: object) -> list[dict[str, object]]:
        context, scope = self._scope_arguments(arguments)
        self._authorization.authorize(context, scope)
        return [item.view() for item in self._repository.list_submissions(context, scope)]

    def get_readiness(self, **arguments: object) -> dict[str, object]:
        context, scope = self._scope_arguments(arguments)
        self._authorization.authorize(context, scope)
        submissions = self._repository.list_submissions(context, scope)
        strategy = self._repository.latest_strategy(context, scope)
        statuses = {item.status for item in submissions}
        if not submissions:
            overall = "waiting"
        elif SubmissionStatus.ANALYZING in statuses or SubmissionStatus.VALIDATING in statuses:
            overall = "analyzing"
        elif SubmissionStatus.FAILED in statuses and len(statuses) == 1:
            overall = "failed"
        elif SubmissionStatus.PARTIAL in statuses or SubmissionStatus.FAILED in statuses:
            overall = "partial"
        elif statuses == {SubmissionStatus.READY}:
            overall = "ready"
        else:
            overall = "analyzing"
        interview_ready = strategy is not None and overall in {"ready", "partial"}
        return {
            "overall_status": overall,
            "submissions": [item.view() for item in submissions],
            "interview_ready": interview_ready,
            "strategy_id": str(strategy.interview_strategy_id) if strategy else None,
            "strategy_version": strategy.strategy_version if strategy else None,
            "impact_summary": next(
                (item.impact_summary for item in submissions if item.impact_summary), None
            ),
        }

    @staticmethod
    def _scope_arguments(
        arguments: dict[str, object],
    ) -> tuple[TenantContext, ApplicantScope]:
        context = arguments["context"]
        scope = arguments["scope"]
        if not isinstance(context, TenantContext) or not isinstance(scope, ApplicantScope):
            raise TypeError("tenant context and applicant scope are required")
        ensure_applicant_scope(context, scope)
        return context, scope

    def _replay(
        self, scope: ApplicantScope, idempotency_key: str, digest: str
    ) -> dict[str, object] | None:
        key = (scope.company_id, idempotency_key)
        existing = self._digests.get(key)
        if existing is None:
            return None
        if existing != digest:
            raise SafeApplicationError(ErrorCode.IDEMPOTENCY_CONFLICT)
        return dict(self._responses[key])

    def _record(
        self,
        scope: ApplicantScope,
        idempotency_key: str,
        digest: str,
        response: dict[str, object],
    ) -> None:
        key = (scope.company_id, idempotency_key)
        self._digests[key] = digest
        self._responses[key] = dict(response)

    @staticmethod
    def _digest(payload: dict[str, object]) -> str:
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
        ).hexdigest()
