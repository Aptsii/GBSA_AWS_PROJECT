from __future__ import annotations

from interview_evidence.interview_engine.domain.session import SessionState
from interview_evidence.interview_engine.repositories.postgres import InterviewSessionRepository
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import OpaqueId
from interview_evidence.shared.tenant import TenantContext, ensure_company_scope


class InterviewEvidencePublicService:
    __slots__ = ("_repository",)

    def __init__(self, repository: InterviewSessionRepository) -> None:
        self._repository = repository

    def get_completed_session_snapshot(
        self,
        context: TenantContext,
        *,
        session_id: str | OpaqueId,
    ) -> dict[str, object]:
        ensure_company_scope(context, context.company_id)
        session = self._repository.get_session_for_company(context, session_id)
        if session.state not in {
            SessionState.COMPLETED,
            SessionState.REPORT_GENERATING,
            SessionState.REVIEWABLE,
        }:
            raise SafeApplicationError(ErrorCode.CONFLICT)
        if session.completed_at is None:
            raise SafeApplicationError(ErrorCode.CONFLICT)
        turns = self._repository.list_turns(
            context,
            session.scope,
            session.interview_session_id,
        )
        chunks = self._repository.list_recording_chunks(
            context,
            session.scope,
            session.interview_session_id,
        )
        checkpoints = self._repository.list_checkpoints(
            context,
            session.scope,
            session.interview_session_id,
        )
        return {
            "company_id": str(session.company_id),
            "applicant_id": str(session.scope.applicant_id),
            "invitation_id": str(session.scope.invitation_id),
            "interview_session_id": str(session.interview_session_id),
            "competency_model_version_id": str(session.competency_model_version_id),
            "state": session.state.value,
            "completed_at": session.completed_at.isoformat().replace("+00:00", "Z"),
            "turns": [
                {
                    "turn_id": str(turn.turn_id),
                    "sequence": turn.sequence,
                    "speaker": turn.speaker.value,
                    "status": turn.status.value,
                    "text": turn.text.reveal() if turn.text is not None else None,
                    "target_criterion_id": (
                        str(turn.target_criterion_id)
                        if turn.target_criterion_id is not None
                        else None
                    ),
                    "model_config_version": turn.model_config_version,
                    "finalized_at": (
                        turn.finalized_at.isoformat().replace("+00:00", "Z")
                        if turn.finalized_at is not None
                        else None
                    ),
                }
                for turn in turns
            ],
            "recording_chunks": [
                {
                    "recording_chunk_id": str(chunk.recording_chunk_id),
                    "sequence": chunk.sequence,
                    "object_key": chunk.object_key,
                    "content_hash": chunk.content_hash,
                    "byte_size": chunk.byte_size,
                    "session_start_ms": chunk.session_start_ms,
                    "session_end_ms": chunk.session_end_ms,
                    "upload_status": chunk.upload_status.value,
                }
                for chunk in chunks
            ],
            "checkpoints": [
                {
                    "checkpoint_id": str(checkpoint.checkpoint_id),
                    "session_sequence": checkpoint.session_sequence,
                    "last_final_turn_id": (
                        str(checkpoint.last_final_turn_id)
                        if checkpoint.last_final_turn_id is not None
                        else None
                    ),
                    "last_media_chunk_sequence": checkpoint.last_media_chunk_sequence,
                }
                for checkpoint in checkpoints
            ],
        }
