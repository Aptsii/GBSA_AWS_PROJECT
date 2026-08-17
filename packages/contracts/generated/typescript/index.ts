// Generated contract types. DO NOT EDIT.

// Run packages/contracts/scripts/generate_contracts.py instead.

export type ErrorEnvelope = {
  type: string;
  title: string;
  status: number;
  code: string;
  detail?: string;
  request_id: string;
  retryable: boolean;
  current_version?: number;
  errors?: Array<{
    field: string;
    code: string;
  }>;
};

export type CompanyUserView = {
  company_user_id: string;
  company_id: string;
  email: string;
  status: "invited" | "active" | "disabled";
};

export type PositionCreate = {
  title: string;
  description: string;
};

export type Position = {
  title: string;
  description: string;
  position_id: string;
  status: "draft" | "active" | "closed";
  row_version: number;
  created_at: string;
};

export type PositionPage = {
  items: Array<{
    title: string;
    description: string;
    position_id: string;
    status: "draft" | "active" | "closed";
    row_version: number;
    created_at: string;
  }>;
  next_cursor?: string | null;
};

export type EvaluationCriterionInput = {
  code: string;
  name: string;
  description: string;
  weight: number;
  good_evidence: Record<string, unknown>;
  weak_evidence: Record<string, unknown>;
  abstain_guidance: string;
  common_questions?: Array<string>;
  required: boolean;
};

export type CompetencyModelVersionCreate = {
  criteria: Array<{
    code: string;
    name: string;
    description: string;
    weight: number;
    good_evidence: Record<string, unknown>;
    weak_evidence: Record<string, unknown>;
    abstain_guidance: string;
    common_questions?: Array<string>;
    required: boolean;
  }>;
  prohibited_topics: Array<string>;
  interview_duration_minutes: number;
  persona_definition: Record<string, unknown>;
};

export type CompetencyModelVersion = {
  criteria: Array<{
    code: string;
    name: string;
    description: string;
    weight: number;
    good_evidence: Record<string, unknown>;
    weak_evidence: Record<string, unknown>;
    abstain_guidance: string;
    common_questions?: Array<string>;
    required: boolean;
  }>;
  prohibited_topics: Array<string>;
  interview_duration_minutes: number;
  persona_definition: Record<string, unknown>;
  competency_model_version_id: string;
  position_id: string;
  version_number: number;
  status: "draft" | "published" | "retired";
  row_version: number;
  published_at?: string | null;
};

export type CampaignCreate = {
  position_id: string;
  competency_model_version_id: string;
  name: string;
  candidate_instructions: string;
};

export type Campaign = {
  position_id: string;
  competency_model_version_id: string;
  name: string;
  candidate_instructions: string;
  campaign_id: string;
  status: "draft" | "published" | "closed";
  row_version: number;
  published_at?: string | null;
};

export type InvitationBatchCreate = {
  applicants: Array<{
    email: string;
    display_name: string;
  }>;
  expires_at: string;
};

export type InvitationView = {
  invitation_id: string;
  campaign_id: string;
  applicant_email: string;
  status: "invited" | "identity_verified" | "consented" | "materials_submitted" | "analyzing" | "ready" | "interviewing" | "interrupted" | "completed" | "reviewed" | "expired" | "revoked" | "deleted";
  expires_at: string;
  row_version: number;
  analysis_status?: string | null;
  interview_status?: string | null;
  report_status?: string | null;
};

export type InvitationPage = {
  items: Array<{
    invitation_id: string;
    campaign_id: string;
    applicant_email: string;
    status: "invited" | "identity_verified" | "consented" | "materials_submitted" | "analyzing" | "ready" | "interviewing" | "interrupted" | "completed" | "reviewed" | "expired" | "revoked" | "deleted";
    expires_at: string;
    row_version: number;
    analysis_status?: string | null;
    interview_status?: string | null;
    report_status?: string | null;
  }>;
  next_cursor?: string | null;
};

export type InvitationBatchResult = {
  accepted_count: number;
  rejected_count: number;
  invitations: Array<{
    invitation_id: string;
    campaign_id: string;
    applicant_email: string;
    status: "invited" | "identity_verified" | "consented" | "materials_submitted" | "analyzing" | "ready" | "interviewing" | "interrupted" | "completed" | "reviewed" | "expired" | "revoked" | "deleted";
    expires_at: string;
    row_version: number;
    analysis_status?: string | null;
    interview_status?: string | null;
    report_status?: string | null;
  }>;
};

export type ApplicantTokenExchange = {
  invitation_token: string;
};

