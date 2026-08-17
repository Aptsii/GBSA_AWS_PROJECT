"""Answer-finalization to next-question interview orchestration."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from interview_evidence.interview_engine.adapters.polly import (
    SpeechSynthesis,
    SpeechSynthesizer,
)
from interview_evidence.interview_engine.adapters.retrieval_client import RetrievalClient
from interview_evidence.interview_engine.adapters.transcribe import StreamingTranscriber
from interview_evidence.interview_engine.application.checkpoints import (
    CheckpointService,
    ResumeSnapshot,
)
from interview_evidence.interview_engine.application.context_builder import ContextBuilder
from interview_evidence.interview_engine.application.idempotency import ScopedIdempotencyStore
from interview_evidence.interview_engine.application.question_generator import QuestionGenerator
from interview_evidence.interview_engine.application.question_policy import QuestionPolicy
from interview_evidence.interview_engine.application.state_machine import SessionStateMachine
from interview_evidence.interview_engine.domain.session import InterviewSession, SessionState
from interview_evidence.interview_engine.domain.turn import Turn, TurnSpeaker, TurnStatus
from interview_evidence.shared.aws_clients.ports import ProtectedText
from interview_evidence.shared.ids import Clock, OpaqueId, SystemClock, UUID7Generator
from interview_evidence.shared.tenant import ApplicantScope, TenantContext, ensure_applicant_scope


@dataclass(frozen=True, slots=True)
class SessionStartResult:
    session: InterviewSession
    protocol_version: str = "1.0"


@dataclass(frozen=True, slots=True)
class NextQuestionResult:
    session: InterviewSession
    answer_turn: Turn
    question_turn: Turn
    speech: SpeechSynthesis
    source_reference_count: int
    transcript_review_required: bool


class InterviewService:
    __slots__ = (
        "_checkpoints",
        "_clock",
        "_context_builder",
        "_id_generator",
        "_idempotency",
        "_policy",
        "_question_generator",
        "_retrieval",
        "_sessions",
        "_speech",
        "_state_machine",
        "_transcriber",
        "_turns",
    )

    def __init__(
        self,
        *,
        retrieval: RetrievalClient,
        question_generator: QuestionGenerator | None = None,
        question_policy: QuestionPolicy | None = None,
        speech: SpeechSynthesizer | None = None,
        transcriber: StreamingTranscriber | None = None,
        context_builder: ContextBuilder | None = None,
        checkpoints: CheckpointService | None = None,
        idempotency: ScopedIdempotencyStore | None = None,
        clock: Clock | None = None,
        id_generator: UUID7Generator | None = None,
    ) -> None:
        self._clock = clock or SystemClock()
        self._id_generator = id_generator or UUID7Generator(self._clock)
        self._retrieval = retrieval
        self._question_generator = question_generator or QuestionGenerator()
        self._policy = question_policy or QuestionPolicy()
        self._speech = speech or SpeechSynthesizer(
            clock=self._clock, id_generator=self._id_generator
        )
        self._transcriber = transcriber or StreamingTranscriber()
        self._context_builder = context_builder or ContextBuilder()
        self._checkpoints = checkpoints or CheckpointService(
            clock=self._clock, id_generator=self._id_generator
        )
        self._idempotency = idempotency or ScopedIdempotencyStore()
        self._state_machine = SessionStateMachine(self._clock)
        self._sessions: dict[tuple[OpaqueId, OpaqueId, OpaqueId, OpaqueId], InterviewSession] = {}
        self._turns: dict[tuple[OpaqueId, OpaqueId, OpaqueId, OpaqueId], list[Turn]] = {}

    @property
    def clock(self) -> Clock:
        return self._clock

    @property
    def id_generator(self) -> UUID7Generator:
        return self._id_generator

    def create_session(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        *,
        interview_strategy_id: str | OpaqueId,
        competency_model_version_id: str | OpaqueId,
        idempotency_key: str,
    ) -> SessionStartResult:
        ensure_applicant_scope(context, scope)

        def create() -> SessionStartResult:
            interview_session = InterviewSession(
                interview_session_id=self._id_generator.new(),
                scope=scope,
                interview_strategy_id=OpaqueId(interview_strategy_id),
                competency_model_version_id=OpaqueId(competency_model_version_id),
                state=SessionState.PREPARING,
                session_sequence=0,
                row_version=1,
                created_at=self._clock.now(),
            )
            key = (*_scope_key(scope), interview_session.interview_session_id)
            self._sessions[key] = interview_session
            self._turns[key] = []
            return SessionStartResult(interview_session)

        return self._idempotency.execute(
            context,
            scope,
            idempotency_key,
            {
                "interview_strategy_id": str(OpaqueId(interview_strategy_id)),
                "competency_model_version_id": str(OpaqueId(competency_model_version_id)),
            },
            create,
            namespace="session-create",
        )

    def start(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        session_id: str | OpaqueId,
        *,
        expected_sequence: int,
    ) -> InterviewSession:
        interview_session = self.get_session(context, scope, session_id)
        started = self._state_machine.transition(
            interview_session,
            expected_sequence=expected_sequence,
            target=SessionState.IN_PROGRESS,
        )
        awaiting = self._state_machine.transition(
            started,
            expected_sequence=started.session_sequence,
            target=SessionState.AWAITING_ANSWER,
        )
        self._store_session(scope, awaiting)
        self._checkpoints.record(
            context,
            scope,
            awaiting.interview_session_id,
            session_sequence=awaiting.session_sequence,
            last_final_turn_id=None,
            last_media_chunk_sequence=0,
            state=awaiting.state,
        )
        return awaiting

    def finalize_answer(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        session_id: str | OpaqueId,
        *,
        expected_sequence: int,
        answer_turn_id: str | OpaqueId,
        transcript_text: str,
        transcript_confidence: float,
        criterion_id: str | OpaqueId,
        criterion_name: str,
        remaining_criteria: Sequence[Mapping[str, object]],
        idempotency_key: str,
        last_recording_chunk_sequence: int = 0,
        summary: str | None = None,
    ) -> NextQuestionResult:
        ensure_applicant_scope(context, scope)
        checked_session_id = OpaqueId(session_id)
        checked_answer_turn_id = OpaqueId(answer_turn_id)

        def finalize() -> NextQuestionResult:
            interview_session = self.get_session(context, scope, checked_session_id)
            if interview_session.state is not SessionState.AWAITING_ANSWER:
                raise ValueError("session is not awaiting an answer")
            if interview_session.session_sequence != expected_sequence:
                raise ValueError("stale session sequence")
            transcript = self._transcriber.result(
                transcript_text, confidence=transcript_confidence, is_final=True
            )
            turns = self._turn_list(scope, checked_session_id)
            answer_turn = Turn(
                turn_id=checked_answer_turn_id,
                company_id=scope.company_id,
                interview_session_id=checked_session_id,
                sequence=len(turns) + 1,
                speaker=TurnSpeaker.APPLICANT,
                status=TurnStatus.FINAL,
                text=transcript.text,
                idempotency_key=idempotency_key,
                finalized_at=self._clock.now(),
                created_at=self._clock.now(),
            )
            turns.append(answer_turn)
            preparing = self._state_machine.transition(
                interview_session,
                expected_sequence=expected_sequence,
                target=SessionState.PREPARING_QUESTION,
            )
            recent_turns = tuple(_turn_context(turn) for turn in turns)
            built_context = self._context_builder.build(
                context,
                scope,
                checked_session_id,
                summary=summary,
                recent_turns=recent_turns,
                remaining_criteria=remaining_criteria,
            )
            retrieval = self._retrieval.retrieve(
                context,
                query=transcript.text.reveal(),
                scope=scope,
                criterion_id=criterion_id,
                interview_session_id=checked_session_id,
            )
            generated = self._question_generator.generate(
                context,
                built_context,
                criterion_id=criterion_id,
                criterion_name=criterion_name,
                retrieval=retrieval,
            )
            previous_questions = tuple(
                turn.text.reveal()
                for turn in turns
                if turn.speaker is TurnSpeaker.INTERVIEWER and turn.text is not None
            )
            question_text = self._policy.validate(
                generated.text.reveal(),
                criterion_id=str(generated.target_criterion_id),
                expected_criterion_id=str(OpaqueId(criterion_id)),
                previous_questions=previous_questions,
            )
            question_turn = Turn(
                turn_id=self._id_generator.new(),
                company_id=scope.company_id,
                interview_session_id=checked_session_id,
                sequence=len(turns) + 1,
                speaker=TurnSpeaker.INTERVIEWER,
                status=TurnStatus.PRESENTED,
                text=ProtectedText(question_text),
                target_criterion_id=generated.target_criterion_id,
                model_config_version=generated.model_config_version,
                idempotency_key=str(self._id_generator.new()),
                created_at=self._clock.now(),
            )
            turns.append(question_turn)
            speech = self._speech.synthesize(context, scope.company_id, question_text)
            awaiting = self._state_machine.transition(
                preparing,
                expected_sequence=preparing.session_sequence,
                target=SessionState.AWAITING_ANSWER,
            )
            for mode in (generated.degraded_mode, speech.degraded_mode):
                if mode != "none":
                    awaiting = awaiting.with_degraded_mode(mode)
            self._store_session(scope, awaiting)
            self._checkpoints.record(
                context,
                scope,
                checked_session_id,
                session_sequence=awaiting.session_sequence,
                last_final_turn_id=answer_turn.turn_id,
                last_media_chunk_sequence=last_recording_chunk_sequence,
                pending_turn_id=question_turn.turn_id,
                state=awaiting.state,
                degraded_modes=awaiting.degraded_modes,
            )
            return NextQuestionResult(
                session=awaiting,
                answer_turn=answer_turn,
                question_turn=question_turn,
                speech=speech,
                source_reference_count=len(generated.source_references),
                transcript_review_required=transcript.review_required,
            )

        return self._idempotency.execute(
            context,
            scope,
            idempotency_key,
            {
                "session_id": str(checked_session_id),
                "expected_sequence": expected_sequence,
                "answer_turn_id": str(checked_answer_turn_id),
                "transcript_digest": _text_digest(transcript_text),
                "criterion_id": str(OpaqueId(criterion_id)),
                "last_recording_chunk_sequence": last_recording_chunk_sequence,
            },
            finalize,
            namespace="answer-complete",
        )

    def get_session(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        session_id: str | OpaqueId,
    ) -> InterviewSession:
        ensure_applicant_scope(context, scope)
        key = (*_scope_key(scope), OpaqueId(session_id))
        try:
            return self._sessions[key]
        except KeyError:
            raise LookupError("interview session was not found") from None

    def list_turns(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        session_id: str | OpaqueId,
    ) -> tuple[Turn, ...]:
        self.get_session(context, scope, session_id)
        return tuple(self._turn_list(scope, OpaqueId(session_id)))

    def resume(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        session_id: str | OpaqueId,
        *,
        client_sequence: int,
    ) -> ResumeSnapshot:
        self.get_session(context, scope, session_id)
        return self._checkpoints.resume(context, scope, session_id, client_sequence=client_sequence)

    def _store_session(self, scope: ApplicantScope, interview_session: InterviewSession) -> None:
        self._sessions[(*_scope_key(scope), interview_session.interview_session_id)] = (
            interview_session
        )

    def _turn_list(self, scope: ApplicantScope, session_id: OpaqueId) -> list[Turn]:
        return self._turns.setdefault((*_scope_key(scope), session_id), [])


def _scope_key(scope: ApplicantScope) -> tuple[OpaqueId, OpaqueId, OpaqueId]:
    return scope.company_id, scope.applicant_id, scope.invitation_id


def _turn_context(turn: Turn) -> dict[str, object]:
    if turn.text is None:
        raise ValueError("context Turn must have text")
    return {
        "turn_id": str(turn.turn_id),
        "speaker": turn.speaker.value,
        "text": turn.text,
    }


def _text_digest(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode()).hexdigest()
