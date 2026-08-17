"""Pilot load scenarios for concurrent and long-running interview pipelines."""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from statistics import mean
from threading import Barrier, Lock
from time import perf_counter
from typing import Any

from interview_evidence.interview_engine.adapters.retrieval_client import RetrievalClient
from interview_evidence.interview_engine.application.interview_service import InterviewService
from interview_evidence.interview_engine.application.question_generator import QuestionGenerator
from interview_evidence.shared.aws_clients.ports import ProtectedText
from interview_evidence.shared.ids import FixedClock, OpaqueId, UUID7Generator
from interview_evidence.shared.tenant import ActorType, ApplicantScope, TenantContext

DEFAULT_CONCURRENT_SESSIONS = 5
DEFAULT_ANSWERS_PER_SESSION = 40
DEFAULT_LONG_RUNNING_ANSWERS = 120
MINIMUM_COMPLETION_RATIO = 0.85
MINIMUM_CUMULATIVE_TURNS = 200


class _EmptyRetrievalContracts:
    def retrieve_context(self, *_args: object, **_kwargs: object) -> dict[str, object]:
        return {"results": [], "retrieval_config_version": "load-hybrid-v1"}


class _SequencedQuestionModel:
    def __init__(self) -> None:
        self._lock = Lock()
        self._sequence = 0

    def generate_question(
        self,
        _context: TenantContext,
        *,
        prompt: ProtectedText,
        criterion_id: OpaqueId,
        criterion_name: str,
        source_references: tuple[dict[str, object], ...],
    ) -> dict[str, object]:
        del prompt, source_references
        with self._lock:
            self._sequence += 1
            sequence = self._sequence
        return {
            "question": f"{criterion_name} 역량을 보여 준 {sequence}번째 판단을 설명해 주세요?",
            "target_criterion_id": str(criterion_id),
        }


@dataclass(frozen=True, slots=True)
class _SessionFixture:
    context: TenantContext
    scope: ApplicantScope
    strategy_id: OpaqueId
    model_version_id: OpaqueId
    criterion_id: OpaqueId


@dataclass(frozen=True, slots=True)
class SessionResult:
    session_number: int
    answer_count: int
    turn_count: int
    final_sequence: int
    elapsed_seconds: float
    resumed_without_duplicate: bool
    tenant_data_mixed: bool


@dataclass(frozen=True, slots=True)
class LoadReport:
    concurrent_sessions: int
    completed_sessions: int
    completion_ratio: float
    concurrent_elapsed_seconds: float
    average_session_seconds: float
    long_running_answers: int
    long_running_turns: int
    long_running_elapsed_seconds: float
    cumulative_turns: int
    minimum_completion_ratio: float
    minimum_cumulative_turns: int
    passed: bool


def _fixture(id_generator: UUID7Generator, session_number: int) -> _SessionFixture:
    company_id = id_generator.new()
    applicant_id = id_generator.new()
    invitation_id = id_generator.new()
    context = TenantContext(
        company_id=company_id,
        actor_type=ActorType.APPLICANT,
        actor_id=applicant_id,
        request_id=id_generator.new(),
        trace_id=f"load-session-{session_number:02d}",
    )
    return _SessionFixture(
        context=context,
        scope=ApplicantScope(company_id, applicant_id, invitation_id),
        strategy_id=id_generator.new(),
        model_version_id=id_generator.new(),
        criterion_id=id_generator.new(),
    )


def _run_session(
    session_number: int,
    answer_count: int,
    fixture: _SessionFixture,
    clock: FixedClock,
    id_generator: UUID7Generator,
    start_barrier: Barrier | None = None,
) -> SessionResult:
    service = InterviewService(
        retrieval=RetrievalClient(_EmptyRetrievalContracts()),
        question_generator=QuestionGenerator(_SequencedQuestionModel()),
        clock=clock,
        id_generator=id_generator,
    )
    if start_barrier is not None:
        start_barrier.wait(timeout=10)

    started_at = perf_counter()
    created = service.create_session(
        fixture.context,
        fixture.scope,
        interview_strategy_id=fixture.strategy_id,
        competency_model_version_id=fixture.model_version_id,
        idempotency_key=f"load-session-create-{session_number:04d}",
    )
    current = service.start(
        fixture.context,
        fixture.scope,
        created.session.interview_session_id,
        expected_sequence=0,
    )

    for answer_number in range(1, answer_count + 1):
        result = service.finalize_answer(
            fixture.context,
            fixture.scope,
            current.interview_session_id,
            expected_sequence=current.session_sequence,
            answer_turn_id=id_generator.new(),
            transcript_text=(
                f"부하 시나리오 {session_number}의 {answer_number}번째 최종 답변입니다."
            ),
            transcript_confidence=0.99,
            criterion_id=fixture.criterion_id,
            criterion_name="문제 해결",
            remaining_criteria=(
                {"criterion_id": str(fixture.criterion_id), "name": "문제 해결"},
            ),
            idempotency_key=f"load-answer-{session_number:04d}-{answer_number:06d}",
            last_recording_chunk_sequence=answer_number,
        )
        current = result.session

    turns = service.list_turns(
        fixture.context,
        fixture.scope,
        current.interview_session_id,
    )
    snapshot = service.resume(
        fixture.context,
        fixture.scope,
        current.interview_session_id,
        client_sequence=0,
    )
    tenant_data_mixed = any(
        turn.company_id != fixture.scope.company_id
        or turn.interview_session_id != current.interview_session_id
        for turn in turns
    )
    return SessionResult(
        session_number=session_number,
        answer_count=answer_count,
        turn_count=len(turns),
        final_sequence=current.session_sequence,
        elapsed_seconds=perf_counter() - started_at,
        resumed_without_duplicate=(
            snapshot.last_final_turn_id == turns[-2].turn_id and len(turns) == answer_count * 2
        ),
        tenant_data_mixed=tenant_data_mixed,
    )


