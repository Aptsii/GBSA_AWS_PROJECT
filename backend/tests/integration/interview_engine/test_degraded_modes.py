from __future__ import annotations

from interview_evidence.interview_engine.adapters.polly import SpeechSynthesizer
from interview_evidence.interview_engine.adapters.retrieval_client import RetrievalClient
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.tenant import TenantContext

from tests.fixtures.shared.factories import COMPANY_ID, make_tenant_context


class _UnavailableContracts:
    def retrieve_context(self, *_: object, **__: object) -> dict[str, object]:
        raise SafeApplicationError(ErrorCode.DEPENDENCY_UNAVAILABLE)


def test_retrieval_and_speech_failures_use_defined_fallbacks() -> None:
    context = TenantContext(**make_tenant_context())
    retrieval = RetrievalClient(_UnavailableContracts()).retrieve(context, query="장애 복구")
    speech = SpeechSynthesizer(fail=True).synthesize(context, COMPANY_ID, "질문")
    assert retrieval.results == ()
    assert retrieval.degraded_mode == "search_fallback"
    assert speech.text_only is True
