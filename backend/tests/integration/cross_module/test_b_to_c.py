from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from interview_evidence.interview_engine.adapters.retrieval_client import RetrievalClient
from interview_evidence.interview_engine.application.interview_service import InterviewService
from interview_evidence.shared.ids import FixedClock, OpaqueId, UUID7Generator
from interview_evidence.shared.tenant import ActorType, ApplicantScope, TenantContext
from interview_evidence.submission_analysis.adapters.search import (
    InMemorySubmissionSearch,
    SearchRecord,
)
from interview_evidence.submission_analysis.application.retrieval import (
    HybridRetriever,
    RetrievalQuery,
)
from interview_evidence.submission_analysis.application.strategy_service import StrategyService
from interview_evidence.submission_analysis.domain.source import SourceLocation, SourceReference
from interview_evidence.submission_analysis.domain.strategy import InterviewStrategy

NOW = datetime(2026, 8, 17, 10, 0, tzinfo=UTC)
COMPANY_ID = OpaqueId("0198b6c5-8800-7000-8000-000000000201")
APPLICANT_ID = OpaqueId("0198b6c5-8800-7000-8000-000000000202")
INVITATION_ID = OpaqueId("0198b6c5-8800-7000-8000-000000000203")
CRITERION_ID = OpaqueId("0198b6c5-8800-7000-8000-000000000204")
MODEL_VERSION_ID = OpaqueId("0198b6c5-8800-7000-8000-000000000205")


@dataclass(slots=True)
class _LiveSubmissionContracts:
    strategy: InterviewStrategy
    retriever: HybridRetriever

    def get_strategy_snapshot(
        self, _context: TenantContext, **_arguments: object
    ) -> dict[str, object]:
        return self.strategy.snapshot()

    def retrieve_context(
        self, context: TenantContext, **arguments: object
    ) -> dict[str, object]:
        result = self.retriever.retrieve(
            context,
            RetrievalQuery(
                scope=arguments["scope"],
                query_text=str(arguments["query_text"]),
                query_vector=arguments["query_vector"],
                criterion_id=arguments["criterion_id"],
                interview_session_id=arguments["interview_session_id"],
                config_version=str(arguments["config_version"]),
                limit=int(arguments["limit"]),
            ),
        )
        return {
            "company_id": str(result.company_id),
            "applicant_id": str(result.applicant_id),
            "interview_session_id": str(result.interview_session_id),
            "criterion_id": str(result.criterion_id),
            "retrieval_config_version": result.retrieval_config_version,
            "results": [
                {
                    "rank": item.rank,
                    "score": item.score,
                    "source_reference": item.source_reference.snapshot(),
                }
                for item in result.results
            ],
        }


def test_lane_b_strategy_and_retrieval_feed_lane_c_session() -> None:
    clock = FixedClock(NOW)
    ids = UUID7Generator(clock)
    scope = ApplicantScope(
        company_id=COMPANY_ID,
        applicant_id=APPLICANT_ID,
        invitation_id=INVITATION_ID,
    )
    context = TenantContext(
        company_id=COMPANY_ID,
        actor_type=ActorType.APPLICANT,
        actor_id=APPLICANT_ID,
        request_id=ids.new(),
        trace_id="integration-b-to-c",
    )
    source = SourceReference(
        company_id=COMPANY_ID,
        source_type="submission_chunk",
        source_id=ids.new(),
        source_version=1,
        source_location=SourceLocation(page=2, section="프로젝트 경험"),
        source_hash="1" * 64,
    )
    strategy = StrategyService(clock=clock, id_generator=ids).generate(
        context,
        scope=scope,
        criterion_snapshot={
            "company_id": str(COMPANY_ID),
            "competency_model_version_id": str(MODEL_VERSION_ID),
            "criteria": [
                {
                    "criterion_id": str(CRITERION_ID),
                    "code": "RECOVERY",
                    "common_questions": ["장애 복구 경험을 설명해 주세요."],
                    "required": True,
                }
            ],
        },
        verification_points=(
            {"criterion_id": CRITERION_ID, "prompt": "복구 판단 근거 확인"},
        ),
        source_references=(source,),
        duration_minutes=30,
        model_config_version="strategy-v1",
        partial=False,
    )
    search = InMemorySubmissionSearch()
    search.index(
        context,
        SearchRecord(
            scope=scope,
            reference=source,
            text="장애 복구에서 트레이드오프를 검토했습니다.",
            vector=(1.0, 0.0),
            symbols=("recover",),
        ),
    )
    contracts = _LiveSubmissionContracts(strategy, HybridRetriever(search))
    strategy_snapshot = contracts.get_strategy_snapshot(
        context, strategy_id=strategy.interview_strategy_id
    )
    retrieval = RetrievalClient(contracts)
    interview = InterviewService(retrieval=retrieval, clock=clock, id_generator=ids)
    created = interview.create_session(
        context,
        scope,
        interview_strategy_id=strategy_snapshot["interview_strategy_id"],
        competency_model_version_id=strategy_snapshot["competency_model_version_id"],
        idempotency_key="b-to-c-session-0001",
    )

    retrieved = retrieval.retrieve(
        context,
        query="장애 복구 트레이드오프",
        scope=scope,
        query_vector=(1.0, 0.0),
        criterion_id=CRITERION_ID,
        interview_session_id=created.session.interview_session_id,
        config_version="hybrid-v1",
    )

    assert created.session.interview_strategy_id == strategy.interview_strategy_id
    assert created.session.competency_model_version_id == MODEL_VERSION_ID
    assert retrieved.degraded_mode == "none"
    assert retrieved.results[0].source_reference["source_id"] == str(source.source_id)
    assert retrieved.results[0].source_reference["evidence_eligible"] is False
