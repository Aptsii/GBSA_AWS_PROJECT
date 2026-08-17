from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from interview_evidence.interview_engine.application.question_policy import QuestionPolicy
from interview_evidence.reporting.application.evidence_service import EvidenceService
from interview_evidence.reporting.domain.report import AssessmentState, Evidence, ReportItem
from interview_evidence.shared.ids import OpaqueId
from interview_evidence.shared.tenant import ActorType, ApplicantScope, TenantContext
from interview_evidence.submission_analysis.adapters.search import (
    InMemorySubmissionSearch,
    SearchRecord,
)
from interview_evidence.submission_analysis.application.retrieval import (
    HybridRetriever,
    RetrievalQuery,
)
from interview_evidence.submission_analysis.domain.source import SourceLocation, SourceReference

REGRESSION_ROOT = Path(__file__).resolve().parent
THRESHOLDS = {
    "retrieval": 0.75,
    "questions": 1.0,
    "evidence": 1.0,
}
COMPANY_ID = OpaqueId("018f2000-0000-7000-8000-000000001100")
APPLICANT_ID = OpaqueId("018f2000-0000-7000-8000-000000001101")
INVITATION_ID = OpaqueId("018f2000-0000-7000-8000-000000001102")
CRITERION_ID = OpaqueId("018f2000-0000-7000-8000-000000001103")
SESSION_ID = OpaqueId("018f2000-0000-7000-8000-000000001104")
MODEL_ID = OpaqueId("018f2000-0000-7000-8000-000000001105")


@dataclass(frozen=True, slots=True)
class SuiteResult:
    name: str
    config_versions: tuple[str, ...]
    passed: int
    total: int
    score: float
    threshold: float
    failures: tuple[str, ...]

    @property
    def accepted(self) -> bool:
        return self.score >= self.threshold and not self.failures


