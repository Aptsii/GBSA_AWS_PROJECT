# Validation Report: Interview Evidence Platform

**Validation date**: 2026-08-17 (Asia/Seoul)
**Validated implementation commit**: `32b5bc3c99db2a76070f6d5fd608bc81b6b7b08a`
**Branch**: `feature/001-integration-hardening`
**Active lane**: Integration
**Overall implementation result**: PASS
**Unresolved critical implementation gaps**: 0

## Historical Correction

The validation report previously recorded commit `85f9a05e42f7c48175328bdb009faa49adc654f7`
as a complete PASS with zero unresolved gaps. That conclusion was premature and is superseded by
this report.

- The first post-report convergence pass appended T193-T203 because production runtime composition,
  queue workers, SPA route mounting, the composed journey, stage/prod state roots, deployment
  sequencing, authenticated stage smoke, shared pilot load, real browser playback measurement,
  production metrics, and final evidence reporting were still missing, partial, or contradictory.
- After T193-T202 were implemented, the next convergence pass appended T204-T205 for tenant-scoped
  human-review idempotency and the runtime-to-Terraform queue metric contract.
- T204 and T205 are now implemented and validated. The final convergence assessment found no new
  implementation tasks and left `tasks.md` byte-for-byte unchanged with SHA-256
  `870dab748865a1b67986813e37f4d209e28ec0038ca8bb5ac1dabebe5ef7c549`.

The earlier report remains useful only as historical execution evidence for the pre-convergence
state. It must not be used as the release conclusion.

## Execution Environment

| Component | Version or state |
|---|---|
| Host | macOS 15.7.7, Darwin 24.6.0 arm64 |
| Python | 3.13.7 |
| uv | 0.10.9 |
| Node.js | 22.14.0 |
| pnpm | 11.21.0 |
| Terraform | 1.15.8 |
| Docker | 28.3.3 |
| Docker Compose | 2.39.2-desktop.1 |
| Browser measurement | Connected Chrome extension browser against a local Vite fixture |
| Local services | PostgreSQL, LocalStack S3/SQS, DynamoDB Local, OpenSearch, API, worker, company SPA, applicant SPA: 8/8 healthy |

The validation environment used synthetic fixtures and opaque identifiers only. No permanent AWS
credential, applicant source text, applicant answer, signed URL value, or real personal data was
used or recorded.

## Versioned Contracts, Metrics, and Migrations

| Artifact | Validated version |
|---|---|
| OpenAPI | `3.1.0`, API version `1.0.0` |
| Module snapshots | catalog version `1.0.0` |
| Async event envelope | `1.0` |
| Async events | event version `1` with committed compatibility fixtures |
| WebSocket protocol | `1.0` |
| Operational metric schema | `1.0` |
| CloudWatch EMF namespace | `InterviewEvidence` |
| Queue age alarm metric | `QueueAgeSeconds`, unit `Seconds`, threshold 300 seconds |
| Alembic head | `m_003` after `m_001` lane merge and `m_002` shared runtime migration |
| Retrieval regression | `retrieval-regression-v1` |
| Question policy regression | `question-policy-v1` |
| Evidence policy regression | `evidence-policy-v1` |

`make contracts-check` and `make migration-check` passed before and after the integration drill.
Migration validation covered an empty database, upgrade from the previous integration snapshot,
downgrade, lane labels and prefixes, one Integration-owned final head, and ORM drift. T204's
`m_003` migration replaced the global human-review idempotency constraint with
`(company_id, idempotency_key)` without deleting or rewriting rows.

## Quickstart Command Record

Every shell command in `quickstart.md` was executed in document order against commit `32b5bc3`.
Repeated integration-drill commands were executed again rather than inferred from an earlier result.

| Result | Seconds | Command |
|---|---:|---|
| PASS | 0 | `make bootstrap` |
| PASS | 8 | `make compose-up` |
| PASS | 0 | `make migrate` |
| PASS | 1 | `make seed-contract-fixtures` |
| PASS | 1 | `make contracts-generate` |
| PASS | 1 | `make contracts-check` |
| PASS | 1 | `make boundaries-check` |
| PASS | 2 | `make migration-check` |
| PASS | 25 | `make test-foundation` |
| PASS | 3 | `make test-lane-a` |
| PASS | 1 | `make demo-lane-a` |
| PASS | 2 | `make test-lane-b` |
| PASS | 0 | `make demo-lane-b` |
| PASS | 2 | `make test-lane-c` |
| PASS | 0 | `make demo-lane-c` |
| PASS | 2 | `make test-lane-d` |
| PASS | 0 | `make demo-lane-d` |
| PASS | 4 | `make test-integration` |
| PASS | 1 | `make test-e2e-thin` |
| PASS | 0 | `make test-recovery` |
| PASS | 1 | `make test-tenant-isolation` |
| PASS | 0 | `make test-deletion-residue` |
| PASS | 0 | `make test-ai-regression` |
| PASS | 0 | `make test-load-pilot` |
| PASS | 0 | `make infra-format-check` |
| PASS | 139 | `make infra-validate` |
| PASS | 0 | `make infra-security-check` |
| PASS | 49 | `make infra-plan-dev` |
| PASS | 1 | `make contracts-check` |
| PASS | 8 | `make migration-check` |
| PASS | 46 | `make test-prior-lanes` |
| PASS | 3 | `make test-e2e-thin` |