export type ApplicantIdentityVerification = {
  display_name: string;
  verification_value: string;
};

export type ApplicantAccessState = {
  invitation_id: string;
  state: string;
  expires_at: string;
  required_actions: Array<string>;
};

export type ConsentCreate = {
  policy_version: string;
  accepted_purposes: Array<"document_analysis" | "recording" | "ai_assessment">;
  consent_content_digest: string;
};

export type ConsentView = {
  consent_record_id: string;
  policy_version: string;
  accepted_purposes: Array<string>;
  retention_days: number;
  accepted_at: string;
};

export type UploadIntentCreate = {
  source_type: "cover_letter" | "resume" | "pdf";
  filename: string;
  media_type: string;
  byte_size: number;
  sha256: string;
};

export type UploadIntent = {
  upload_id: string;
  method: "PUT";
  url: string;
  required_headers: Record<string, unknown>;
  expires_at: string;
};

export type SubmissionCreate = {
  source_type: "cover_letter" | "resume" | "pdf";
  upload_id: string;
} | {
  source_type: "public_git" | "public_url";
  public_url: string;
  candidate_identity_inputs?: Record<string, unknown>;
};

export type SubmissionView = {
  submission_id: string;
  source_type: string;
  status: "received" | "validating" | "analyzing" | "ready" | "partial" | "failed" | "deleted";
  failure_code?: string | null;
  impact_summary?: string | null;
  created_at: string;
};

export type AnalysisReadiness = {
  overall_status: "waiting" | "analyzing" | "ready" | "partial" | "failed";
  submissions: Array<{
    submission_id: string;
    source_type: string;
    status: "received" | "validating" | "analyzing" | "ready" | "partial" | "failed" | "deleted";
    failure_code?: string | null;
    impact_summary?: string | null;
    created_at: string;
  }>;
  interview_ready: boolean;
  strategy_id?: string | null;
  strategy_version?: number | null;
  impact_summary?: string | null;
};

export type EquipmentCheckCreate = {
  camera: {
    status: "ready" | "warning" | "failed";
    sanitized_code?: string | null;
  };
  microphone: {
    status: "ready" | "warning" | "failed";
    sanitized_code?: string | null;
  };
  network: {
    status: "ready" | "warning" | "failed";
    sanitized_code?: string | null;
  };
};

export type EquipmentComponent = {
  status: "ready" | "warning" | "failed";
  sanitized_code?: string | null;
};

export type EquipmentCheck = {
  camera: {
    status: "ready" | "warning" | "failed";
    sanitized_code?: string | null;
  };
  microphone: {
    status: "ready" | "warning" | "failed";
    sanitized_code?: string | null;
  };
  network: {
    status: "ready" | "warning" | "failed";
    sanitized_code?: string | null;
  };
  equipment_check_id: string;
  overall_status: "ready" | "warning" | "failed";
  checked_at: string;
};

export type InterviewSessionCreate = {
  equipment_check_id: string;
  strategy_id: string;
  acknowledged_partial_analysis: boolean;
};

export type InterviewSessionView = {
  interview_session_id: string;
  state: "preparing" | "in_progress" | "awaiting_answer" | "preparing_question" | "paused" | "completed" | "report_generating" | "reviewable";
  session_sequence: number;
  websocket_path: string;
  protocol_version: "1.0";
};

export type InterviewResumeSnapshot = {
  interview_session_id: string;
  state: string;
  server_sequence: number;
  last_final_turn_id?: string | null;
  pending_turn?: Record<string, unknown> | null;
  last_verified_recording_chunk_sequence: number;
  degraded_modes?: Array<string>;
};

export type RecordingUploadIntentCreate = {
  chunk_sequence: number;
  byte_size: number;
  sha256: string;
  session_start_ms: number;
  session_end_ms: number;
};

export type AssessmentState = "confirmed" | "partially_confirmed" | "insufficient_evidence" | "needs_follow_up";

export type EvidenceView = {
  evidence_id: string;
  answer_turn_id: string;
  transcript_segment_id: string;
  video_start_ms: number;
  video_end_ms: number;
  observation: string;
  rationale: string;
  sufficiency: "direct" | "supporting" | "weak";
};

export type ReportItemView = {
  report_item_id: string;
  criterion_id: string;
  assessment_state: "confirmed" | "partially_confirmed" | "insufficient_evidence" | "needs_follow_up";
  observation: string;
  rationale: string;
  uncertainty: string;
  follow_up_question?: string | null;
  evidence: Array<{
    evidence_id: string;
    answer_turn_id: string;
    transcript_segment_id: string;
    video_start_ms: number;
    video_end_ms: number;
    observation: string;
    rationale: string;
    sufficiency: "direct" | "supporting" | "weak";
  }>;
};

