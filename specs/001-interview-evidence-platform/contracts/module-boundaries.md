# Module Boundary Contract

**Version**: 1.0.0

This contract defines the only allowed cross-domain calls. Names describe application interfaces,
not concrete class locations.

## Common Types

```text
TenantContext {
  company_id: UUID
  actor_type: company_user | applicant | system
  actor_id: UUID
  request_id: UUID
  trace_id: string
}

EntityRef {
  company_id: UUID
  entity_type: string
  entity_id: UUID
  version?: integer
}

CommandMeta {
  idempotency_key: string
  expected_version?: integer
  occurred_at: timestamp
}
```

Every public call takes `TenantContext` first. Implementations MUST validate that every referenced
entity belongs to the context before returning data or performing side effects.

## Lane A Exports — Company Management

| Interface | Input | Output | Consumers |
|---|---|---|---|
| `get_campaign_snapshot` | campaign ID | position, published criterion version, prohibited topics, duration, persona | B, C, D |
| `get_criterion_version` | version ID | immutable criteria and observation rules | B, C, D |
| `authorize_invitation` | invitation ID, required state | applicant, campaign, expiry and authorization result | B, C, D |
| `get_consent_authorization` | invitation ID, required purposes | policy version, purposes, accepted/withdrawn state, retention snapshot | B, C, D |
| `advance_invitation_state` | invitation ID, from/to state, CommandMeta | new state and row version | B, C, D |
| `append_audit_event` | opaque resource/action/result metadata | audit event ID | A, B, C, D |

Lane A does not expose CompanyUser credentials, invitation raw tokens or mutable criterion internals.

## Lane B Exports — Submission Analysis

| Interface | Input | Output | Consumers |
|---|---|---|---|
| `get_analysis_status` | invitation ID | per-submission status, impact and strategy readiness | A, C |
| `get_strategy_snapshot` | strategy ID | immutable strategy, criterion version, time budget, source candidates | C |
| `retrieve_context` | applicant/session scope, query, criterion ID, config version | ranked source refs and scores | C |
| `resolve_source_reference` | chunk/code-unit ID and stored locator | immutable source location and ownership confidence | C, D |
| `enumerate_submission_deletion_targets` | invitation/applicant ID | owned durable/object/search target refs | D |
| `delete_submission_target` | deletion target, CommandMeta | deletion receipt and verification state | D |

Lane B does not expose raw applicant text through events. Consumers retrieve scoped content only
inside an authorized request and never place it in logs.

## Lane C Exports — Interview Engine

| Interface | Input | Output | Consumers |
|---|---|---|---|
| `get_session_snapshot` | session ID | state, sequence, strategy/version refs, last final Turn and degraded modes | A, D |
| `get_final_turn` | session ID, turn ID | immutable question/answer Turn | D |
| `list_final_turns` | session ID, cursor | ordered immutable Turns | D |
| `resolve_recording_chunks` | session ID | verified object refs and session-clock ranges | D |
| `enumerate_interview_deletion_targets` | session/applicant ID | session, Turn, checkpoint, hot-view and chunk targets | D |
| `delete_interview_target` | deletion target, CommandMeta | deletion receipt and verification state | D |

Lane C does not create ReportItem, Evidence, HumanReview or final hiring decisions.

## Lane D Exports — Reporting

| Interface | Input | Output | Consumers |
|---|---|---|---|
| `get_review_projection` | invitation/session ID | report readiness, summary status and human decision status | A |
| `get_report` | report ID/version | report, items, Evidence refs and human overrides | A |
| `request_deletion` | applicant/invitation scope, reason, requester | deletion request and manifest status | A |
| `get_deletion_status` | deletion request ID | per-store target and verification state | A |

Lane D does not modify campaigns, criteria, invitations, Strategies, Sessions or Turns.

## Dependency Direction

```text
HTTP/WebSocket routers -> own application service -> own domain -> own repositories/adapters
                                             |
                                             +-> declared module interface or domain event
```

Forbidden:

- import of another module's `domain/`, `repositories/`, `models/` or `internal/`;
- SQL joins or queries against another lane's owned table from a consumer repository;
- direct object-key construction outside the owning module;
- shared enums that duplicate a domain contract;
- consumer mutation of producer-owned rows;
- calling AWS SDK clients from domain models.

CI MUST maintain an import-boundary rule set and a repository query audit for these restrictions.

## Compatibility

- Additive optional response fields are backward compatible within a major version.
- New enum values require consumers to support an `unknown` or safe-default branch before publish.
- A required field, removed field/value, semantic change or renamed method requires a new major
  contract version.
- Consumers declare the supported version range; startup and worker registration fail fast on an
  incompatible version.
- A contract version remains available until all consumers have migrated and replayable events using
  the version have passed their retention window.