The foundation run included 153 Python unit tests, 49 contract tests, 10 company-console tests,
12 applicant-interview tests, generated-contract drift, module boundaries, and migration
validation. `make test-integration` passed 18 Python tests and skipped the protected live-stage case,
then passed both SPA route suites. The live-stage test requires an approved AWS identity and explicit
`IEP_RUN_STAGE_SMOKE=1`; it was not silently counted as a local execution PASS.

## Post-Convergence Task Evidence

| Tasks | Evidence | Result |
|---|---|---|
| T193 | production `ApplicationRuntimes`, configured SQLAlchemy/AWS adapters, mounted `/v1` routers, OpenAPI/runtime tests | PASS |
| T194 | tenant-scoped versioned queue loop, durable processed-message state, retry/DLQ/ack/shutdown tests, `m_002` | PASS |
| T195 | both React Router feature registries mounted into the real SPA shells and navigation tests | PASS |
| T196 | composed company-to-human-decision thin journey over production runtime and local service adapters | PASS |
| T197 | independent `foundation`, `data-ai`, and `application` roots for stage and prod | PASS |
| T198 | all deployment roots selected, immutable `image_digest` task definitions registered, migrations awaited before ECS rollout | PASS |
| T199 | authenticated CloudFront-to-API stage business journey with configured AWS service assertions | Implementation PASS; protected live execution SKIPPED locally |
| T200 | shared production-like pilot runtime | PASS: 5/5 completed, ratio 1.0, 640 cumulative Turns, zero cross-company lookup success |
| T201 | real Chrome `<video>` playback measurement after signed retrieval | PASS: signed retrieval true, 93 ms playback start, 3 ms seek offset, 2,000 ms threshold |
| T202 | versioned API/worker EMF metrics for latency, retry, reconciliation lag, queue age, and degraded mode | PASS |
| T203 | this corrected report and complete affected-gate rerun | PASS |
| T204 | company-scoped human-review replay query, ORM constraint, `m_003`, cross-company same-key regression | PASS |
| T205 | runtime/Terraform namespace, queue name, unit, conversion, and cross-layer contract test | PASS |

## Functional Requirement Coverage

| Requirements | Primary automated evidence | Result |
|---|---|---|
| FR-001-FR-005 | Korean UI journeys, thin E2E, human-control checks, nonverbal exclusion, cross-store tenant isolation, T204 same-key regression | PASS |
| FR-006-FR-012 | Lane A HTTP contracts, criterion/persona/versioning/invitation tests, audit redaction, Lane A quickstart | PASS |
| FR-013-FR-015 | invitation access, consent policy/gate, A-to-B real boundary, thin journey | PASS |
| FR-016-FR-022 | submission contracts, document/code analysis units, partial analysis, retrieval isolation, Lane B quickstart | PASS |
| FR-023-FR-027 | applicant interview UI, session state/recording/transcription units, idempotency and recovery tests | PASS |
| FR-028-FR-030 | context reconciliation, question policy, B-to-C boundary, fixed question and retrieval regression | PASS |
| FR-031-FR-036 | WebSocket contracts, state sequence tests, checkpoint resume, degraded search/speech modes | PASS |
| FR-037-FR-041 | C-to-D boundary, timeline alignment, real browser playback, Evidence integrity, SourceReference/Evidence separation | PASS |
| FR-042-FR-045 | reporting contracts, report/review units, human-only decision integration, thin journey | PASS |
| FR-046-FR-048 | retention/deletion services, deletion manifest, full-store residue and retry suite, audit tests | PASS |
| FR-049-FR-050 | protected-value redaction, safe errors, bounded dependency failure tests, tenant-scoped queue worker | PASS |
| FR-051-FR-052 | versioned API/worker EMF, Terraform alarm contract, fixed regression corpora, pilot load and threshold enforcement | PASS |

## Success Criteria Coverage

| Criterion | Evidence | Result |
|---|---|---|
| SC-001 | Lane A campaign quickstart and company UI journey are executable | Implementation PASS; 30-minute field observation remains a pilot metric |
| SC-002 | Retrieval corpus scored 1.0 against a 0.75 threshold | Automated proxy PASS; company relevance survey remains a pilot metric |
| SC-003 | Evidence timeline, search, direct seek, and playback path are executable | Implementation PASS; 50% reviewer-time reduction remains a pilot metric |
| SC-004 | Evidence regression accepted all valid/invalid anchor cases | PASS |
| SC-005 | Report-state tests require Evidence or explicit insufficient/follow-up state | PASS |
| SC-006 | Human review, override, and immutable AI-original paths pass | Implementation PASS; satisfaction survey remains a pilot metric |
| SC-007 | Five shared-runtime sessions completed; ratio 1.0, required minimum 0.85 | PASS |
| SC-008 | Checkpoint recovery resumes without duplicate Turns | PASS |
| SC-009 | One-question policy, repeat request, and applicant interview UI pass | Implementation PASS; comprehension survey remains a pilot metric |
| SC-010 | Consent is recorded and processing without valid consent is rejected | PASS |
| SC-011 | No AI route, worker, or role can set the final hiring decision | PASS |
| SC-012 | Chrome playback began in 93 ms with 3 ms seek error after signed retrieval; threshold 2 seconds | PASS |
| SC-013 | Five concurrent sessions and 640 cumulative Turns completed without tenant mixing | PASS |
| SC-014 | Cross-route, worker, repository, search, object, hot-view, and same-key replay isolation returned zero leaks | PASS |
| SC-015 | Deletion completion requires verified absence across every durable and derived target | PASS |
| SC-016 | Unsupported claims never became confirmed or partially confirmed Evidence | PASS |

