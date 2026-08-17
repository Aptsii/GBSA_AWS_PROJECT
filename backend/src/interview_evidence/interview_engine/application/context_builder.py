"""Token-budgeted context assembly for the next interview question."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from interview_evidence.shared.aws_clients.ports import ProtectedText
from interview_evidence.shared.ids import OpaqueId
from interview_evidence.shared.tenant import ApplicantScope, TenantContext, ensure_applicant_scope


@dataclass(frozen=True, slots=True, repr=False)
class InterviewContext:
    interview_session_id: OpaqueId
    prompt: ProtectedText
    included_turn_ids: tuple[str, ...]
    remaining_criterion_ids: tuple[str, ...]
    estimated_tokens: int
    truncated: bool

    def __repr__(self) -> str:
        return (
            "InterviewContext(prompt=[REDACTED], "
            f"interview_session_id={self.interview_session_id!r}, "
            f"included_turn_ids={self.included_turn_ids!r}, "
            f"remaining_criterion_ids={self.remaining_criterion_ids!r}, "
            f"estimated_tokens={self.estimated_tokens!r}, truncated={self.truncated!r})"
        )


class ContextBuilder:
    __slots__ = ("_max_tokens",)

    def __init__(self, *, max_tokens: int = 1_200) -> None:
        if max_tokens < 128:
            raise ValueError("context token budget must be at least 128")
        self._max_tokens = max_tokens

    def build(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        session_id: str | OpaqueId,
        *,
        summary: str | None,
        recent_turns: Sequence[Mapping[str, object]],
        remaining_criteria: Sequence[Mapping[str, object]],
    ) -> InterviewContext:
        ensure_applicant_scope(context, scope)
        checked_session_id = OpaqueId(session_id)
        criterion_lines, criterion_ids = _criterion_lines(remaining_criteria)
        fixed_lines = [
            "고정 평가축을 변경하지 말고 한 번에 하나의 질문만 생성하세요.",
            "남은 평가 기준:",
            *criterion_lines,
        ]
        if summary:
            fixed_lines.extend(("이전 답변 요약:", summary.strip()))
        fixed_text = "\n".join(fixed_lines)
        used_tokens = _token_cost(fixed_text)
        if used_tokens > self._max_tokens:
            raise ValueError("summary and remaining criteria exceed the context budget")

        selected: list[tuple[str, str]] = []
        truncated = False
        for turn in reversed(recent_turns):
            turn_id, rendered = _render_turn(turn)
            cost = _token_cost(rendered)
            if used_tokens + cost > self._max_tokens:
                truncated = True
                continue
            selected.append((turn_id, rendered))
            used_tokens += cost
        selected.reverse()
        prompt_parts = [fixed_text]
        if selected:
            prompt_parts.extend(("최근 대화:", *(rendered for _, rendered in selected)))
        return InterviewContext(
            interview_session_id=checked_session_id,
            prompt=ProtectedText("\n".join(prompt_parts)),
            included_turn_ids=tuple(turn_id for turn_id, _ in selected),
            remaining_criterion_ids=criterion_ids,
            estimated_tokens=used_tokens,
            truncated=truncated,
        )


def _criterion_lines(
    criteria: Sequence[Mapping[str, object]],
) -> tuple[list[str], tuple[str, ...]]:
    lines: list[str] = []
    criterion_ids: list[str] = []
    for criterion in criteria:
        criterion_id = criterion.get("criterion_id")
        name = criterion.get("name")
        if not isinstance(criterion_id, str) or not isinstance(name, str):
            raise ValueError("remaining criteria require criterion_id and name")
        criterion_ids.append(criterion_id)
        lines.append(f"- {criterion_id}: {name}")
    return lines, tuple(criterion_ids)


def _render_turn(turn: Mapping[str, object]) -> tuple[str, str]:
    turn_id = turn.get("turn_id")
    speaker = turn.get("speaker")
    text = turn.get("text")
    if not isinstance(turn_id, str) or not isinstance(speaker, str):
        raise ValueError("recent Turn requires turn_id and speaker")
    if isinstance(text, ProtectedText):
        plain_text = text.reveal()
    elif isinstance(text, str):
        plain_text = text
    else:
        raise ValueError("recent Turn requires protected text")
    return turn_id, f"[{speaker}] {plain_text}"


def _token_cost(value: str) -> int:
    return max(1, (len(value) + 3) // 4)