export type ReportView = {
  report_id: string;
  report_version: number;
  status: "generating" | "ready" | "partial" | "failed";
  summary: string;
  items: Array<{
    report_item_id: string;
    criterion_id: string;
    assessment_state: "confirmed" | "partially_confirmed" | "insufficient_evidence" | "needs_follow_up";
    observation: string;
    rationale: string;
    uncertainty: string;
    follow_up_question?: string | null;
    evidence: Array<{
      evidence_id: string;
      answer_turn_id: string;
      transcript_segment_id: string;
      video_start_ms: number;
      video_end_ms: number;
      observation: string;
      rationale: string;
      sufficiency: "direct" | "supporting" | "weak";
    }>;
  }>;
  ai_original_immutable: true;
  human_reviews?: Array<{
    human_review_id: string;
    review_type: "assessment_override" | "note" | "bookmark" | "final_decision";
    created_by: string;
    created_at: string;
  }>;
};

export type TimelineView = {
  entries: Array<{
    entry_id: string;
    entry_type: "question" | "answer" | "event" | "evidence";
    start_ms: number;
    end_ms: number;
    text?: string | null;
    technical_failure?: boolean;
  }>;
  playback: {
    url: string | null;
    expires_at: string | null;
    status: "ready" | "partial" | "processing" | "unavailable";
  };
};

export type HumanAssessmentReviewCreate = {
  assessment_state: "confirmed" | "partially_confirmed" | "insufficient_evidence" | "needs_follow_up";
  reason: string;
};

export type ReviewArtifactCreate = {
  review_type: "note" | "bookmark";
  target_id: string;
  value: string;
};

export type FinalDecisionCreate = {
  decision: "advance" | "reject" | "hold" | "withdrawn";
  reason: string;
};

export type HumanReviewView = {
  human_review_id: string;
  review_type: "assessment_override" | "note" | "bookmark" | "final_decision";
  created_by: string;
  created_at: string;
};

export type DeletionRequestCreate = {
  scope_type: "invitation" | "applicant";
  scope_id: string;
  reason: string;
};

export type DeletionTargetView = {
  target_id: string;
  owner_lane: "A" | "B" | "C" | "D";
  store: "aurora" | "dynamodb" | "s3" | "opensearch";
  target_type: string;
  status: "pending" | "deleting" | "retrying" | "failed" | "verified_absent";
  attempts: number;
  verified_at?: string | null;
  error_code?: string | null;
};

export type DeletionStatus = {
  deletion_request_id: string;
  manifest_id: string;
  status: "requested" | "enumerating" | "deleting" | "verifying" | "retrying" | "partially_completed" | "completed";
  expected_targets: number;
  verified_targets: number;
  targets: Array<{
    target_id: string;
    owner_lane: "A" | "B" | "C" | "D";
    store: "aurora" | "dynamodb" | "s3" | "opensearch";
    target_type: string;
    status: "pending" | "deleting" | "retrying" | "failed" | "verified_absent";
    attempts: number;
    verified_at?: string | null;
    error_code?: string | null;
  }>;
};

export type ProcessingStatus = {
  status: "queued" | "running" | "partial" | "failed";
  retryable?: boolean;
  message?: string | null;
};

export type SessionStartMessage = {
  protocol_version: "1.0";
  message_type: "session.start";
  session_id: string;
  sequence: number;
  idempotency_key: string;
  correlation_id: string;
  sent_at: string;
  payload: {
    equipment_check_id: string;
    expected_state: "preparing";
  };
};

export type AudioChunkBeginMessage = {
  protocol_version: "1.0";
  message_type: "audio.chunk.begin";
  session_id: string;
  sequence: number;
  idempotency_key: string;
  correlation_id: string;
  sent_at: string;
  payload: {
    answer_turn_id: string;
    chunk_sequence: number;
    codec: "pcm_s16le" | "opus";
    sample_rate_hz: number;
    channel_count: number;
    byte_length: number;
    sha256: string;
  };
};

export type AnswerCompleteMessage = {
  protocol_version: "1.0";
  message_type: "answer.complete";
  session_id: string;
  sequence: number;
  idempotency_key: string;
  correlation_id: string;
  sent_at: string;
  payload: {
    answer_turn_id: string;
    last_audio_chunk_sequence: number;
    last_recording_chunk_sequence: number;
    expected_state: "awaiting_answer";
  };
};

