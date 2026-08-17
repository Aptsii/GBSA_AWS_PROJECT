"""Structured next-question generation without exposing model reasoning."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol

from interview_evidence.interview_engine.adapters.retrieval_client import RetrievalResult
from interview_evidence.interview_engine.application.context_builder import InterviewContext
from interview_evidence.shared.aws_clients.ports import ProtectedText
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import OpaqueId
from interview_evidence.shared.tenant import TenantContext, require_tenant_context


class QuestionModel(Protocol):
    def generate_question(
        self,
        context: TenantContext,
        *,
        prompt: ProtectedText,
        criterion_id: OpaqueId,
        criterion_name: str,
        source_references: tuple[Mapping[str, object], ...],
    ) -> Mapping[str, object]: ...


@dataclass(frozen=True, slots=True, repr=False)
class GeneratedQuestion:
    text: ProtectedText
    target_criterion_id: OpaqueId
    model_config_version: str
    source_references: tuple[Mapping[str, object], ...]
    degraded_mode: Literal["none", "model_fallback", "search_fallback"]

    def __repr__(self) -> str:
        return (
            "GeneratedQuestion(text=[REDACTED], "
            f"target_criterion_id={self.target_criterion_id!r}, "
            f"model_config_version={self.model_config_version!r}, "
            f"source_reference_count={len(self.source_references)!r}, "
            f"degraded_mode={self.degraded_mode!r})"
        )


class QuestionGenerator:
    __slots__ = ("_model", "_model_config_version")

    def __init__(
        self,
        model: QuestionModel | None = None,
        *,
        model_config_version: str = "question-v1",
    ) -> None:
        if not model_config_version:
            raise ValueError("model_config_version must not be blank")
        self._model = model
        self._model_config_version = model_config_version

    def generate(
        self,
        context: TenantContext,
        interview_context: InterviewContext,
        *,
        criterion_id: str | OpaqueId,
        criterion_name: str,
        retrieval: RetrievalResult,
    ) -> GeneratedQuestion:
        require_tenant_context(context)
        checked_criterion_id = OpaqueId(criterion_id)
        if checked_criterion_id not in {
            OpaqueId(item) for item in interview_context.remaining_criterion_ids
        }:
            raise ValueError("question criterion is outside the remaining fixed axis")
        if not criterion_name.strip():
            raise ValueError("criterion_name must not be blank")
        source_references = tuple(item.source_reference for item in retrieval.results)
        if self._model is None:
            return self._fallback(
                checked_criterion_id,
                criterion_name,
                source_references,
                "search_fallback" if not source_references else "model_fallback",
            )
        try:
            payload = self._model.generate_question(
                context,
                prompt=interview_context.prompt,
                criterion_id=checked_criterion_id,
                criterion_name=criterion_name,
                source_references=source_references,
            )
        except SafeApplicationError as error:
            if error.code not in {
                ErrorCode.DEPENDENCY_TIMEOUT,
                ErrorCode.DEPENDENCY_UNAVAILABLE,
            }:
                raise
            return self._fallback(
                checked_criterion_id,
                criterion_name,
                source_references,
                "model_fallback",
            )
        text = payload.get("question")
        returned_criterion = payload.get("target_criterion_id")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("question model returned an invalid question")
        if returned_criterion != str(checked_criterion_id):
            raise ValueError("question model attempted to change the fixed criterion axis")
        return GeneratedQuestion(
            text=ProtectedText(text.strip()),
            target_criterion_id=checked_criterion_id,
            model_config_version=self._model_config_version,
            source_references=source_references,
            degraded_mode=retrieval.degraded_mode,
        )

    def _fallback(
        self,
        criterion_id: OpaqueId,
        criterion_name: str,
        source_references: tuple[Mapping[str, object], ...],
        degraded_mode: Literal["model_fallback", "search_fallback"],
    ) -> GeneratedQuestion:
        return GeneratedQuestion(
            text=ProtectedText(
                f"{criterion_name} 역량을 보여 준 경험과 당시 판단 근거를 설명해 주세요."
            ),
            target_criterion_id=criterion_id,
            model_config_version=self._model_config_version,
            source_references=source_references,
            degraded_mode=degraded_mode,
        )
