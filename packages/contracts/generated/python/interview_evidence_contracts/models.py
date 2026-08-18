"""Generated contract types. DO NOT EDIT.

Run packages/contracts/scripts/generate_contracts.py instead.
"""

from __future__ import annotations

from typing import Any, Literal, NotRequired, Required, TypeAlias, TypedDict


class ErrorEnvelopeErrorsItem(TypedDict, total=False):
    field: Required[str]
    code: Required[str]

class ErrorEnvelope(TypedDict, total=False):
    type: Required[str]
    title: Required[str]
    status: Required[int]
    code: Required[str]
    detail: NotRequired[str]
    request_id: Required[str]
    retryable: Required[bool]
    current_version: NotRequired[int]
    errors: NotRequired[list[ErrorEnvelopeErrorsItem]]

class CompanyUserView(TypedDict, total=False):
    company_user_id: Required[str]
    company_id: Required[str]
    email: Required[str]
    status: Required[Literal['invited', 'active', 'disabled']]

class PositionCreate(TypedDict, total=False):
    title: Required[str]
    description: Required[str]

class Position(TypedDict, total=False):
    title: Required[str]
    description: Required[str]
    position_id: Required[str]
    status: Required[Literal['draft', 'active', 'closed']]
    row_version: Required[int]
    created_at: Required[str]

class PositionPageItemsItem(TypedDict, total=False):
    title: Required[str]
    description: Required[str]
    position_id: Required[str]
    status: Required[Literal['draft', 'active', 'closed']]
    row_version: Required[int]
    created_at: Required[str]

class PositionPage(TypedDict, total=False):
    items: Required[list[PositionPageItemsItem]]
    next_cursor: NotRequired[str | None]

class EvaluationCriterionInput(TypedDict, total=False):
    code: Required[str]
    name: Required[str]
    description: Required[str]
    weight: Required[float]
    good_evidence: Required[dict[str, Any]]
    weak_evidence: Required[dict[str, Any]]
    abstain_guidance: Required[str]
    common_questions: NotRequired[list[str]]
    required: Required[bool]

class CompetencyModelVersionCreateCriteriaItem(TypedDict, total=False):
    code: Required[str]
    name: Required[str]
    description: Required[str]
    weight: Required[float]
    good_evidence: Required[dict[str, Any]]
    weak_evidence: Required[dict[str, Any]]
    abstain_guidance: Required[str]
    common_questions: NotRequired[list[str]]
    required: Required[bool]

class CompetencyModelVersionCreate(TypedDict, total=False):
    criteria: Required[list[CompetencyModelVersionCreateCriteriaItem]]
    prohibited_topics: Required[list[str]]
    interview_duration_minutes: Required[int]
    persona_definition: Required[dict[str, Any]]

class CompetencyModelVersionCriteriaItem(TypedDict, total=False):
    code: Required[str]
    name: Required[str]
    description: Required[str]
    weight: Required[float]
    good_evidence: Required[dict[str, Any]]
    weak_evidence: Required[dict[str, Any]]
    abstain_guidance: Required[str]
    common_questions: NotRequired[list[str]]
    required: Required[bool]

class CompetencyModelVersion(TypedDict, total=False):
    criteria: Required[list[CompetencyModelVersionCriteriaItem]]
    prohibited_topics: Required[list[str]]
    interview_duration_minutes: Required[int]
    persona_definition: Required[dict[str, Any]]
    competency_model_version_id: Required[str]
    position_id: Required[str]
    version_number: Required[int]
    status: Required[Literal['draft', 'published', 'retired']]
    row_version: Required[int]
    published_at: NotRequired[str | None]

class CampaignCreate(TypedDict, total=False):
    position_id: Required[str]
    competency_model_version_id: Required[str]
    name: Required[str]
    candidate_instructions: Required[str]

class Campaign(TypedDict, total=False):
    position_id: Required[str]
    competency_model_version_id: Required[str]
    name: Required[str]
    candidate_instructions: Required[str]
    campaign_id: Required[str]
    status: Required[Literal['draft', 'published', 'closed']]
    row_version: Required[int]
    published_at: NotRequired[str | None]

class InvitationBatchCreateApplicantsItem(TypedDict, total=False):
    email: Required[str]
    display_name: Required[str]

class InvitationBatchCreate(TypedDict, total=False):
    applicants: Required[list[InvitationBatchCreateApplicantsItem]]
    expires_at: Required[str]

class InvitationView(TypedDict, total=False):
    invitation_id: Required[str]
    campaign_id: Required[str]
    applicant_email: Required[str]
    status: Required[Literal['invited', 'identity_verified', 'consented', 'materials_submitted', 'analyzing', 'ready', 'interviewing', 'interrupted', 'completed', 'reviewed', 'expired', 'revoked', 'deleted']]
    expires_at: Required[str]
    row_version: Required[int]
    analysis_status: NotRequired[str | None]
    interview_status: NotRequired[str | None]
    report_status: NotRequired[str | None]

class InvitationPageItemsItem(TypedDict, total=False):
    invitation_id: Required[str]
    campaign_id: Required[str]
    applicant_email: Required[str]
    status: Required[Literal['invited', 'identity_verified', 'consented', 'materials_submitted', 'analyzing', 'ready', 'interviewing', 'interrupted', 'completed', 'reviewed', 'expired', 'revoked', 'deleted']]
    expires_at: Required[str]
    row_version: Required[int]
    analysis_status: NotRequired[str | None]
    interview_status: NotRequired[str | None]
    report_status: NotRequired[str | None]

class InvitationPage(TypedDict, total=False):
    items: Required[list[InvitationPageItemsItem]]
    next_cursor: NotRequired[str | None]

class InvitationBatchResultInvitationsItem(TypedDict, total=False):
    invitation_id: Required[str]
    campaign_id: Required[str]
    applicant_email: Required[str]
    status: Required[Literal['invited', 'identity_verified', 'consented', 'materials_submitted', 'analyzing', 'ready', 'interviewing', 'interrupted', 'completed', 'reviewed', 'expired', 'revoked', 'deleted']]
    expires_at: Required[str]
    row_version: Required[int]
    analysis_status: NotRequired[str | None]
    interview_status: NotRequired[str | None]
    report_status: NotRequired[str | None]

class InvitationBatchResult(TypedDict, total=False):
    accepted_count: Required[int]
    rejected_count: Required[int]
    invitations: Required[list[InvitationBatchResultInvitationsItem]]

class ApplicantTokenExchange(TypedDict, total=False):
    invitation_token: Required[str]

class ApplicantIdentityVerification(TypedDict, total=False):
    display_name: Required[str]
    verification_value: Required[str]

class ApplicantAccessState(TypedDict, total=False):
    invitation_id: Required[str]
    state: Required[str]
    expires_at: Required[str]
    required_actions: Required[list[str]]

class ConsentCreate(TypedDict, total=False):
    policy_version: Required[str]
    accepted_purposes: Required[list[Literal['document_analysis', 'recording', 'ai_assessment']]]
    consent_content_digest: Required[str]

class ConsentView(TypedDict, total=False):
    consent_record_id: Required[str]
    policy_version: Required[str]
    accepted_purposes: Required[list[str]]
    retention_days: Required[int]
    accepted_at: Required[str]

class UploadIntentCreate(TypedDict, total=False):
    source_type: Required[Literal['cover_letter', 'resume', 'pdf']]
    filename: Required[str]
    media_type: Required[str]
    byte_size: Required[int]
    sha256: Required[str]

class UploadIntent(TypedDict, total=False):
    upload_id: Required[str]
    method: Required[Literal['PUT']]
    url: Required[str]
    required_headers: Required[dict[str, Any]]
    expires_at: Required[str]