## Quality Gate Coverage

| Gate | Automated evidence | Result |
|---|---|---|
| QG-01 | production runtime composition, four real cross-module boundaries, and composed thin journey | PASS |
| QG-02 | Evidence integrity units and Evidence regression corpus | PASS |
| QG-03 | human-control E2E and human-only decision integration | PASS |
| QG-04 | route, repository, worker, object, hot-view, and human-review idempotency tenant isolation | PASS |
| QG-05 | consent gate, retention/deletion services, and audit tests | PASS |
| QG-06 | full-store deletion residue and retry verification | PASS |
| QG-07 | static/runtime no-nonverbal-scoring suite | PASS |
| QG-08 | idempotency, queue replay, session recovery, WebSocket protocol, and checkpoint tests | PASS |
| QG-09 | exact source location and SourceReference regression checks | PASS |
| QG-10 | applicant-scoped retrieval and cross-tenant search isolation | PASS |
| QG-11 | production-contract Compose stack, production router mounting, and 8/8 healthy services | PASS |
| QG-12 | versioned fixed corpora and regression threshold runner | PASS |
| QG-13 | deploy workflow contract, API/worker images, migration-gated ECS rollout, authenticated stage smoke implementation | Implementation PASS; live stage Apply/smoke remains protected and was skipped locally |
| QG-14 | private storage/database Terraform assertions, KMS/Secrets/WAF resources, stage security smoke assertions | PASS for code and plan; live verification remains deployment-gated |
| QG-15 | commit/code-unit analysis, exact-symbol retrieval, and source-location regression | PASS |
| QG-16 | split stage/prod state roots, roles, lockfile backends, protected resources, migration lifecycle, validate, and no-apply dev plans | PASS for reproducibility checks; real Apply requires a reviewed saved plan and human approval |

## Failure, Privacy, Load, and Observability Observations

- **Retry/idempotency**: duplicate answer completion, queue delivery, and human-review replay produced
  one durable result inside a company; the same review key was accepted independently for another
  company; incompatible same-company replays remained conflicts.
- **Recovery**: reconnect resumed from the latest final Turn and checkpoint without duplicate Turns.
- **Degraded modes**: search and speech failure produced explicit fallback states; no technical
  failure became competency Evidence. Degraded-mode counters are emitted at API/worker boundaries.
- **Queue observability**: runtime emits schema `1.0` EMF in namespace `InterviewEvidence`; queue age
  is converted from milliseconds to `QueueAgeSeconds` with CloudWatch unit `Seconds`, matching the
  Terraform alarm.
- **Deletion**: completion remained false until relational, hot-view, object, search, summary, and
  recent-context targets all verified absence; retry remained idempotent.
- **Regression**: retrieval 4/4, questions 7/7, and Evidence 6/6 passed their versioned thresholds.
- **Load**: 5 concurrent sessions completed at 100%; the long-running scenario produced 240 Turns;
  the combined run produced 640 Turns with no tenant mixing.
- **Evidence seek**: the deterministic service benchmark measured a maximum 0.000382334 seconds,
  p95 0.000376 seconds, and 0 ms seek error over 500 segments and 200 iterations. The real Chrome
  fixture measured signed retrieval true, 93 ms to `playing`, and 3 ms seek error.
- **Stage smoke**: authenticated business-journey and AWS resource assertions are implemented. The
  local run intentionally skipped the protected stage execution because no approved stage identity
  and no `IEP_RUN_STAGE_SMOKE=1` opt-in were provided.

## Review and Release Gates

- **Integration evidence reviewer**: Codex CLI coding agent, acting under repository-owner
  authorization in this thread on 2026-08-17.
- **Reviewer-owned readiness checklists**: `parallel-readiness.md` CHK001-CHK034 and
  `requirements.md` are complete.
- **Human-only product decision gate**: runtime tests use an authorized synthetic company principal;
  AI and system principals are rejected.
- **Convergence gate**: no new implementation findings after T204-T205; `tasks.md` remained
  byte-for-byte unchanged.
- **Stage/prod infrastructure approval**: not exercised locally. A named human approver must review
  the saved Terraform plan before Apply, as enforced by the deployment workflow.

There are no unresolved critical implementation gaps in the validated repository state. Remaining
field surveys, live stage Apply, live stage smoke, and production approval are external acceptance or
release activities; they are not silently treated as completed by this report.