def _load_cases(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _context() -> TenantContext:
    return TenantContext(
        company_id=COMPANY_ID,
        actor_type=ActorType.APPLICANT,
        actor_id=APPLICANT_ID,
        request_id="018f2000-0000-7000-8000-000000001106",
        trace_id="regression-runner",
    )


def _result(
    name: str,
    cases: list[dict[str, Any]],
    passed: int,
    failures: list[str],
) -> SuiteResult:
    total = len(cases)
    return SuiteResult(
        name=name,
        config_versions=tuple(sorted({str(case["config_version"]) for case in cases})),
        passed=passed,
        total=total,
        score=passed / total if total else 0.0,
        threshold=THRESHOLDS[name],
        failures=tuple(failures),
    )


def run_retrieval() -> SuiteResult:
    cases = _load_cases(REGRESSION_ROOT / "retrieval" / "cases.jsonl")
    passed = 0
    failures: list[str] = []
    scope = ApplicantScope(COMPANY_ID, APPLICANT_ID, INVITATION_ID)
    context = _context()
    for case in cases:
        search = InMemorySubmissionSearch()
        for record in case["records"]:
            source_id = OpaqueId(record["source_id"])
            reference = SourceReference(
                company_id=COMPANY_ID,
                source_type=record["source_type"],
                source_id=source_id,
                source_version=1,
                source_location=SourceLocation(**record["location"]),
                source_hash=hashlib.sha256(str(source_id).encode()).hexdigest(),
            )
            search.index(
                context,
                SearchRecord(
                    scope=scope,
                    reference=reference,
                    text=record["text"],
                    vector=tuple(float(value) for value in record["vector"]),
                    symbols=tuple(record["symbols"]),
                ),
            )
        result = HybridRetriever(search).retrieve(
            context,
            RetrievalQuery(
                scope=scope,
                query_text=case["query"],
                query_vector=tuple(float(value) for value in case["query_vector"]),
                criterion_id=CRITERION_ID,
                interview_session_id=SESSION_ID,
                config_version=case["config_version"],
                exact_symbol=case["exact_symbol"],
            ),
        )
        actual_ids = [str(item.source_reference.source_id) for item in result.results]
        expected_ids = list(case["expected_source_ids"])
        top_score = result.results[0].score if result.results else 0.0
        accepted = actual_ids[: len(expected_ids)] == expected_ids and (
            bool(expected_ids) or not actual_ids
        )
        accepted = accepted and top_score >= float(case["min_top_score"])
        if accepted:
            passed += 1
        else:
            failures.append(
                f"{case['case_id']}: expected={expected_ids!r} actual={actual_ids!r} "
                f"top_score={top_score}"
            )
    return _result("retrieval", cases, passed, failures)


def run_questions() -> SuiteResult:
    cases = _load_cases(REGRESSION_ROOT / "questions" / "cases.jsonl")
    passed = 0
    failures: list[str] = []
    for case in cases:
        policy = QuestionPolicy(prohibited_topics=tuple(case["prohibited_topics"]))
        error: str | None = None
        try:
            policy.validate(
                case["question"],
                criterion_id=case["criterion_id"],
                expected_criterion_id=case["expected_criterion_id"],
                previous_questions=tuple(case["previous_questions"]),
            )
            allowed = True
        except ValueError as caught:
            allowed = False
            error = str(caught)
        expected_error = case["expected_error"]
        accepted = allowed is bool(case["expected_allowed"])
        if expected_error is not None:
            accepted = accepted and error is not None and expected_error in error
        accepted = accepted and case["expected_degraded_mode"] in {
            "none",
            "retrieval_fallback",
        }
        if accepted:
            passed += 1
        else:
            failures.append(f"{case['case_id']}: allowed={allowed} error={error!r}")
    return _result("questions", cases, passed, failures)


def _evidence() -> Evidence:
    return Evidence(
        evidence_id="018f2000-0000-7000-8000-000000001110",
        company_id=COMPANY_ID,
        report_item_id="018f2000-0000-7000-8000-000000001111",
        criterion_id=CRITERION_ID,
        competency_model_version_id=MODEL_ID,
        answer_turn_id="018f2000-0000-7000-8000-000000001112",
        transcript_segment_id="018f2000-0000-7000-8000-000000001113",
        video_start_ms=1_000,
        video_end_ms=3_000,
        observation="지원자 최종 답변 관찰",
        rationale="확정 Turn과 미디어 구간이 일치합니다.",
        sufficiency="direct",
        generation_version="evidence-policy-v1",
        created_at=datetime(2026, 8, 17, tzinfo=UTC),
    )


def run_evidence() -> SuiteResult:
    cases = _load_cases(REGRESSION_ROOT / "evidence" / "cases.jsonl")
    passed = 0
    failures: list[str] = []
    service = EvidenceService()
    for case in cases:
        anchor_valid = True
        try:
            service.validate_anchor(**case["anchor"])
        except ValueError:
            anchor_valid = False
        assessment_state = AssessmentState(case["assessment_state"])
        item_valid = True
        try:
            ReportItem(
                report_item_id="018f2000-0000-7000-8000-000000001111",
                report_id="018f2000-0000-7000-8000-000000001114",
                criterion_id=CRITERION_ID,
                competency_model_version_id=MODEL_ID,
                assessment_state=assessment_state,
                observation="회귀 관찰",
                rationale="회귀 근거",
                uncertainty="고정",
                evidence=(_evidence(),) if case["has_evidence"] else (),
            )
        except ValueError:
            item_valid = False
        accepted = anchor_valid is bool(case["expected_anchor_valid"])
        accepted = accepted and item_valid
        if case["unsupported_claim"]:
            accepted = accepted and assessment_state is AssessmentState.INSUFFICIENT_EVIDENCE
            accepted = accepted and not case["has_evidence"]
        if accepted:
            passed += 1
        else:
            failures.append(
                f"{case['case_id']}: anchor_valid={anchor_valid} item_valid={item_valid}"
            )
    return _result("evidence", cases, passed, failures)


def run_all() -> tuple[SuiteResult, ...]:
    return run_retrieval(), run_questions(), run_evidence()


def main() -> int:
    results = run_all()
    payload = {
        "accepted": all(result.accepted for result in results),
        "suites": [{**asdict(result), "accepted": result.accepted} for result in results],
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return 0 if payload["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