class SubmissionCreateOption1(TypedDict, total=False):
    source_type: Required[Literal['cover_letter', 'resume', 'pdf']]
    upload_id: Required[str]

class SubmissionCreateOption2(TypedDict, total=False):
    source_type: Required[Literal['public_git', 'public_url']]
    public_url: Required[str]
    candidate_identity_inputs: NotRequired[dict[str, Any]]

class SubmissionView(TypedDict, total=False):
    submission_id: Required[str]
    source_type: Required[str]
    status: Required[Literal['received', 'validating', 'analyzing', 'ready', 'partial', 'failed', 'deleted']]
    failure_code: NotRequired[str | None]
    impact_summary: NotRequired[str | None]
    created_at: Required[str]

class AnalysisReadinessSubmissionsItem(TypedDict, total=False):
    submission_id: Required[str]
    source_type: Required[str]
    status: Required[Literal['received', 'validating', 'analyzing', 'ready', 'partial', 'failed', 'deleted']]
    failure_code: NotRequired[str | None]
    impact_summary: NotRequired[str | None]
    created_at: Required[str]

class AnalysisReadiness(TypedDict, total=False):
    overall_status: Required[Literal['waiting', 'analyzing', 'ready', 'partial', 'failed']]
    submissions: Required[list[AnalysisReadinessSubmissionsItem]]
    interview_ready: Required[bool]
    strategy_id: NotRequired[str | None]
    strategy_version: NotRequired[int | None]
    impact_summary: NotRequired[str | None]

class EquipmentCheckCreateCamera(TypedDict, total=False):
    status: Required[Literal['ready', 'warning', 'failed']]
    sanitized_code: NotRequired[str | None]

class EquipmentCheckCreateMicrophone(TypedDict, total=False):
    status: Required[Literal['ready', 'warning', 'failed']]
    sanitized_code: NotRequired[str | None]

class EquipmentCheckCreateNetwork(TypedDict, total=False):
    status: Required[Literal['ready', 'warning', 'failed']]
    sanitized_code: NotRequired[str | None]

class EquipmentCheckCreate(TypedDict, total=False):
    camera: Required[EquipmentCheckCreateCamera]
    microphone: Required[EquipmentCheckCreateMicrophone]
    network: Required[EquipmentCheckCreateNetwork]

class EquipmentComponent(TypedDict, total=False):
    status: Required[Literal['ready', 'warning', 'failed']]
    sanitized_code: NotRequired[str | None]

class EquipmentCheckCamera(TypedDict, total=False):
    status: Required[Literal['ready', 'warning', 'failed']]
    sanitized_code: NotRequired[str | None]

class EquipmentCheckMicrophone(TypedDict, total=False):
    status: Required[Literal['ready', 'warning', 'failed']]
    sanitized_code: NotRequired[str | None]

class EquipmentCheckNetwork(TypedDict, total=False):
    status: Required[Literal['ready', 'warning', 'failed']]
    sanitized_code: NotRequired[str | None]

class EquipmentCheck(TypedDict, total=False):
    camera: Required[EquipmentCheckCamera]
    microphone: Required[EquipmentCheckMicrophone]
    network: Required[EquipmentCheckNetwork]
    equipment_check_id: Required[str]
    overall_status: Required[Literal['ready', 'warning', 'failed']]
    checked_at: Required[str]

class InterviewSessionCreate(TypedDict, total=False):
    equipment_check_id: Required[str]
    strategy_id: Required[str]
    acknowledged_partial_analysis: Required[bool]

class InterviewSessionView(TypedDict, total=False):
    interview_session_id: Required[str]
    state: Required[Literal['preparing', 'in_progress', 'awaiting_answer', 'preparing_question', 'paused', 'completed', 'report_generating', 'reviewable']]
    session_sequence: Required[int]
    websocket_path: Required[str]
    protocol_version: Required[Literal['1.0']]

class InterviewResumeSnapshot(TypedDict, total=False):
    interview_session_id: Required[str]
    state: Required[str]
    server_sequence: Required[int]
    last_final_turn_id: NotRequired[str | None]
    pending_turn: NotRequired[dict[str, Any] | None]
    last_verified_recording_chunk_sequence: Required[int]
    degraded_modes: NotRequired[list[str]]

class RecordingUploadIntentCreate(TypedDict, total=False):
    chunk_sequence: Required[int]
    byte_size: Required[int]
    sha256: Required[str]
    session_start_ms: Required[int]
    session_end_ms: Required[int]

class EvidenceView(TypedDict, total=False):
    evidence_id: Required[str]
    answer_turn_id: Required[str]
    transcript_segment_id: Required[str]
    video_start_ms: Required[int]
    video_end_ms: Required[int]
    observation: Required[str]
    rationale: Required[str]
    sufficiency: Required[Literal['direct', 'supporting', 'weak']]

class ReportItemViewEvidenceItem(TypedDict, total=False):
    evidence_id: Required[str]
    answer_turn_id: Required[str]
    transcript_segment_id: Required[str]
    video_start_ms: Required[int]
    video_end_ms: Required[int]
    observation: Required[str]
    rationale: Required[str]
    sufficiency: Required[Literal['direct', 'supporting', 'weak']]

class ReportItemView(TypedDict, total=False):
    report_item_id: Required[str]
    criterion_id: Required[str]
    assessment_state: Required[Literal['confirmed', 'partially_confirmed', 'insufficient_evidence', 'needs_follow_up']]
    observation: Required[str]
    rationale: Required[str]
    uncertainty: Required[str]
    follow_up_question: NotRequired[str | None]
    evidence: Required[list[ReportItemViewEvidenceItem]]

class ReportViewItemsItemEvidenceItem(TypedDict, total=False):
    evidence_id: Required[str]
    answer_turn_id: Required[str]
    transcript_segment_id: Required[str]
    video_start_ms: Required[int]
    video_end_ms: Required[int]
    observation: Required[str]
    rationale: Required[str]
    sufficiency: Required[Literal['direct', 'supporting', 'weak']]

class ReportViewItemsItem(TypedDict, total=False):
    report_item_id: Required[str]
    criterion_id: Required[str]
    assessment_state: Required[Literal['confirmed', 'partially_confirmed', 'insufficient_evidence', 'needs_follow_up']]
    observation: Required[str]
    rationale: Required[str]
    uncertainty: Required[str]
    follow_up_question: NotRequired[str | None]
    evidence: Required[list[ReportViewItemsItemEvidenceItem]]

class ReportViewHumanReviewsItem(TypedDict, total=False):
    human_review_id: Required[str]
    review_type: Required[Literal['assessment_override', 'note', 'bookmark', 'final_decision']]
    created_by: Required[str]
    created_at: Required[str]

class ReportView(TypedDict, total=False):
    report_id: Required[str]
    report_version: Required[int]
    status: Required[Literal['generating', 'ready', 'partial', 'failed']]
    summary: Required[str]
    items: Required[list[ReportViewItemsItem]]
    ai_original_immutable: Required[Literal[True]]
    human_reviews: NotRequired[list[ReportViewHumanReviewsItem]]

class TimelineViewEntriesItem(TypedDict, total=False):
    entry_id: Required[str]
    entry_type: Required[Literal['question', 'answer', 'event', 'evidence']]
    start_ms: Required[int]
    end_ms: Required[int]
    text: NotRequired[str | None]
    technical_failure: NotRequired[bool]

class TimelineViewPlayback(TypedDict, total=False):
    url: Required[str | None]
    expires_at: Required[str | None]
    status: Required[Literal['ready', 'partial', 'processing', 'unavailable']]