export type QuestionRepeatMessage = {
  protocol_version: "1.0";
  message_type: "question.repeat";
  session_id: string;
  sequence: number;
  idempotency_key: string;
  correlation_id: string;
  sent_at: string;
  payload: {
    question_turn_id: string;
    mode: "repeat_or_clarify";
  };
};

export type SessionResumeMessage = {
  protocol_version: "1.0";
  message_type: "session.resume";
  session_id: string;
  sequence: number;
  idempotency_key: string;
  correlation_id: string;
  sent_at: string;
  payload: {
    last_applied_server_sequence: number;
    last_final_turn_id: string | null;
    last_uploaded_recording_chunk_sequence: number;
  };
};

export type ClientAckMessage = {
  protocol_version: "1.0";
  message_type: "client.ack";
  session_id: string;
  sequence: number;
  idempotency_key: string;
  correlation_id: string;
  sent_at: string;
  payload: {
    server_event_id: string;
    applied_sequence: number;
  };
};

export type HeartbeatPingMessage = {
  protocol_version: "1.0";
  message_type: "heartbeat.ping";
  session_id: string;
  sequence: number;
  idempotency_key: string;
  correlation_id: string;
  sent_at: string;
  payload: {
    client_monotonic_ms: number;
  };
};

export type SessionStateChangedMessage = {
  protocol_version: "1.0";
  message_type: "session.state_changed";
  session_id: string;
  sequence: number;
  idempotency_key: string;
  correlation_id: string;
  sent_at: string;
  payload: {
    previous_state: string;
    state: string;
    reason_code: string;
    checkpoint_id: string;
  };
};

export type TranscriptPartialMessage = {
  protocol_version: "1.0";
  message_type: "transcript.partial";
  session_id: string;
  sequence: number;
  idempotency_key: string;
  correlation_id: string;
  sent_at: string;
  payload: {
    answer_turn_id: string;
    segment_sequence: number;
    text: string;
    start_ms: number;
    end_ms: number;
    confidence: number;
    is_final: false;
  };
};

export type TranscriptFinalMessage = {
  protocol_version: "1.0";
  message_type: "transcript.final";
  session_id: string;
  sequence: number;
  idempotency_key: string;
  correlation_id: string;
  sent_at: string;
  payload: {
    answer_turn_id: string;
    transcript_segment_id: string;
    segment_sequence: number;
    text: string;
    start_ms: number;
    end_ms: number;
    confidence: number;
    is_final: true;
    review_required: boolean;
  };
};

export type QuestionPreparingMessage = {
  protocol_version: "1.0";
  message_type: "question.preparing";
  session_id: string;
  sequence: number;
  idempotency_key: string;
  correlation_id: string;
  sent_at: string;
  payload: {
    stage: "retrieval" | "generation" | "policy" | "speech";
    degraded_mode: "none" | "search_fallback" | "text_only";
  };
};

export type QuestionReadyMessage = {
  protocol_version: "1.0";
  message_type: "question.ready";
  session_id: string;
  sequence: number;
  idempotency_key: string;
  correlation_id: string;
  sent_at: string;
  payload: {
    question_turn_id: string;
    text: string;
    target_criterion_id: string;
    audio_url: string | null;
    audio_expires_at: string | null;
    speech_marks_url: string | null;
    source_reference_count: number;
    text_only: boolean;
  };
};

export type ResumeSnapshotMessage = {
  protocol_version: "1.0";
  message_type: "resume.snapshot";
  session_id: string;
  sequence: number;
  idempotency_key: string;
  correlation_id: string;
  sent_at: string;
  payload: {
    state: string;
    server_sequence: number;
    last_final_turn_id: string | null;
    pending_turn: null | {
      turn_id: string;
      speaker: "interviewer" | "applicant";
      status: string;
    };
    last_verified_recording_chunk_sequence: number;
    allowed_client_messages: Array<string>;
    degraded_modes: Array<string>;
  };
};

export type SessionPausedMessage = {
  protocol_version: "1.0";
  message_type: "session.paused";
  session_id: string;
  sequence: number;
  idempotency_key: string;
  correlation_id: string;
  sent_at: string;
  payload: {
    reason_code: string;
    retryable: boolean;
    next_retry_at: string | null;
    user_message: string;
  };
};

export type SessionCompletedMessage = {
  protocol_version: "1.0";
  message_type: "session.completed";
  session_id: string;
  sequence: number;
  idempotency_key: string;
  correlation_id: string;
  sent_at: string;
  payload: {
    completed_at: string;
    last_turn_id: string;
    post_processing_status: "queued" | "running" | "partial" | "ready";
  };
};

