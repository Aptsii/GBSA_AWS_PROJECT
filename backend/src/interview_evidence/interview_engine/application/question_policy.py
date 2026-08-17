"""Deterministic primary and secondary safety checks for interview questions."""

from __future__ import annotations

import re
from collections.abc import Sequence

_DEFAULT_PROHIBITED_TOPICS = (
    "가족",
    "결혼",
    "임신",
    "종교",
    "정치 성향",
    "질병",
    "장애 여부",
)
_SENTENCE_SPLIT = re.compile(r"[?\uFF1F]")
_WHITESPACE = re.compile(r"\s+")


class QuestionPolicy:
    __slots__ = ("_prohibited_topics",)

    def __init__(self, *, prohibited_topics: Sequence[str] = ()) -> None:
        combined = (*_DEFAULT_PROHIBITED_TOPICS, *prohibited_topics)
        self._prohibited_topics = tuple(
            dict.fromkeys(topic.strip().casefold() for topic in combined if topic.strip())
        )

    def validate(
        self,
        question: str,
        *,
        criterion_id: str,
        previous_questions: Sequence[str],
        expected_criterion_id: str | None = None,
    ) -> str:
        normalized = _normalize(question)
        if not normalized:
            raise ValueError("question must not be blank")
        if len(normalized) > 500:
            raise ValueError("question exceeds the allowed length")
        if expected_criterion_id is not None and criterion_id != expected_criterion_id:
            raise ValueError("question criterion does not match the fixed criterion axis")
        folded = normalized.casefold()
        if any(topic in folded for topic in self._prohibited_topics):
            raise ValueError("question contains a prohibited topic")
        if _question_count(normalized) > 1:
            raise ValueError("only one question may be asked at a time")
        previous = {_normalize(item).casefold() for item in previous_questions}
        if folded in previous:
            raise ValueError("duplicate question is not allowed")
        if "평가 점수" in folded or "합격 여부" in folded:
            raise ValueError("question must not disclose or solicit a hiring decision")
        return normalized


def _question_count(value: str) -> int:
    clauses = [clause.strip() for clause in _SENTENCE_SPLIT.split(value)]
    explicit = sum(1 for clause in clauses[:-1] if clause)
    return explicit if explicit else 1


def _normalize(value: str) -> str:
    return _WHITESPACE.sub(" ", value).strip()