class TimelineView(TypedDict, total=False):
    entries: Required[list[TimelineViewEntriesItem]]
    playback: Required[TimelineViewPlayback]

class HumanAssessmentReviewCreate(TypedDict, total=False):
    assessment_state: Required[Literal['confirmed', 'partially_confirmed', 'insufficient_evidence', 'needs_follow_up']]
    reason: Required[str]

class ReviewArtifactCreate(TypedDict, total=False):
    review_type: Required[Literal['note', 'bookmark']]
    target_id: Required[str]
    value: Required[str]

class FinalDecisionCreate(TypedDict, total=False):
    decision: Required[Literal['advance', 'reject', 'hold', 'withdrawn']]
    reason: Required[str]

class HumanReviewView(TypedDict, total=False):
    human_review_id: Required[str]
    review_type: Required[Literal['assessment_override', 'note', 'bookmark', 'final_decision']]
    created_by: Required[str]
    created_at: Required[str]

class DeletionRequestCreate(TypedDict, total=False):
    scope_type: Required[Literal['invitation', 'applicant']]
    scope_id: Required[str]
    reason: Required[str]

class DeletionTargetView(TypedDict, total=False):
    target_id: Required[str]
    owner_lane: Required[Literal['A', 'B', 'C', 'D']]
    store: Required[Literal['aurora', 'dynamodb', 's3', 'opensearch']]
    target_type: Required[str]
    status: Required[Literal['pending', 'deleting', 'retrying', 'failed', 'verified_absent']]
    attempts: Required[int]
    verified_at: NotRequired[str | None]
    error_code: NotRequired[str | None]

class DeletionStatusTargetsItem(TypedDict, total=False):
    target_id: Required[str]
    owner_lane: Required[Literal['A', 'B', 'C', 'D']]
    store: Required[Literal['aurora', 'dynamodb', 's3', 'opensearch']]
    target_type: Required[str]
    status: Required[Literal['pending', 'deleting', 'retrying', 'failed', 'verified_absent']]
    attempts: Required[int]
    verified_at: NotRequired[str | None]
    error_code: NotRequired[str | None]

class DeletionStatus(TypedDict, total=False):
    deletion_request_id: Required[str]
    manifest_id: Required[str]
    status: Required[Literal['requested', 'enumerating', 'deleting', 'verifying', 'retrying', 'partially_completed', 'completed']]
    expected_targets: Required[int]
    verified_targets: Required[int]
    targets: Required[list[DeletionStatusTargetsItem]]

class ProcessingStatus(TypedDict, total=False):
    status: Required[Literal['queued', 'running', 'partial', 'failed']]
    retryable: NotRequired[bool]
    message: NotRequired[str | None]

class SessionStartMessagePayload(TypedDict, total=False):
    equipment_check_id: Required[str]
    expected_state: Required[Literal['preparing']]

class SessionStartMessage(TypedDict, total=False):
    protocol_version: Required[Literal['1.0']]
    message_type: Required[Literal['session.start']]
    session_id: Required[str]
    sequence: Required[int]
    idempotency_key: Required[str]
    correlation_id: Required[str]
    sent_at: Required[str]
    payload: Required[SessionStartMessagePayload]

class AudioChunkBeginMessagePayload(TypedDict, total=False):
    answer_turn_id: Required[str]
    chunk_sequence: Required[int]
    codec: Required[Literal['pcm_s16le', 'opus']]
    sample_rate_hz: Required[int]
    channel_count: Required[int]
    byte_length: Required[int]
    sha256: Required[str]

class AudioChunkBeginMessage(TypedDict, total=False):
    protocol_version: Required[Literal['1.0']]
    message_type: Required[Literal['audio.chunk.begin']]
    session_id: Required[str]
    sequence: Required[int]
    idempotency_key: Required[str]
    correlation_id: Required[str]
    sent_at: Required[str]
    payload: Required[AudioChunkBeginMessagePayload]

class AnswerTextSubmitMessagePayload(TypedDict, total=False):
    answer_turn_id: Required[str]
    text: Required[str]

class AnswerTextSubmitMessage(TypedDict, total=False):
    protocol_version: Required[Literal['1.0']]
    message_type: Required[Literal['answer.text.submit']]
    session_id: Required[str]
    sequence: Required[int]
    idempotency_key: Required[str]
    correlation_id: Required[str]
    sent_at: Required[str]
    payload: Required[AnswerTextSubmitMessagePayload]

class AnswerCompleteMessagePayload(TypedDict, total=False):
    answer_turn_id: Required[str]
    last_audio_chunk_sequence: Required[int]
    last_recording_chunk_sequence: Required[int]
    expected_state: Required[Literal['awaiting_answer']]

class AnswerCompleteMessage(TypedDict, total=False):
    protocol_version: Required[Literal['1.0']]
    message_type: Required[Literal['answer.complete']]
    session_id: Required[str]
    sequence: Required[int]
    idempotency_key: Required[str]
    correlation_id: Required[str]
    sent_at: Required[str]
    payload: Required[AnswerCompleteMessagePayload]

class QuestionRepeatMessagePayload(TypedDict, total=False):
    question_turn_id: Required[str]
    mode: Required[Literal['repeat_or_clarify']]

class QuestionRepeatMessage(TypedDict, total=False):
    protocol_version: Required[Literal['1.0']]
    message_type: Required[Literal['question.repeat']]
    session_id: Required[str]
    sequence: Required[int]
    idempotency_key: Required[str]
    correlation_id: Required[str]
    sent_at: Required[str]
    payload: Required[QuestionRepeatMessagePayload]

class SessionResumeMessagePayload(TypedDict, total=False):
    last_applied_server_sequence: Required[int]
    last_final_turn_id: Required[str | None]
    last_uploaded_recording_chunk_sequence: Required[int]

class SessionResumeMessage(TypedDict, total=False):
    protocol_version: Required[Literal['1.0']]
    message_type: Required[Literal['session.resume']]
    session_id: Required[str]
    sequence: Required[int]
    idempotency_key: Required[str]
    correlation_id: Required[str]
    sent_at: Required[str]
    payload: Required[SessionResumeMessagePayload]

class ClientAckMessagePayload(TypedDict, total=False):
    server_event_id: Required[str]
    applied_sequence: Required[int]

class ClientAckMessage(TypedDict, total=False):
    protocol_version: Required[Literal['1.0']]
    message_type: Required[Literal['client.ack']]
    session_id: Required[str]
    sequence: Required[int]
    idempotency_key: Required[str]
    correlation_id: Required[str]
    sent_at: Required[str]
    payload: Required[ClientAckMessagePayload]

class HeartbeatPingMessagePayload(TypedDict, total=False):
    client_monotonic_ms: Required[float]

class HeartbeatPingMessage(TypedDict, total=False):
    protocol_version: Required[Literal['1.0']]
    message_type: Required[Literal['heartbeat.ping']]
    session_id: Required[str]
    sequence: Required[int]
    idempotency_key: Required[str]
    correlation_id: Required[str]
    sent_at: Required[str]
    payload: Required[HeartbeatPingMessagePayload]

class SessionStateChangedMessagePayload(TypedDict, total=False):
    previous_state: Required[str]
    state: Required[str]
    reason_code: Required[str]
    checkpoint_id: Required[str]

class SessionStateChangedMessage(TypedDict, total=False):
    protocol_version: Required[Literal['1.0']]
    message_type: Required[Literal['session.state_changed']]
    session_id: Required[str]
    sequence: Required[int]
    idempotency_key: Required[str]
    correlation_id: Required[str]
    sent_at: Required[str]
    payload: Required[SessionStateChangedMessagePayload]