def run_load_scenarios(
    *,
    concurrent_sessions: int = DEFAULT_CONCURRENT_SESSIONS,
    answers_per_session: int = DEFAULT_ANSWERS_PER_SESSION,
    long_running_answers: int = DEFAULT_LONG_RUNNING_ANSWERS,
) -> LoadReport:
    if concurrent_sessions < DEFAULT_CONCURRENT_SESSIONS:
        raise ValueError("pilot load requires at least five concurrent sessions")
    if answers_per_session < 1 or long_running_answers < 1:
        raise ValueError("answer counts must be positive")

    clock = FixedClock(datetime(2026, 8, 17, 12, 0, tzinfo=UTC))
    id_generator = UUID7Generator(clock)
    fixtures = [
        _fixture(id_generator, session_number)
        for session_number in range(1, concurrent_sessions + 1)
    ]
    start_barrier = Barrier(concurrent_sessions)

    concurrent_started_at = perf_counter()
    results: list[SessionResult] = []
    with ThreadPoolExecutor(max_workers=concurrent_sessions) as executor:
        futures = [
            executor.submit(
                _run_session,
                session_number,
                answers_per_session,
                fixture,
                clock,
                id_generator,
                start_barrier,
            )
            for session_number, fixture in enumerate(fixtures, start=1)
        ]
        for future in as_completed(futures):
            results.append(future.result())
    concurrent_elapsed = perf_counter() - concurrent_started_at

    completed = sum(
        result.turn_count == result.answer_count * 2
        and result.resumed_without_duplicate
        and not result.tenant_data_mixed
        for result in results
    )
    completion_ratio = completed / concurrent_sessions

    long_fixture = _fixture(id_generator, concurrent_sessions + 1)
    long_result = _run_session(
        concurrent_sessions + 1,
        long_running_answers,
        long_fixture,
        clock,
        id_generator,
    )
    cumulative_turns = sum(result.turn_count for result in results) + long_result.turn_count
    passed = (
        completion_ratio >= MINIMUM_COMPLETION_RATIO
        and cumulative_turns >= MINIMUM_CUMULATIVE_TURNS
        and long_result.resumed_without_duplicate
        and not long_result.tenant_data_mixed
    )
    return LoadReport(
        concurrent_sessions=concurrent_sessions,
        completed_sessions=completed,
        completion_ratio=completion_ratio,
        concurrent_elapsed_seconds=concurrent_elapsed,
        average_session_seconds=mean(result.elapsed_seconds for result in results),
        long_running_answers=long_running_answers,
        long_running_turns=long_result.turn_count,
        long_running_elapsed_seconds=long_result.elapsed_seconds,
        cumulative_turns=cumulative_turns,
        minimum_completion_ratio=MINIMUM_COMPLETION_RATIO,
        minimum_cumulative_turns=MINIMUM_CUMULATIVE_TURNS,
        passed=passed,
    )


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concurrent-sessions", type=int, default=DEFAULT_CONCURRENT_SESSIONS)
    parser.add_argument("--answers-per-session", type=int, default=DEFAULT_ANSWERS_PER_SESSION)
    parser.add_argument("--long-running-answers", type=int, default=DEFAULT_LONG_RUNNING_ANSWERS)
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    report = run_load_scenarios(
        concurrent_sessions=arguments.concurrent_sessions,
        answers_per_session=arguments.answers_per_session,
        long_running_answers=arguments.long_running_answers,
    )
    payload: dict[str, Any] = asdict(report)
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