export type WebSocketErrorMessage = {
  protocol_version: "1.0";
  message_type: "error";
  session_id: string;
  sequence: number;
  idempotency_key: string;
  correlation_id: string;
  sent_at: string;
  payload: {
    code: string;
    message: string;
    retryable: boolean;
    current_state: string;
    current_sequence: number;
  };
};

export type InvitationConsentCompletedEventV1 = {
  event_id: string;
  event_type: "invitation.consent_completed";
  event_version: 1;
  occurred_at: string;
  company_id: string;
  aggregate: {
    type: "invitation";
    id: string;
    version: number;
  };
  idempotency_key: string;
  trace_id: string;
  correlation_id: string;
  causation_id: string | null;
  payload: {
    invitation_id: string;
    applicant_id: string;
    consent_record_id: string;
    purpose_codes: Array<"document_analysis" | "recording" | "ai_assessment">;
    retention_policy_version: string;
    retention_days: number;
  };
};

export type InvitationEmailRequestedEventV1 = {
  event_id: string;
  event_type: "invitation.email_requested";
  event_version: 1;
  occurred_at: string;
  company_id: string;
  aggregate: {
    type: "invitation";
    id: string;
    version: number;
  };
  idempotency_key: string;
  trace_id: string;
  correlation_id: string;
  causation_id: string | null;
  payload: {
    invitation_id: string;
    applicant_id: string;
    campaign_id: string;
    email_delivery_request_id: string;
    template_id: string;
    link_resolution_id: string;
    expires_at: string;
  };
};

export type SubmissionAnalysisRequestedEventV1 = {
  event_id: string;
  event_type: "submission.analysis_requested";
  event_version: 1;
  occurred_at: string;
  company_id: string;
  aggregate: {
    type: "submission";
    id: string;
    version: number;
  };
  idempotency_key: string;
  trace_id: string;
  correlation_id: string;
  causation_id: string | null;
  payload: {
    submission_id: string;
    analysis_version: number;
    source_type: "cover_letter" | "resume" | "pdf" | "public_git" | "public_url";
    source_object_id: string;
    limits_config_version: string;
  };
};

export type SubmissionAnalysisCompletedEventV1 = {
  event_id: string;
  event_type: "submission.analysis_completed";
  event_version: 1;
  occurred_at: string;
  company_id: string;
  aggregate: {
    type: "submission";
    id: string;
    version: number;
  };
  idempotency_key: string;
  trace_id: string;
  correlation_id: string;
  causation_id: string | null;
  payload: {
    invitation_id: string;
    submission_id: string;
    analysis_id: string;
    status: "ready" | "partial" | "failed";
    impact_code: string | null;
  };
};

export type StrategyReadyEventV1 = {
  event_id: string;
  event_type: "strategy.ready";
  event_version: 1;
  occurred_at: string;
  company_id: string;
  aggregate: {
    type: "interview_strategy";
    id: string;
    version: number;
  };
  idempotency_key: string;
  trace_id: string;
  correlation_id: string;
  causation_id: string | null;
  payload: {
    invitation_id: string;
    interview_strategy_id: string;
    strategy_version: number;
    competency_model_version_id: string;
    status: "ready" | "partial";
  };
};

export type InterviewTurnFinalizedEventV1 = {
  event_id: string;
  event_type: "interview.turn_finalized";
  event_version: 1;
  occurred_at: string;
  company_id: string;
  aggregate: {
    type: "interview_session";
    id: string;
    version: number;
  };
  idempotency_key: string;
  trace_id: string;
  correlation_id: string;
  causation_id: string | null;
  payload: {
    interview_session_id: string;
    turn_id: string;
    turn_sequence: number;
    speaker: "interviewer" | "applicant";
    transcript_status: "final" | "review_required";
    recording_range_status: "ready" | "pending";
  };
};

export type InterviewSessionPausedEventV1 = {
  event_id: string;
  event_type: "interview.session_paused";
  event_version: 1;
  occurred_at: string;
  company_id: string;
  aggregate: {
    type: "interview_session";
    id: string;
    version: number;
  };
  idempotency_key: string;
  trace_id: string;
  correlation_id: string;
  causation_id: string | null;
  payload: {
    interview_session_id: string;
    session_sequence: number;
    technical_reason_code: string;
    retryable: boolean;
  };
};

export type InterviewCompletedEventV1 = {
  event_id: string;
  event_type: "interview.completed";
  event_version: 1;
  occurred_at: string;
  company_id: string;
  aggregate: {
    type: "interview_session";
    id: string;
    version: number;
  };
  idempotency_key: string;
  trace_id: string;
  correlation_id: string;
  causation_id: string | null;
  payload: {
    interview_session_id: string;
    invitation_id: string;
    last_turn_id: string;
    completed_at: string;
    media_status: "ready" | "pending" | "partial";
  };
};