class TranscriptPartialMessagePayload(TypedDict, total=False):
    answer_turn_id: Required[str]
    segment_sequence: Required[int]
    text: Required[str]
    start_ms: Required[int]
    end_ms: Required[int]
    confidence: Required[float]
    is_final: Required[Literal[False]]

class TranscriptPartialMessage(TypedDict, total=False):
    protocol_version: Required[Literal['1.0']]
    message_type: Required[Literal['transcript.partial']]
    session_id: Required[str]
    sequence: Required[int]
    idempotency_key: Required[str]
    correlation_id: Required[str]
    sent_at: Required[str]
    payload: Required[TranscriptPartialMessagePayload]

class TranscriptFinalMessagePayload(TypedDict, total=False):
    answer_turn_id: Required[str]
    transcript_segment_id: Required[str]
    segment_sequence: Required[int]
    text: Required[str]
    start_ms: Required[int]
    end_ms: Required[int]
    confidence: Required[float]
    is_final: Required[Literal[True]]
    review_required: Required[bool]

class TranscriptFinalMessage(TypedDict, total=False):
    protocol_version: Required[Literal['1.0']]
    message_type: Required[Literal['transcript.final']]
    session_id: Required[str]
    sequence: Required[int]
    idempotency_key: Required[str]
    correlation_id: Required[str]
    sent_at: Required[str]
    payload: Required[TranscriptFinalMessagePayload]

class QuestionPreparingMessagePayload(TypedDict, total=False):
    stage: Required[Literal['retrieval', 'generation', 'policy', 'speech']]
    degraded_mode: Required[Literal['none', 'search_fallback', 'text_only']]

class QuestionPreparingMessage(TypedDict, total=False):
    protocol_version: Required[Literal['1.0']]
    message_type: Required[Literal['question.preparing']]
    session_id: Required[str]
    sequence: Required[int]
    idempotency_key: Required[str]
    correlation_id: Required[str]
    sent_at: Required[str]
    payload: Required[QuestionPreparingMessagePayload]

class QuestionReadyMessagePayload(TypedDict, total=False):
    question_turn_id: Required[str]
    text: Required[str]
    target_criterion_id: Required[str]
    audio_url: Required[str | None]
    audio_expires_at: Required[str | None]
    speech_marks_url: Required[str | None]
    source_reference_count: Required[int]
    text_only: Required[bool]

class QuestionReadyMessage(TypedDict, total=False):
    protocol_version: Required[Literal['1.0']]
    message_type: Required[Literal['question.ready']]
    session_id: Required[str]
    sequence: Required[int]
    idempotency_key: Required[str]
    correlation_id: Required[str]
    sent_at: Required[str]
    payload: Required[QuestionReadyMessagePayload]

class ResumeSnapshotMessagePayloadPendingTurnOption2(TypedDict, total=False):
    turn_id: Required[str]
    speaker: Required[Literal['interviewer', 'applicant']]
    status: Required[str]

class ResumeSnapshotMessagePayload(TypedDict, total=False):
    state: Required[str]
    server_sequence: Required[int]
    last_final_turn_id: Required[str | None]
    pending_turn: Required[None | ResumeSnapshotMessagePayloadPendingTurnOption2]
    last_verified_recording_chunk_sequence: Required[int]
    allowed_client_messages: Required[list[str]]
    degraded_modes: Required[list[str]]

class ResumeSnapshotMessage(TypedDict, total=False):
    protocol_version: Required[Literal['1.0']]
    message_type: Required[Literal['resume.snapshot']]
    session_id: Required[str]
    sequence: Required[int]
    idempotency_key: Required[str]
    correlation_id: Required[str]
    sent_at: Required[str]
    payload: Required[ResumeSnapshotMessagePayload]

class SessionPausedMessagePayload(TypedDict, total=False):
    reason_code: Required[str]
    retryable: Required[bool]
    next_retry_at: Required[str | None]
    user_message: Required[str]

class SessionPausedMessage(TypedDict, total=False):
    protocol_version: Required[Literal['1.0']]
    message_type: Required[Literal['session.paused']]
    session_id: Required[str]
    sequence: Required[int]
    idempotency_key: Required[str]
    correlation_id: Required[str]
    sent_at: Required[str]
    payload: Required[SessionPausedMessagePayload]

class SessionCompletedMessagePayload(TypedDict, total=False):
    completed_at: Required[str]
    last_turn_id: Required[str]
    post_processing_status: Required[Literal['queued', 'running', 'partial', 'ready']]

class SessionCompletedMessage(TypedDict, total=False):
    protocol_version: Required[Literal['1.0']]
    message_type: Required[Literal['session.completed']]
    session_id: Required[str]
    sequence: Required[int]
    idempotency_key: Required[str]
    correlation_id: Required[str]
    sent_at: Required[str]
    payload: Required[SessionCompletedMessagePayload]

class WebSocketErrorMessagePayload(TypedDict, total=False):
    code: Required[str]
    message: Required[str]
    retryable: Required[bool]
    current_state: Required[str]
    current_sequence: Required[int]

class WebSocketErrorMessage(TypedDict, total=False):
    protocol_version: Required[Literal['1.0']]
    message_type: Required[Literal['error']]
    session_id: Required[str]
    sequence: Required[int]
    idempotency_key: Required[str]
    correlation_id: Required[str]
    sent_at: Required[str]
    payload: Required[WebSocketErrorMessagePayload]

class InvitationConsentCompletedEventV1Aggregate(TypedDict, total=False):
    type: Required[Literal['invitation']]
    id: Required[str]
    version: Required[int]

class InvitationConsentCompletedEventV1Payload(TypedDict, total=False):
    invitation_id: Required[str]
    applicant_id: Required[str]
    consent_record_id: Required[str]
    purpose_codes: Required[list[Literal['document_analysis', 'recording', 'ai_assessment']]]
    retention_policy_version: Required[str]
    retention_days: Required[int]

class InvitationConsentCompletedEventV1(TypedDict, total=False):
    event_id: Required[str]
    event_type: Required[Literal['invitation.consent_completed']]
    event_version: Required[Literal[1]]
    occurred_at: Required[str]
    company_id: Required[str]
    aggregate: Required[InvitationConsentCompletedEventV1Aggregate]
    idempotency_key: Required[str]
    trace_id: Required[str]
    correlation_id: Required[str]
    causation_id: Required[str | None]
    payload: Required[InvitationConsentCompletedEventV1Payload]

class InvitationEmailRequestedEventV1Aggregate(TypedDict, total=False):
    type: Required[Literal['invitation']]
    id: Required[str]
    version: Required[int]

class InvitationEmailRequestedEventV1Payload(TypedDict, total=False):
    invitation_id: Required[str]
    applicant_id: Required[str]
    campaign_id: Required[str]
    email_delivery_request_id: Required[str]
    template_id: Required[str]
    link_resolution_id: Required[str]
    expires_at: Required[str]

class InvitationEmailRequestedEventV1(TypedDict, total=False):
    event_id: Required[str]
    event_type: Required[Literal['invitation.email_requested']]
    event_version: Required[Literal[1]]
    occurred_at: Required[str]
    company_id: Required[str]
    aggregate: Required[InvitationEmailRequestedEventV1Aggregate]
    idempotency_key: Required[str]
    trace_id: Required[str]
    correlation_id: Required[str]
    causation_id: Required[str | None]
    payload: Required[InvitationEmailRequestedEventV1Payload]

class SubmissionAnalysisRequestedEventV1Aggregate(TypedDict, total=False):
    type: Required[Literal['submission']]
    id: Required[str]
    version: Required[int]

