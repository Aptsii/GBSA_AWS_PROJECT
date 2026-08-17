from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from interview_evidence.reporting.application.deletion_service import DeletionService
from interview_evidence.reporting.application.review_service import ReviewService
from interview_evidence.reporting.domain.deletion import DeletionManifest
from interview_evidence.reporting.domain.report import (
    AssessmentState,
    Evidence,
    Report,
    ReportItem,
)
from interview_evidence.shared.ids import OpaqueId
from interview_evidence.shared.tenant import (
    ActorType,
    ApplicantScope,
    TenantContext,
    ensure_company_scope,
)

NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
COMPANY_ID = OpaqueId("0198b6c5-8800-7000-8000-000000000401")
COMPANY_USER_ID = OpaqueId("0198b6c5-8800-7000-8000-000000000402")
APPLICANT_ID = OpaqueId("0198b6c5-8800-7000-8000-000000000403")
INVITATION_ID = OpaqueId("0198b6c5-8800-7000-8000-000000000404")
SESSION_ID = OpaqueId("0198b6c5-8800-7000-8000-000000000405")
MODEL_VERSION_ID = OpaqueId("0198b6c5-8800-7000-8000-000000000406")
CRITERION_ID = OpaqueId("0198b6c5-8800-7000-8000-000000000407")


@dataclass(slots=True)
class _LiveReportingContracts:
    report: Report
    invitation_id: OpaqueId
    review: ReviewService
    deletion: DeletionService
    manifest: DeletionManifest | None = None

    def get_report(self, context: TenantContext, **arguments: object) -> dict[str, object]:
        ensure_company_scope(context, self.report.company_id)
        assert OpaqueId(arguments["session_id"]) == self.report.interview_session_id
        item = self.report.items[0]
        return {
            "company_id": str(self.report.company_id),
            "interview_session_id": str(self.report.interview_session_id),
            "report_id": str(self.report.report_id),
            "status": self.report.status,
            "summary": self.report.summary,
            "items": [
                {
                    "report_item_id": str(item.report_item_id),
                    "criterion_id": str(item.criterion_id),
                    "assessment_state": item.assessment_state.value,
                    "evidence_count": len(item.evidence),
                }
            ],
            "ai_original_immutable": self.report.kind == "ai_original",
        }

    def get_review_projection(
        self, context: TenantContext, **_arguments: object
    ) -> dict[str, object]:
        history = self.review.history(context, self.invitation_id)
        decisions = [item for item in history if item.review_type.value == "final_decision"]
        decision = decisions[-1].value.get("decision") if decisions else None
        return {
            "company_id": str(context.company_id),
            "invitation_id": str(self.invitation_id),
            "interview_session_id": str(self.report.interview_session_id),
            "report_id": str(self.report.report_id),
            "report_status": self.report.status,
            "summary_status": "ready",
            "human_decision_status": decision,
        }

    def request_deletion(self, context: TenantContext, **arguments: object) -> dict[str, object]:
        request = self.deletion.request(
            context,
            ApplicantScope(COMPANY_ID, APPLICANT_ID, self.invitation_id),
            reason=str(arguments["reason"]),
        )
        self.manifest = self.deletion.enumerate(
            request,
            (
                ("aurora", "report", str(self.report.report_id)),
                ("s3", "evidence_media", str(self.report.items[0].evidence[0].evidence_id)),
            ),
        )
        return self.get_deletion_status(context, deletion_request_id=request.deletion_request_id)

    def get_deletion_status(self, context: TenantContext, **arguments: object) -> dict[str, object]:
        ensure_company_scope(context, COMPANY_ID)
        assert self.manifest is not None
        assert OpaqueId(arguments["deletion_request_id"]) == self.manifest.deletion_request_id
        return {
            "company_id": str(COMPANY_ID),
            "deletion_request_id": str(self.manifest.deletion_request_id),
            "manifest_id": str(self.manifest.manifest_id),
            "status": self.manifest.status,
            "expected_targets": len(self.manifest.targets),
            "verified_targets": sum(
                target.status == "verified_absent" for target in self.manifest.targets
            ),
        }


