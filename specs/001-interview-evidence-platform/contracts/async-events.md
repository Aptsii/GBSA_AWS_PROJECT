# Asynchronous Event Contract

**Envelope version**: `1.0`

Events contain identifiers and sanitized status only. Raw document text, answer text, credentials,
tokens and signed URLs are prohibited.

## Envelope

```json
{
  "event_id": "uuid",
  "event_type": "submission.analysis.requested",
  "event_version": 1,
  "occurred_at": "2026-08-14T00:00:00Z",
  "company_id": "uuid",
  "aggregate": {
    "type": "submission",
    "id": "uuid",
    "version": 3
  },
  "idempotency_key": "stable-operation-key",
  "trace_id": "opaque-trace-id",
  "correlation_id": "uuid",
  "causation_id": "uuid-or-null",
  "payload": {}
}
```

## Processing Rules

1. Producer stores the event in its durable outbox with the aggregate transaction.
2. Relay publishes at least once; order is guaranteed only within an aggregate.
3. Consumer validates schema and tenant scope before recording `ProcessedMessage`.
4. Duplicate event ID/version or idempotency key returns the recorded result.
5. Retryable failures use bounded exponential backoff; exhausted work moves to a DLQ.
6. A replay uses the original event ID and version and adds replay metadata outside the domain
   payload.
7. Unsupported major event versions are quarantined; they are not silently ignored.
8. Logs contain event IDs and sanitized codes only.

## Event Catalog

| Event | Producer | Consumer | Minimum payload |
|---|---|---|---|
| `invitation.consent_completed` v1 | A | B, C | invitation ID, applicant ID, consent record ID, purpose codes, retention snapshot |
| `submission.analysis_requested` v1 | B | B analysis worker | submission ID, analysis version, source type, object/reference ID |
| `submission.analysis_completed` v1 | B | A, C | invitation ID, submission ID, analysis ID, status, impact code |
| `strategy.ready` v1 | B | A, C | invitation ID, strategy ID/version, criterion version ID, status |
| `interview.turn_finalized` v1 | C | D | session ID, turn ID, sequence, speaker, transcript-ready flag |
| `interview.session_paused` v1 | C | A, D | session ID, sequence, technical reason code, retryable |
| `interview.completed` v1 | C | A, D | session ID, invitation ID, last Turn ID, completion time, media status |
| `media.postprocess_requested` v1 | D | D media worker | session ID, ordered chunk-set ID, output profile version |
| `report.generation_requested` v1 | D | D report worker | session ID, report version, criterion version ID |
| `report.ready` v1 | D | A | session ID, report ID/version, status, evidence coverage counts |
| `deletion.requested` v1 | D | A, B, C, D | deletion request ID, manifest ID, applicant/invitation/session scope |
| `deletion.target_requested` v1 | D | owning lane | deletion request ID, target ID/type/store, target version |
| `deletion.target_verified` v1 | A/B/C/D | D | deletion request ID, target ID, status, verification time |
| `retention.expired` v1 | A | D | invitation/applicant ID, policy snapshot ID, expiry time |

## Payload Details

### `submission.analysis_requested`

```json
{
  "submission_id": "uuid",
  "analysis_version": 1,
  "source_type": "pdf",
  "source_object_id": "uuid",
  "limits_config_version": "analysis-limits-v1"
}
```

The worker resolves the object through Lane B authorization; an S3 key is not required in the event.

### `interview.turn_finalized`

```json
{
  "interview_session_id": "uuid",
  "turn_id": "uuid",
  "turn_sequence": 8,
  "speaker": "applicant",
  "transcript_status": "final_or_review_required",
  "recording_range_status": "ready_or_pending"
}
```

Answer text is retrieved through Lane C's scoped interface only when Lane D builds Evidence.

### `report.ready`

```json
{
  "interview_session_id": "uuid",
  "report_id": "uuid",
  "report_version": 1,
  "status": "ready_or_partial",
  "confirmed_count": 2,
  "partially_confirmed_count": 1,
  "insufficient_evidence_count": 1,
  "needs_follow_up_count": 1
}
```

### `deletion.target_requested`

```json
{
  "deletion_request_id": "uuid",
  "manifest_id": "uuid",
  "target_id": "uuid",
  "target_type": "submission_chunk",
  "target_store": "opensearch",
  "target_version": 1,
  "verification_required": true
}
```

## State and Failure Semantics

- A completed event describes durable producer state; consumers may retrieve details later.
- A `partial` status is successful processing with explicit impact, not a transport failure.
- Consumer business rejection produces a non-retryable sanitized code.
- Dependency timeout, throttle or temporary unavailability is retryable.
- DLQ arrival creates an operational alert and a user-visible domain status where applicable.
- Deletion completion is impossible until every enumerated target reports `verified_absent`.

## Compatibility Test Fixtures

Each event version has:

- one minimum valid payload;
- one full payload;
- one duplicate-delivery scenario;
- one wrong-tenant rejection;
- one unsupported-version rejection;
- one retryable and one non-retryable failure fixture.