class SubmissionAnalysisRequestedEventV1Payload(TypedDict, total=False):
    submission_id: Required[str]
    analysis_version: Required[int]
    source_type: Required[Literal['cover_letter', 'resume', 'pdf', 'public_git', 'public_url']]
    source_object_id: Required[str]
    limits_config_version: Required[str]

class SubmissionAnalysisRequestedEventV1(TypedDict, total=False):
    event_id: Required[str]
    event_type: Required[Literal['submission.analysis_requested']]
    event_version: Required[Literal[1]]
    occurred_at: Required[str]
    company_id: Required[str]
    aggregate: Required[SubmissionAnalysisRequestedEventV1Aggregate]
    idempotency_key: Required[str]
    trace_id: Required[str]
    correlation_id: Required[str]
    causation_id: Required[str | None]
    payload: Required[SubmissionAnalysisRequestedEventV1Payload]

class SubmissionAnalysisCompletedEventV1Aggregate(TypedDict, total=False):
    type: Required[Literal['submission']]
    id: Required[str]
    version: Required[int]

class SubmissionAnalysisCompletedEventV1Payload(TypedDict, total=False):
    invitation_id: Required[str]
    submission_id: Required[str]
    analysis_id: Required[str]
    status: Required[Literal['ready', 'partial', 'failed']]
    impact_code: Required[str | None]

class SubmissionAnalysisCompletedEventV1(TypedDict, total=False):
    event_id: Required[str]
    event_type: Required[Literal['submission.analysis_completed']]
    event_version: Required[Literal[1]]
    occurred_at: Required[str]
    company_id: Required[str]
    aggregate: Required[SubmissionAnalysisCompletedEventV1Aggregate]
    idempotency_key: Required[str]
    trace_id: Required[str]
    correlation_id: Required[str]
    causation_id: Required[str | None]
    payload: Required[SubmissionAnalysisCompletedEventV1Payload]

class StrategyReadyEventV1Aggregate(TypedDict, total=False):
    type: Required[Literal['interview_strategy']]
    id: Required[str]
    version: Required[int]

class StrategyReadyEventV1Payload(TypedDict, total=False):
    invitation_id: Required[str]
    interview_strategy_id: Required[str]
    strategy_version: Required[int]
    competency_model_version_id: Required[str]
    status: Required[Literal['ready', 'partial']]

class StrategyReadyEventV1(TypedDict, total=False):
    event_id: Required[str]
    event_type: Required[Literal['strategy.ready']]
    event_version: Required[Literal[1]]
    occurred_at: Required[str]
    company_id: Required[str]
    aggregate: Required[StrategyReadyEventV1Aggregate]
    idempotency_key: Required[str]
    trace_id: Required[str]
    correlation_id: Required[str]
    causation_id: Required[str | None]
    payload: Required[StrategyReadyEventV1Payload]

class InterviewTurnFinalizedEventV1Aggregate(TypedDict, total=False):
    type: Required[Literal['interview_session']]
    id: Required[str]
    version: Required[int]

class InterviewTurnFinalizedEventV1Payload(TypedDict, total=False):
    interview_session_id: Required[str]
    turn_id: Required[str]
    turn_sequence: Required[int]
    speaker: Required[Literal['interviewer', 'applicant']]
    transcript_status: Required[Literal['final', 'review_required']]
    recording_range_status: Required[Literal['ready', 'pending']]

class InterviewTurnFinalizedEventV1(TypedDict, total=False):
    event_id: Required[str]
    event_type: Required[Literal['interview.turn_finalized']]
    event_version: Required[Literal[1]]
    occurred_at: Required[str]
    company_id: Required[str]
    aggregate: Required[InterviewTurnFinalizedEventV1Aggregate]
    idempotency_key: Required[str]
    trace_id: Required[str]
    correlation_id: Required[str]
    causation_id: Required[str | None]
    payload: Required[InterviewTurnFinalizedEventV1Payload]

class InterviewSessionPausedEventV1Aggregate(TypedDict, total=False):
    type: Required[Literal['interview_session']]
    id: Required[str]
    version: Required[int]

class InterviewSessionPausedEventV1Payload(TypedDict, total=False):
    interview_session_id: Required[str]
    session_sequence: Required[int]
    technical_reason_code: Required[str]
    retryable: Required[bool]

class InterviewSessionPausedEventV1(TypedDict, total=False):
    event_id: Required[str]
    event_type: Required[Literal['interview.session_paused']]
    event_version: Required[Literal[1]]
    occurred_at: Required[str]
    company_id: Required[str]
    aggregate: Required[InterviewSessionPausedEventV1Aggregate]
    idempotency_key: Required[str]
    trace_id: Required[str]
    correlation_id: Required[str]
    causation_id: Required[str | None]
    payload: Required[InterviewSessionPausedEventV1Payload]

class InterviewCompletedEventV1Aggregate(TypedDict, total=False):
    type: Required[Literal['interview_session']]
    id: Required[str]
    version: Required[int]

class InterviewCompletedEventV1Payload(TypedDict, total=False):
    interview_session_id: Required[str]
    invitation_id: Required[str]
    last_turn_id: Required[str]
    completed_at: Required[str]
    media_status: Required[Literal['ready', 'pending', 'partial']]

class InterviewCompletedEventV1(TypedDict, total=False):
    event_id: Required[str]
    event_type: Required[Literal['interview.completed']]
    event_version: Required[Literal[1]]
    occurred_at: Required[str]
    company_id: Required[str]
    aggregate: Required[InterviewCompletedEventV1Aggregate]
    idempotency_key: Required[str]
    trace_id: Required[str]
    correlation_id: Required[str]
    causation_id: Required[str | None]
    payload: Required[InterviewCompletedEventV1Payload]

class MediaPostprocessRequestedEventV1Aggregate(TypedDict, total=False):
    type: Required[Literal['recording_asset']]
    id: Required[str]
    version: Required[int]

class MediaPostprocessRequestedEventV1Payload(TypedDict, total=False):
    interview_session_id: Required[str]
    ordered_chunk_set_id: Required[str]
    output_profile_version: Required[str]

class MediaPostprocessRequestedEventV1(TypedDict, total=False):
    event_id: Required[str]
    event_type: Required[Literal['media.postprocess_requested']]
    event_version: Required[Literal[1]]
    occurred_at: Required[str]
    company_id: Required[str]
    aggregate: Required[MediaPostprocessRequestedEventV1Aggregate]
    idempotency_key: Required[str]
    trace_id: Required[str]
    correlation_id: Required[str]
    causation_id: Required[str | None]
    payload: Required[MediaPostprocessRequestedEventV1Payload]

class ReportGenerationRequestedEventV1Aggregate(TypedDict, total=False):
    type: Required[Literal['report']]
    id: Required[str]
    version: Required[int]

class ReportGenerationRequestedEventV1Payload(TypedDict, total=False):
    interview_session_id: Required[str]
    report_version: Required[int]
    competency_model_version_id: Required[str]

class ReportGenerationRequestedEventV1(TypedDict, total=False):
    event_id: Required[str]
    event_type: Required[Literal['report.generation_requested']]
    event_version: Required[Literal[1]]
    occurred_at: Required[str]
    company_id: Required[str]
    aggregate: Required[ReportGenerationRequestedEventV1Aggregate]
    idempotency_key: Required[str]
    trace_id: Required[str]
    correlation_id: Required[str]
    causation_id: Required[str | None]
    payload: Required[ReportGenerationRequestedEventV1Payload]

class ReportReadyEventV1Aggregate(TypedDict, total=False):
    type: Required[Literal['report']]
    id: Required[str]
    version: Required[int]