export type MediaPostprocessRequestedEventV1 = {
  event_id: string;
  event_type: "media.postprocess_requested";
  event_version: 1;
  occurred_at: string;
  company_id: string;
  aggregate: {
    type: "recording_asset";
    id: string;
    version: number;
  };
  idempotency_key: string;
  trace_id: string;
  correlation_id: string;
  causation_id: string | null;
  payload: {
    interview_session_id: string;
    ordered_chunk_set_id: string;
    output_profile_version: string;
  };
};

export type ReportGenerationRequestedEventV1 = {
  event_id: string;
  event_type: "report.generation_requested";
  event_version: 1;
  occurred_at: string;
  company_id: string;
  aggregate: {
    type: "report";
    id: string;
    version: number;
  };
  idempotency_key: string;
  trace_id: string;
  correlation_id: string;
  causation_id: string | null;
  payload: {
    interview_session_id: string;
    report_version: number;
    competency_model_version_id: string;
  };
};

export type ReportReadyEventV1 = {
  event_id: string;
  event_type: "report.ready";
  event_version: 1;
  occurred_at: string;
  company_id: string;
  aggregate: {
    type: "report";
    id: string;
    version: number;
  };
  idempotency_key: string;
  trace_id: string;
  correlation_id: string;
  causation_id: string | null;
  payload: {
    interview_session_id: string;
    report_id: string;
    report_version: number;
    status: "ready" | "partial";
    confirmed_count: number;
    partially_confirmed_count: number;
    insufficient_evidence_count: number;
    needs_follow_up_count: number;
  };
};

export type DeletionRequestedEventV1 = {
  event_id: string;
  event_type: "deletion.requested";
  event_version: 1;
  occurred_at: string;
  company_id: string;
  aggregate: {
    type: "deletion_request";
    id: string;
    version: number;
  };
  idempotency_key: string;
  trace_id: string;
  correlation_id: string;
  causation_id: string | null;
  payload: {
    deletion_request_id: string;
    manifest_id: string;
    scope_type: "applicant" | "invitation";
    scope_id: string;
  };
};

export type DeletionTargetRequestedEventV1 = {
  event_id: string;
  event_type: "deletion.target_requested";
  event_version: 1;
  occurred_at: string;
  company_id: string;
  aggregate: {
    type: "deletion_request";
    id: string;
    version: number;
  };
  idempotency_key: string;
  trace_id: string;
  correlation_id: string;
  causation_id: string | null;
  payload: {
    deletion_request_id: string;
    manifest_id: string;
    owner_lane: "A" | "B" | "C" | "D";
    target_id: string;
    target_type: string;
    target_store: "aurora" | "dynamodb" | "s3" | "opensearch";
    target_version: number;
    verification_required: true;
  };
};

export type DeletionTargetVerifiedEventV1 = {
  event_id: string;
  event_type: "deletion.target_verified";
  event_version: 1;
  occurred_at: string;
  company_id: string;
  aggregate: {
    type: "deletion_request";
    id: string;
    version: number;
  };
  idempotency_key: string;
  trace_id: string;
  correlation_id: string;
  causation_id: string | null;
  payload: {
    deletion_request_id: string;
    target_id: string;
    status: "verified_absent";
    verified_at: string;
  };
};

export type RetentionExpiredEventV1 = {
  event_id: string;
  event_type: "retention.expired";
  event_version: 1;
  occurred_at: string;
  company_id: string;
  aggregate: {
    type: "invitation";
    id: string;
    version: number;
  };
  idempotency_key: string;
  trace_id: string;
  correlation_id: string;
  causation_id: string | null;
  payload: {
    invitation_id: string;
    applicant_id: string;
    policy_snapshot_id: string;
    expired_at: string;
  };
};

export type CampaignSnapshot = {
  company_id: string;
  campaign_id: string;
  position_id: string;
  competency_model_version_id: string;
  status: "draft" | "published" | "closed";
  prohibited_topics: Array<string>;
  interview_duration_minutes: number;
  persona_definition: Record<string, unknown>;
};

export type CriterionVersionSnapshot = {
  company_id: string;
  competency_model_version_id: string;
  position_id: string;
  version_number: number;
  status: "published" | "retired";
  criteria: Array<{
    criterion_id: string;
    code: string;
    name: string;
    description: string;
    weight: number;
    good_evidence: Record<string, unknown>;
    weak_evidence: Record<string, unknown>;
    abstain_guidance: string;
    common_questions: Array<string>;
    required: boolean;
  }>;
};

