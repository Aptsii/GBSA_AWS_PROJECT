# Interview WebSocket Contract

**Protocol version**: `1.0`

**Endpoint**: `/v1/applicant/interview-sessions/{session_id}/stream`

The applicant authenticates with the scoped HttpOnly session cookie established by token exchange.
The server validates that the session belongs to the invitation in that cookie.

## Envelope

Every client and server message uses:

```json
{
  "protocol_version": "1.0",
  "message_type": "namespace.action",
  "session_id": "uuid",
  "sequence": 42,
  "idempotency_key": "client-generated-or-server-event-key",
  "correlation_id": "uuid",
  "sent_at": "2026-08-14T00:00:00Z",
  "payload": {}
}
```

Rules:

- Client `sequence` is the last server sequence it has applied.
- State-changing client messages require a unique `idempotency_key`.
- Server `sequence` is the authoritative session sequence after the event.
- Repeated idempotency keys return the original result and do not create a new Turn or state.
- A stale sequence produces `resume.snapshot`; it never rolls server state backward.
- Binary audio frames are preceded by an `audio.chunk.begin` JSON envelope carrying metadata.
- Applicant/source text is allowed in protected message payloads but never copied to operational logs.

## Client Messages

### `session.start`

```json
{
  "payload": {
    "equipment_check_id": "uuid",
    "expected_state": "preparing"
  }
}
```

Accepted only when consent, invitation and strategy authorization are valid.

### `audio.chunk.begin`

```json
{
  "payload": {
    "answer_turn_id": "uuid",
    "chunk_sequence": 12,
    "codec": "pcm_s16le",
    "sample_rate_hz": 16000,
    "channel_count": 1,
    "byte_length": 32000,
    "sha256": "hex"
  }
}
```

The next binary frame must match the declared size and digest. Partial transcript results are
display-only.

### `answer.complete`

```json
{
  "payload": {
    "answer_turn_id": "uuid",
    "last_audio_chunk_sequence": 12,
    "last_recording_chunk_sequence": 5,
    "expected_state": "awaiting_answer"
  }
}
```

The server finalizes exactly one applicant Turn. Voluntary re-recording is not a valid message.

### `question.repeat`

```json
{
  "payload": {
    "question_turn_id": "uuid",
    "mode": "repeat_or_clarify"
  }
}
```

Repeating or clarifying a question does not penalize the applicant or change the target criterion.

### `session.resume`

```json
{
  "payload": {
    "last_applied_server_sequence": 42,
    "last_final_turn_id": "uuid-or-null",
    "last_uploaded_recording_chunk_sequence": 5
  }
}
```

The server always answers with `resume.snapshot`.

### `client.ack`

```json
{
  "payload": {
    "server_event_id": "uuid",
    "applied_sequence": 43
  }
}
```

### `heartbeat.ping`

Contains a client monotonic timestamp only. It has no state side effect.

## Server Messages

### `session.state_changed`

```json
{
  "payload": {
    "previous_state": "awaiting_answer",
    "state": "preparing_question",
    "reason_code": "answer_finalized",
    "checkpoint_id": "uuid"
  }
}
```

### `transcript.partial`

```json
{
  "payload": {
    "answer_turn_id": "uuid",
    "segment_sequence": 3,
    "text": "display-only partial text",
    "start_ms": 1200,
    "end_ms": 2500,
    "confidence": 0.82,
    "is_final": false
  }
}
```

Partial text is not persisted as final Evidence input.

### `transcript.final`

Uses the same shape with `is_final=true` and includes `transcript_segment_id`. Low confidence
adds `review_required=true`.

### `question.preparing`

```json
{
  "payload": {
    "stage": "retrieval_or_generation_or_policy_or_speech",
    "degraded_mode": "none_or_search_fallback_or_text_only"
  }
}
```

### `question.ready`

```json
{
  "payload": {
    "question_turn_id": "uuid",
    "text": "질문",
    "target_criterion_id": "uuid",
    "audio_url": "short-lived-url-or-null",
    "audio_expires_at": "timestamp-or-null",
    "speech_marks_url": "short-lived-url-or-null",
    "source_reference_count": 2,
    "text_only": false
  }
}
```

The contract never exposes model reasoning. `source_reference_count` is informational; scoped
source details are available only through authorized review APIs.

### `resume.snapshot`

```json
{
  "payload": {
    "state": "paused",
    "server_sequence": 43,
    "last_final_turn_id": "uuid",
    "pending_turn": {
      "turn_id": "uuid",
      "speaker": "interviewer",
      "status": "presented"
    },
    "last_verified_recording_chunk_sequence": 5,
    "allowed_client_messages": ["session.resume"],
    "degraded_modes": []
  }
}
```

### `session.paused`

Contains a technical `reason_code`, retryability, next retry time if known, and a Korean user
message. It is never an assessment signal.

### `session.completed`

Contains completed time, last Turn ID and post-processing status. No later answer mutation is allowed.

### `error`

```json
{
  "payload": {
    "code": "STALE_SEQUENCE",
    "message": "사용자에게 표시할 안전한 한국어 메시지",
    "retryable": true,
    "current_state": "paused",
    "current_sequence": 43
  }
}
```

## Close Codes

| Code | Meaning | Client action |
|---|---|---|
| 4001 | authentication expired or invalid | return to safe link verification |
| 4003 | session scope denied | stop; do not retry with same credential |
| 4008 | client message rate exceeded | back off and reconnect |
| 4009 | incompatible protocol version | refresh supported client |
| 4010 | session already completed | fetch completion status |
| 1011 | temporary server or dependency failure | preserve local chunks and resume |

## Protocol Acceptance

- A duplicated `answer.complete` creates one final Turn and returns the same result.
- A stale client receives a snapshot and cannot overwrite a newer state.
- Reconnect resumes from the last final Turn and verified media sequence.
- Search failure can produce a common-criterion question with a recorded degraded mode.
- Speech synthesis failure can produce a text-only question.
- No technical pause or objective observation changes criterion status.