@dataclass(frozen=True, slots=True)
class _CompanyCandidateView:
    reporting: _LiveReportingContracts

    def load(
        self, context: TenantContext, *, invitation_id: OpaqueId, session_id: OpaqueId
    ) -> dict[str, object]:
        ensure_company_scope(context, COMPANY_ID)
        report = self.reporting.get_report(context, session_id=session_id)
        review = self.reporting.get_review_projection(context, invitation_id=invitation_id)
        return {"report": report, "review": review}


def test_lane_d_report_review_and_deletion_project_into_company_view() -> None:
    context = TenantContext(
        company_id=COMPANY_ID,
        actor_type=ActorType.COMPANY_USER,
        actor_id=COMPANY_USER_ID,
        request_id="0198b6c5-8800-7000-8000-000000000408",
        trace_id="integration-d-to-a",
    )
    report_item_id = OpaqueId("0198b6c5-8800-7000-8000-000000000409")
    evidence = Evidence(
        evidence_id="0198b6c5-8800-7000-8000-000000000410",
        company_id=COMPANY_ID,
        report_item_id=report_item_id,
        criterion_id=CRITERION_ID,
        competency_model_version_id=MODEL_VERSION_ID,
        answer_turn_id="0198b6c5-8800-7000-8000-000000000411",
        transcript_segment_id="0198b6c5-8800-7000-8000-000000000412",
        video_start_ms=1_000,
        video_end_ms=4_000,
        observation="지원자가 복구 판단을 설명했습니다.",
        rationale="확정 답변과 영상 구간이 직접 연결됩니다.",
        sufficiency="direct",
        generation_version="report-v1",
        created_at=NOW,
    )
    report = Report(
        report_id="0198b6c5-8800-7000-8000-000000000413",
        company_id=COMPANY_ID,
        interview_session_id=SESSION_ID,
        competency_model_version_id=MODEL_VERSION_ID,
        report_version=1,
        status="ready",
        summary="사람 검토용 근거 보고서",
        model_config_version="report-model-v1",
        prompt_version="report-prompt-v1",
        items=(
            ReportItem(
                report_item_id=report_item_id,
                report_id="0198b6c5-8800-7000-8000-000000000413",
                criterion_id=CRITERION_ID,
                competency_model_version_id=MODEL_VERSION_ID,
                assessment_state=AssessmentState.CONFIRMED,
                observation="복구 판단을 구체적으로 설명했습니다.",
                rationale="지원자 최종 답변이 직접 뒷받침합니다.",
                uncertainty="낮음",
                evidence=(evidence,),
            ),
        ),
        created_at=NOW,
    )
    review = ReviewService()
    review.final_decision(
        context,
        invitation_id=INVITATION_ID,
        decision="hold",
        reason="사람 면접 추가 확인",
        idempotency_key="d-to-a-final-decision-0001",
    )
    contracts = _LiveReportingContracts(report, INVITATION_ID, review, DeletionService())

    view = _CompanyCandidateView(contracts).load(
        context, invitation_id=INVITATION_ID, session_id=SESSION_ID
    )
    deletion = contracts.request_deletion(context, reason="지원자 삭제 요청")
    assert contracts.manifest is not None
    contracts.deletion.record_result(
        contracts.manifest,
        contracts.manifest.targets[0].target_id,
        verified_absent=True,
    )
    deleting = contracts.get_deletion_status(
        context, deletion_request_id=deletion["deletion_request_id"]
    )

    assert view["report"]["ai_original_immutable"] is True
    assert view["report"]["items"][0]["evidence_count"] == 1
    assert view["review"]["human_decision_status"] == "hold"
    assert deleting["status"] != "completed"
    assert deleting["verified_targets"] == 1