export type InvitationAuthorizationSnapshot = {
  company_id: string;
  invitation_id: string;
  applicant_id: string;
  campaign_id: string;
  state: string;
  expires_at: string;
  authorized: boolean;
  reason_code: string | null;
};

export type ConsentAuthorizationSnapshot = {
  company_id: string;
  invitation_id: string;
  consent_record_id: string;
  policy_version: string;
  purpose_codes: Array<string>;
  retention_days: number;
  accepted_at: string;
  withdrawn_at: string | null;
  authorized: boolean;
  reason_code: string | null;
};

export type InvitationStateTransitionSnapshot = {
  company_id: string;
  invitation_id: string;
  previous_state: string;
  state: string;
  row_version: number;
  applied: boolean;
  idempotency_key: string;
};

export type AuditAppendReceipt = {
  company_id: string;
  audit_event_id: string;
  action: string;
  resource_type: string;
  resource_id: string;
  result: "succeeded" | "denied" | "failed";
};

export type CompanyDeletionTargetEnumerationSnapshot = {
  company_id: string;
  scope_type: "invitation" | "applicant";
  scope_id: string;
  owner_lane: "A";
  targets: Array<{
    target_id: string;
    target_type: "applicant" | "audit_event" | "consent_record" | "invitation";
    store: "aurora";
    target_version: number;
  }>;
};

export type CompanyDeletionTargetReceipt = {
  company_id: string;
  deletion_request_id: string;
  target_id: string;
  owner_lane: "A";
  status: "deleting" | "retrying" | "failed" | "verified_absent";
  attempts: number;
  verified_at: string | null;
  error_code: string | null;
};

export type SubmissionAnalysisStatusSnapshot = {
  company_id: string;
  invitation_id: string;
  overall_status: "waiting" | "analyzing" | "ready" | "partial" | "failed";
  submissions: Array<{
    submission_id: string;
    status: "received" | "validating" | "analyzing" | "ready" | "partial" | "failed" | "deleted";
    impact_code: string | null;
  }>;
  strategy_ready: boolean;
};

export type StrategySnapshot = {
  company_id: string;
  invitation_id: string;
  interview_strategy_id: string;
  strategy_version: number;
  competency_model_version_id: string;
  status: "ready" | "partial" | "superseded";
  common_topics: Array<Record<string, unknown>>;
  verification_points: Array<Record<string, unknown>>;
  follow_up_directions: Record<string, unknown>;
  time_budget: Record<string, unknown>;
  required_evidence_plan: Record<string, unknown>;
  source_reference_candidates: Array<{
    source_type: "submission_chunk" | "candidate_code_unit";
    source_id: string;
    locator_version: number;
  }>;
  model_config_version: string;
};

export type RetrievedContextSnapshot = {
  company_id: string;
  applicant_id: string;
  interview_session_id: string;
  criterion_id: string;
  retrieval_config_version: string;
  results: Array<{
    rank: number;
    score: number;
    source_reference: {
      company_id: string;
      source_type: "submission_chunk" | "candidate_code_unit";
      source_id: string;
      source_version: number;
      source_location: Record<string, unknown>;
      ownership_confidence: number | null;
      source_hash: string;
      evidence_eligible: false;
    };
  }>;
};

export type SourceReferenceSnapshot = {
  company_id: string;
  source_type: "submission_chunk" | "candidate_code_unit";
  source_id: string;
  source_version: number;
  source_location: Record<string, unknown>;
  ownership_confidence: number | null;
  source_hash: string;
  evidence_eligible: false;
};

export type SubmissionDeletionTargetEnumerationSnapshot = {
  company_id: string;
  scope_type: "invitation" | "applicant";
  scope_id: string;
  owner_lane: "B";
  targets: Array<{
    target_id: string;
    target_type: string;
    store: "aurora" | "s3" | "opensearch";
    target_version: number;
  }>;
};

export type SubmissionDeletionTargetReceipt = {
  company_id: string;
  deletion_request_id: string;
  target_id: string;
  owner_lane: "B";
  status: "deleting" | "retrying" | "failed" | "verified_absent";
  attempts: number;
  verified_at: string | null;
  error_code: string | null;
};

export type SessionSnapshot = {
  company_id: string;
  interview_session_id: string;
  invitation_id: string;
  applicant_id: string;
  interview_strategy_id: string;
  competency_model_version_id: string;
  state: "preparing" | "in_progress" | "awaiting_answer" | "preparing_question" | "paused" | "completed" | "report_generating" | "reviewable";
  session_sequence: number;
  last_final_turn_id: string | null;
  last_verified_recording_chunk_sequence: number;
  degraded_modes: Array<string>;
};