class ReportReadyEventV1Payload(TypedDict, total=False):
    interview_session_id: Required[str]
    report_id: Required[str]
    report_version: Required[int]
    status: Required[Literal['ready', 'partial']]
    confirmed_count: Required[int]
    partially_confirmed_count: Required[int]
    insufficient_evidence_count: Required[int]
    needs_follow_up_count: Required[int]

class ReportReadyEventV1(TypedDict, total=False):
    event_id: Required[str]
    event_type: Required[Literal['report.ready']]
    event_version: Required[Literal[1]]
    occurred_at: Required[str]
    company_id: Required[str]
    aggregate: Required[ReportReadyEventV1Aggregate]
    idempotency_key: Required[str]
    trace_id: Required[str]
    correlation_id: Required[str]
    causation_id: Required[str | None]
    payload: Required[ReportReadyEventV1Payload]

class DeletionRequestedEventV1Aggregate(TypedDict, total=False):
    type: Required[Literal['deletion_request']]
    id: Required[str]
    version: Required[int]

class DeletionRequestedEventV1Payload(TypedDict, total=False):
    deletion_request_id: Required[str]
    manifest_id: Required[str]
    scope_type: Required[Literal['applicant', 'invitation']]
    scope_id: Required[str]

class DeletionRequestedEventV1(TypedDict, total=False):
    event_id: Required[str]
    event_type: Required[Literal['deletion.requested']]
    event_version: Required[Literal[1]]
    occurred_at: Required[str]
    company_id: Required[str]
    aggregate: Required[DeletionRequestedEventV1Aggregate]
    idempotency_key: Required[str]
    trace_id: Required[str]
    correlation_id: Required[str]
    causation_id: Required[str | None]
    payload: Required[DeletionRequestedEventV1Payload]

class DeletionTargetRequestedEventV1Aggregate(TypedDict, total=False):
    type: Required[Literal['deletion_request']]
    id: Required[str]
    version: Required[int]

class DeletionTargetRequestedEventV1Payload(TypedDict, total=False):
    deletion_request_id: Required[str]
    manifest_id: Required[str]
    owner_lane: Required[Literal['A', 'B', 'C', 'D']]
    target_id: Required[str]
    target_type: Required[str]
    target_store: Required[Literal['aurora', 'dynamodb', 's3', 'opensearch']]
    target_version: Required[int]
    verification_required: Required[Literal[True]]

class DeletionTargetRequestedEventV1(TypedDict, total=False):
    event_id: Required[str]
    event_type: Required[Literal['deletion.target_requested']]
    event_version: Required[Literal[1]]
    occurred_at: Required[str]
    company_id: Required[str]
    aggregate: Required[DeletionTargetRequestedEventV1Aggregate]
    idempotency_key: Required[str]
    trace_id: Required[str]
    correlation_id: Required[str]
    causation_id: Required[str | None]
    payload: Required[DeletionTargetRequestedEventV1Payload]

class DeletionTargetVerifiedEventV1Aggregate(TypedDict, total=False):
    type: Required[Literal['deletion_request']]
    id: Required[str]
    version: Required[int]

class DeletionTargetVerifiedEventV1Payload(TypedDict, total=False):
    deletion_request_id: Required[str]
    target_id: Required[str]
    status: Required[Literal['verified_absent']]
    verified_at: Required[str]

class DeletionTargetVerifiedEventV1(TypedDict, total=False):
    event_id: Required[str]
    event_type: Required[Literal['deletion.target_verified']]
    event_version: Required[Literal[1]]
    occurred_at: Required[str]
    company_id: Required[str]
    aggregate: Required[DeletionTargetVerifiedEventV1Aggregate]
    idempotency_key: Required[str]
    trace_id: Required[str]
    correlation_id: Required[str]
    causation_id: Required[str | None]
    payload: Required[DeletionTargetVerifiedEventV1Payload]

class RetentionExpiredEventV1Aggregate(TypedDict, total=False):
    type: Required[Literal['invitation']]
    id: Required[str]
    version: Required[int]

class RetentionExpiredEventV1Payload(TypedDict, total=False):
    invitation_id: Required[str]
    applicant_id: Required[str]
    policy_snapshot_id: Required[str]
    expired_at: Required[str]

class RetentionExpiredEventV1(TypedDict, total=False):
    event_id: Required[str]
    event_type: Required[Literal['retention.expired']]
    event_version: Required[Literal[1]]
    occurred_at: Required[str]
    company_id: Required[str]
    aggregate: Required[RetentionExpiredEventV1Aggregate]
    idempotency_key: Required[str]
    trace_id: Required[str]
    correlation_id: Required[str]
    causation_id: Required[str | None]
    payload: Required[RetentionExpiredEventV1Payload]

class CampaignSnapshot(TypedDict, total=False):
    company_id: Required[str]
    campaign_id: Required[str]
    position_id: Required[str]
    competency_model_version_id: Required[str]
    status: Required[Literal['draft', 'published', 'closed']]
    prohibited_topics: Required[list[str]]
    interview_duration_minutes: Required[int]
    persona_definition: Required[dict[str, Any]]

class CriterionVersionSnapshotCriteriaItem(TypedDict, total=False):
    criterion_id: Required[str]
    code: Required[str]
    name: Required[str]
    description: Required[str]
    weight: Required[float]
    good_evidence: Required[dict[str, Any]]
    weak_evidence: Required[dict[str, Any]]
    abstain_guidance: Required[str]
    common_questions: Required[list[str]]
    required: Required[bool]

class CriterionVersionSnapshot(TypedDict, total=False):
    company_id: Required[str]
    competency_model_version_id: Required[str]
    position_id: Required[str]
    version_number: Required[int]
    status: Required[Literal['published', 'retired']]
    criteria: Required[list[CriterionVersionSnapshotCriteriaItem]]

class InvitationAuthorizationSnapshot(TypedDict, total=False):
    company_id: Required[str]
    invitation_id: Required[str]
    applicant_id: Required[str]
    campaign_id: Required[str]
    state: Required[str]
    expires_at: Required[str]
    authorized: Required[bool]
    reason_code: Required[str | None]

class ConsentAuthorizationSnapshot(TypedDict, total=False):
    company_id: Required[str]
    invitation_id: Required[str]
    consent_record_id: Required[str]
    policy_version: Required[str]
    purpose_codes: Required[list[str]]
    retention_days: Required[int]
    accepted_at: Required[str]
    withdrawn_at: Required[str | None]
    authorized: Required[bool]
    reason_code: Required[str | None]

class InvitationStateTransitionSnapshot(TypedDict, total=False):
    company_id: Required[str]
    invitation_id: Required[str]
    previous_state: Required[str]
    state: Required[str]
    row_version: Required[int]
    applied: Required[bool]
    idempotency_key: Required[str]

class AuditAppendReceipt(TypedDict, total=False):
    company_id: Required[str]
    audit_event_id: Required[str]
    action: Required[str]
    resource_type: Required[str]
    resource_id: Required[str]
    result: Required[Literal['succeeded', 'denied', 'failed']]

class CompanyDeletionTargetEnumerationSnapshotTargetsItem(TypedDict, total=False):
    target_id: Required[str]
    target_type: Required[Literal['applicant', 'audit_event', 'consent_record', 'invitation']]
    store: Required[Literal['aurora']]
    target_version: Required[int]

class CompanyDeletionTargetEnumerationSnapshot(TypedDict, total=False):
    company_id: Required[str]
    scope_type: Required[Literal['invitation', 'applicant']]
    scope_id: Required[str]
    owner_lane: Required[Literal['A']]
    targets: Required[list[CompanyDeletionTargetEnumerationSnapshotTargetsItem]]