export type FinalTurnSnapshot = {
  company_id: string;
  interview_session_id: string;
  turn_id: string;
  sequence: number;
  speaker: "interviewer" | "applicant";
  status: "final";
  text: string;
  target_criterion_id: string | null;
  model_config_version: string | null;
  finalized_at: string;
};

export type FinalTurnPageSnapshot = {
  company_id: string;
  interview_session_id: string;
  items: Array<{
    company_id: string;
    interview_session_id: string;
    turn_id: string;
    sequence: number;
    speaker: "interviewer" | "applicant";
    status: "final";
    text: string;
    target_criterion_id: string | null;
    model_config_version: string | null;
    finalized_at: string;
  }>;
  next_cursor: string | null;
};

export type RecordingChunkSetSnapshot = {
  company_id: string;
  interview_session_id: string;
  chunks: Array<{
    recording_chunk_id: string;
    sequence: number;
    object_ref: string;
    content_hash: string;
    byte_size: number;
    session_start_ms: number;
    session_end_ms: number;
    upload_status: "verified";
  }>;
};

export type InterviewDeletionTargetEnumerationSnapshot = {
  company_id: string;
  scope_type: "session" | "applicant";
  scope_id: string;
  owner_lane: "C";
  targets: Array<{
    target_id: string;
    target_type: string;
    store: "aurora" | "dynamodb" | "s3";
    target_version: number;
  }>;
};

export type InterviewDeletionTargetReceipt = {
  company_id: string;
  deletion_request_id: string;
  target_id: string;
  owner_lane: "C";
  status: "deleting" | "retrying" | "failed" | "verified_absent";
  attempts: number;
  verified_at: string | null;
  error_code: string | null;
};

export type ReviewProjectionSnapshot = {
  company_id: string;
  invitation_id: string;
  interview_session_id: string;
  report_id: string | null;
  report_status: "queued" | "generating" | "ready" | "partial" | "failed";
  summary_status: "unavailable" | "processing" | "ready" | "partial";
  human_decision_status: "advance" | "reject" | "hold" | "withdrawn" | null;
};

export type ReportSnapshot = {
  company_id: string;
  interview_session_id: string;
  report_id: string;
  report_version: number;
  competency_model_version_id: string;
  status: "generating" | "ready" | "partial" | "failed";
  summary: string;
  assessment_counts: {
    confirmed: number;
    partially_confirmed: number;
    insufficient_evidence: number;
    needs_follow_up: number;
  };
  items: Array<{
    report_item_id: string;
    criterion_id: string;
    competency_model_version_id: string;
    assessment_state: "confirmed" | "partially_confirmed" | "insufficient_evidence" | "needs_follow_up";
    observation: string;
    rationale: string;
    sufficiency: "sufficient" | "limited" | "insufficient";
    uncertainty: string;
    follow_up_question: string | null;
    evidence: Array<{
      evidence_id: string;
      evidence_type: "applicant_answer";
      company_id: string;
      criterion_id: string;
      competency_model_version_id: string;
      answer_turn_id: string;
      answer_turn_speaker: "applicant";
      answer_turn_status: "final";
      transcript_segment_id: string;
      video_start_ms: number;
      video_end_ms: number;
      technical_failure_overlap: false;
      observation: string;
      rationale: string;
      sufficiency: "direct" | "supporting" | "weak";
      generation_version: string;
    }>;
  }>;
  human_overrides: Array<{
    human_review_id: string;
    company_user_id: string;
    review_type: "assessment_override" | "note" | "bookmark" | "final_decision";
    target_id: string;
    value: Record<string, unknown>;
    reason: string;
    created_at: string;
  }>;
  human_decision_status: "advance" | "reject" | "hold" | "withdrawn" | null;
  ai_original_immutable: true;
};

export type DeletionStatusSnapshot = {
  company_id: string;
  deletion_request_id: string;
  manifest_id: string;
  status: "requested" | "enumerating" | "deleting" | "verifying" | "retrying" | "partially_completed" | "completed";
  expected_targets: number;
  verified_targets: number;
  targets: Array<{
    target_id: string;
    owner_lane: "A" | "B" | "C" | "D";
    store: "aurora" | "dynamodb" | "s3" | "opensearch";
    target_type: string;
    status: "pending" | "deleting" | "retrying" | "failed" | "verified_absent";
    attempts: number;
    verified_at: string | null;
    error_code: string | null;
  }>;
};