class CompanyDeletionTargetReceipt(TypedDict, total=False):
    company_id: Required[str]
    deletion_request_id: Required[str]
    target_id: Required[str]
    owner_lane: Required[Literal['A']]
    status: Required[Literal['deleting', 'retrying', 'failed', 'verified_absent']]
    attempts: Required[int]
    verified_at: Required[str | None]
    error_code: Required[str | None]

class SubmissionAnalysisStatusSnapshotSubmissionsItem(TypedDict, total=False):
    submission_id: Required[str]
    status: Required[Literal['received', 'validating', 'analyzing', 'ready', 'partial', 'failed', 'deleted']]
    impact_code: Required[str | None]

class SubmissionAnalysisStatusSnapshot(TypedDict, total=False):
    company_id: Required[str]
    invitation_id: Required[str]
    overall_status: Required[Literal['waiting', 'analyzing', 'ready', 'partial', 'failed']]
    submissions: Required[list[SubmissionAnalysisStatusSnapshotSubmissionsItem]]
    strategy_ready: Required[bool]

class StrategySnapshotSourceReferenceCandidatesItem(TypedDict, total=False):
    source_type: Required[Literal['submission_chunk', 'candidate_code_unit']]
    source_id: Required[str]
    locator_version: Required[int]

class StrategySnapshot(TypedDict, total=False):
    company_id: Required[str]
    invitation_id: Required[str]
    interview_strategy_id: Required[str]
    strategy_version: Required[int]
    competency_model_version_id: Required[str]
    status: Required[Literal['ready', 'partial', 'superseded']]
    common_topics: Required[list[dict[str, Any]]]
    verification_points: Required[list[dict[str, Any]]]
    follow_up_directions: Required[dict[str, Any]]
    time_budget: Required[dict[str, Any]]
    required_evidence_plan: Required[dict[str, Any]]
    source_reference_candidates: Required[list[StrategySnapshotSourceReferenceCandidatesItem]]
    model_config_version: Required[str]

class RetrievedContextSnapshotResultsItemSourceReference(TypedDict, total=False):
    company_id: Required[str]
    source_type: Required[Literal['submission_chunk', 'candidate_code_unit']]
    source_id: Required[str]
    source_version: Required[int]
    source_location: Required[dict[str, Any]]
    ownership_confidence: Required[float | None]
    source_hash: Required[str]
    evidence_eligible: Required[Literal[False]]

class RetrievedContextSnapshotResultsItem(TypedDict, total=False):
    rank: Required[int]
    score: Required[float]
    source_reference: Required[RetrievedContextSnapshotResultsItemSourceReference]

class RetrievedContextSnapshot(TypedDict, total=False):
    company_id: Required[str]
    applicant_id: Required[str]
    interview_session_id: Required[str]
    criterion_id: Required[str]
    retrieval_config_version: Required[str]
    results: Required[list[RetrievedContextSnapshotResultsItem]]

class SourceReferenceSnapshot(TypedDict, total=False):
    company_id: Required[str]
    source_type: Required[Literal['submission_chunk', 'candidate_code_unit']]
    source_id: Required[str]
    source_version: Required[int]
    source_location: Required[dict[str, Any]]
    ownership_confidence: Required[float | None]
    source_hash: Required[str]
    evidence_eligible: Required[Literal[False]]

class SubmissionDeletionTargetEnumerationSnapshotTargetsItem(TypedDict, total=False):
    target_id: Required[str]
    target_type: Required[str]
    store: Required[Literal['aurora', 's3', 'opensearch']]
    target_version: Required[int]

class SubmissionDeletionTargetEnumerationSnapshot(TypedDict, total=False):
    company_id: Required[str]
    scope_type: Required[Literal['invitation', 'applicant']]
    scope_id: Required[str]
    owner_lane: Required[Literal['B']]
    targets: Required[list[SubmissionDeletionTargetEnumerationSnapshotTargetsItem]]

class SubmissionDeletionTargetReceipt(TypedDict, total=False):
    company_id: Required[str]
    deletion_request_id: Required[str]
    target_id: Required[str]
    owner_lane: Required[Literal['B']]
    status: Required[Literal['deleting', 'retrying', 'failed', 'verified_absent']]
    attempts: Required[int]
    verified_at: Required[str | None]
    error_code: Required[str | None]

class SessionSnapshot(TypedDict, total=False):
    company_id: Required[str]
    interview_session_id: Required[str]
    invitation_id: Required[str]
    applicant_id: Required[str]
    interview_strategy_id: Required[str]
    competency_model_version_id: Required[str]
    state: Required[Literal['preparing', 'in_progress', 'awaiting_answer', 'preparing_question', 'paused', 'completed', 'report_generating', 'reviewable']]
    session_sequence: Required[int]
    last_final_turn_id: Required[str | None]
    last_verified_recording_chunk_sequence: Required[int]
    degraded_modes: Required[list[str]]

class FinalTurnSnapshot(TypedDict, total=False):
    company_id: Required[str]
    interview_session_id: Required[str]
    turn_id: Required[str]
    sequence: Required[int]
    speaker: Required[Literal['interviewer', 'applicant']]
    status: Required[Literal['final']]
    text: Required[str]
    target_criterion_id: Required[str | None]
    model_config_version: Required[str | None]
    finalized_at: Required[str]

class FinalTurnPageSnapshotItemsItem(TypedDict, total=False):
    company_id: Required[str]
    interview_session_id: Required[str]
    turn_id: Required[str]
    sequence: Required[int]
    speaker: Required[Literal['interviewer', 'applicant']]
    status: Required[Literal['final']]
    text: Required[str]
    target_criterion_id: Required[str | None]
    model_config_version: Required[str | None]
    finalized_at: Required[str]

class FinalTurnPageSnapshot(TypedDict, total=False):
    company_id: Required[str]
    interview_session_id: Required[str]
    items: Required[list[FinalTurnPageSnapshotItemsItem]]
    next_cursor: Required[str | None]

class RecordingChunkSetSnapshotChunksItem(TypedDict, total=False):
    recording_chunk_id: Required[str]
    sequence: Required[int]
    object_ref: Required[str]
    content_hash: Required[str]
    byte_size: Required[int]
    session_start_ms: Required[int]
    session_end_ms: Required[int]
    upload_status: Required[Literal['verified']]

class RecordingChunkSetSnapshot(TypedDict, total=False):
    company_id: Required[str]
    interview_session_id: Required[str]
    chunks: Required[list[RecordingChunkSetSnapshotChunksItem]]

class InterviewDeletionTargetEnumerationSnapshotTargetsItem(TypedDict, total=False):
    target_id: Required[str]
    target_type: Required[str]
    store: Required[Literal['aurora', 'dynamodb', 's3']]
    target_version: Required[int]

class InterviewDeletionTargetEnumerationSnapshot(TypedDict, total=False):
    company_id: Required[str]
    scope_type: Required[Literal['session', 'applicant']]
    scope_id: Required[str]
    owner_lane: Required[Literal['C']]
    targets: Required[list[InterviewDeletionTargetEnumerationSnapshotTargetsItem]]

class InterviewDeletionTargetReceipt(TypedDict, total=False):
    company_id: Required[str]
    deletion_request_id: Required[str]
    target_id: Required[str]
    owner_lane: Required[Literal['C']]
    status: Required[Literal['deleting', 'retrying', 'failed', 'verified_absent']]
    attempts: Required[int]
    verified_at: Required[str | None]
    error_code: Required[str | None]

class ReviewProjectionSnapshot(TypedDict, total=False):
    company_id: Required[str]
    invitation_id: Required[str]
    interview_session_id: Required[str]
    report_id: Required[str | None]
    report_status: Required[Literal['queued', 'generating', 'ready', 'partial', 'failed']]
    summary_status: Required[Literal['unavailable', 'processing', 'ready', 'partial']]
    human_decision_status: Required[Literal['advance', 'reject', 'hold', 'withdrawn', None]]

class ReportSnapshotAssessmentCounts(TypedDict, total=False):
    confirmed: Required[int]
    partially_confirmed: Required[int]
    insufficient_evidence: Required[int]
    needs_follow_up: Required[int]

class ReportSnapshotItemsItemEvidenceItem(TypedDict, total=False):
    evidence_id: Required[str]
    evidence_type: Required[Literal['applicant_answer']]
    company_id: Required[str]
    criterion_id: Required[str]
    competency_model_version_id: Required[str]
    answer_turn_id: Required[str]
    answer_turn_speaker: Required[Literal['applicant']]
    answer_turn_status: Required[Literal['final']]
    transcript_segment_id: Required[str]
    video_start_ms: Required[int]
    video_end_ms: Required[int]
    technical_failure_overlap: Required[Literal[False]]
    observation: Required[str]
    rationale: Required[str]
    sufficiency: Required[Literal['direct', 'supporting', 'weak']]
    generation_version: Required[str]

class ReportSnapshotItemsItem(TypedDict, total=False):
    report_item_id: Required[str]
    criterion_id: Required[str]
    competency_model_version_id: Required[str]
    assessment_state: Required[Literal['confirmed', 'partially_confirmed', 'insufficient_evidence', 'needs_follow_up']]
    observation: Required[str]
    rationale: Required[str]
    sufficiency: Required[Literal['sufficient', 'limited', 'insufficient']]
    uncertainty: Required[str]
    follow_up_question: Required[str | None]
    evidence: Required[list[ReportSnapshotItemsItemEvidenceItem]]

class ReportSnapshotHumanOverridesItem(TypedDict, total=False):
    human_review_id: Required[str]
    company_user_id: Required[str]
    review_type: Required[Literal['assessment_override', 'note', 'bookmark', 'final_decision']]
    target_id: Required[str]
    value: Required[dict[str, Any]]
    reason: Required[str]
    created_at: Required[str]

class ReportSnapshot(TypedDict, total=False):
    company_id: Required[str]
    interview_session_id: Required[str]
    report_id: Required[str]
    report_version: Required[int]
    competency_model_version_id: Required[str]
    status: Required[Literal['generating', 'ready', 'partial', 'failed']]
    summary: Required[str]
    assessment_counts: Required[ReportSnapshotAssessmentCounts]
    items: Required[list[ReportSnapshotItemsItem]]
    human_overrides: Required[list[ReportSnapshotHumanOverridesItem]]
    human_decision_status: Required[Literal['advance', 'reject', 'hold', 'withdrawn', None]]
    ai_original_immutable: Required[Literal[True]]

class DeletionStatusSnapshotTargetsItem(TypedDict, total=False):
    target_id: Required[str]
    owner_lane: Required[Literal['A', 'B', 'C', 'D']]
    store: Required[Literal['aurora', 'dynamodb', 's3', 'opensearch']]
    target_type: Required[str]
    status: Required[Literal['pending', 'deleting', 'retrying', 'failed', 'verified_absent']]
    attempts: Required[int]
    verified_at: Required[str | None]
    error_code: Required[str | None]

class DeletionStatusSnapshot(TypedDict, total=False):
    company_id: Required[str]
    deletion_request_id: Required[str]
    manifest_id: Required[str]
    status: Required[Literal['requested', 'enumerating', 'deleting', 'verifying', 'retrying', 'partially_completed', 'completed']]
    expected_targets: Required[int]
    verified_targets: Required[int]
    targets: Required[list[DeletionStatusSnapshotTargetsItem]]

SubmissionCreate: TypeAlias = SubmissionCreateOption1 | SubmissionCreateOption2

AssessmentState: TypeAlias = Literal['confirmed', 'partially_confirmed', 'insufficient_evidence', 'needs_follow_up']

__all__ = [
    "ErrorEnvelope",
    "CompanyUserView",
    "PositionCreate",
    "Position",
    "PositionPage",
    "EvaluationCriterionInput",
    "CompetencyModelVersionCreate",
    "CompetencyModelVersion",
    "CampaignCreate",
    "Campaign",
    "InvitationBatchCreate",
    "InvitationView",
    "InvitationPage",
    "InvitationBatchResult",
    "ApplicantTokenExchange",
    "ApplicantIdentityVerification",
    "ApplicantAccessState",
    "ConsentCreate",
    "ConsentView",
    "UploadIntentCreate",
    "UploadIntent",
    "SubmissionCreate",
    "SubmissionView",
    "AnalysisReadiness",
    "EquipmentCheckCreate",
    "EquipmentComponent",
    "EquipmentCheck",
    "InterviewSessionCreate",
    "InterviewSessionView",
    "InterviewResumeSnapshot",
    "RecordingUploadIntentCreate",
    "AssessmentState",
    "EvidenceView",
    "ReportItemView",
    "ReportView",
    "TimelineView",
    "HumanAssessmentReviewCreate",
    "ReviewArtifactCreate",
    "FinalDecisionCreate",
    "HumanReviewView",
    "DeletionRequestCreate",
    "DeletionTargetView",
    "DeletionStatus",
    "ProcessingStatus",
    "SessionStartMessage",
    "AudioChunkBeginMessage",
    "AnswerTextSubmitMessage",
    "AnswerCompleteMessage",
    "QuestionRepeatMessage",
    "SessionResumeMessage",
    "ClientAckMessage",
    "HeartbeatPingMessage",
    "SessionStateChangedMessage",
    "TranscriptPartialMessage",
    "TranscriptFinalMessage",
    "QuestionPreparingMessage",
    "QuestionReadyMessage",
    "ResumeSnapshotMessage",
    "SessionPausedMessage",
    "SessionCompletedMessage",
    "WebSocketErrorMessage",
    "InvitationConsentCompletedEventV1",
    "InvitationEmailRequestedEventV1",
    "SubmissionAnalysisRequestedEventV1",
    "SubmissionAnalysisCompletedEventV1",
    "StrategyReadyEventV1",
    "InterviewTurnFinalizedEventV1",
    "InterviewSessionPausedEventV1",
    "InterviewCompletedEventV1",
    "MediaPostprocessRequestedEventV1",
    "ReportGenerationRequestedEventV1",
    "ReportReadyEventV1",
    "DeletionRequestedEventV1",
    "DeletionTargetRequestedEventV1",
    "DeletionTargetVerifiedEventV1",
    "RetentionExpiredEventV1",
    "CampaignSnapshot",
    "CriterionVersionSnapshot",
    "InvitationAuthorizationSnapshot",
    "ConsentAuthorizationSnapshot",
    "InvitationStateTransitionSnapshot",
    "AuditAppendReceipt",
    "CompanyDeletionTargetEnumerationSnapshot",
    "CompanyDeletionTargetReceipt",
    "SubmissionAnalysisStatusSnapshot",
    "StrategySnapshot",
    "RetrievedContextSnapshot",
    "SourceReferenceSnapshot",
    "SubmissionDeletionTargetEnumerationSnapshot",
    "SubmissionDeletionTargetReceipt",
    "SessionSnapshot",
    "FinalTurnSnapshot",
    "FinalTurnPageSnapshot",
    "RecordingChunkSetSnapshot",
    "InterviewDeletionTargetEnumerationSnapshot",
    "InterviewDeletionTargetReceipt",
    "ReviewProjectionSnapshot",
    "ReportSnapshot",
    "DeletionStatusSnapshot",
]
