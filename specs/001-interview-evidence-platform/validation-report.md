# Validation Report: Interview Evidence Platform

**Validation date**: 2026-08-17 (Asia/Seoul)  
**Executed commit**: `85f9a05e42f7c48175328bdb009faa49adc654f7`  
**Branch**: `feature/001-integration-hardening`  
**Active lane**: Integration  
**Overall implementation result**: PASS  
**Unresolved critical implementation gaps**: 0

## Execution Environment

| Component | Version or state |
|---|---|
| Host | Darwin 24.6.0 arm64 |
| Python | 3.13.7 |
| uv | 0.10.9 |
| Node.js | 22.14.0 |
| pnpm | 11.21.0 |
| Terraform | 1.15.8 |
| Docker | 28.3.3 |
| Docker Compose | 2.39.2-desktop.1 |
| Local services | PostgreSQL, LocalStack S3/SQS, DynamoDB Local, OpenSearch, API, worker, company SPA, applicant SPA: 8/8 healthy |

The validation environment used synthetic fixtures and opaque identifiers only. No permanent AWS
credential, applicant source text, applicant answer, signed URL, or real personal data was used.

## Versioned Contracts and Migrations

| Artifact | Validated version |
|---|---|
| OpenAPI | `3.1.0`, API version `1.0.0` |
| Module snapshots | catalog version `1.0.0` |
| Async event envelope | `1.0` |
| Async events | event version `1` with committed compatibility fixtures |
| WebSocket protocol | `1.0` |
| Alembic head | `m_001` merging `a_001`, `b_001`, `c_001`, and `d_001` |
| Retrieval regression | `retrieval-regression-v1` |
| Question policy regression | `question-policy-v1` |
| Evidence policy regression | `evidence-policy-v1` |

`make contracts-check` and `make migration-check` passed both before and after the four-lane
integration drill. Migration validation covered an empty database, the previous four-head snapshot,
downgrade, branch labels and prefixes, and ORM drift.

## Quickstart Command Record

Every command in `quickstart.md` was executed in document order. Repeated integration-drill commands
were executed again rather than inferred from an earlier result.

| Result | Seconds | Command |
|---|---:|---|
| PASS | 0 | `make bootstrap` |
| PASS | 2 | `make compose-up` |
| PASS | 1 | `make migrate` |
| PASS | 0 | `make seed-contract-fixtures` |
| PASS | 1 | `make contracts-generate` |
| PASS | 1 | `make contracts-check` |
| PASS | 1 | `make boundaries-check` |
| PASS | 3 | `make migration-check` |
| PASS | 25 | `make test-foundation` |
| PASS | 3 | `make test-lane-a` |
| PASS | 0 | `make demo-lane-a` |
| PASS | 2 | `make test-lane-b` |
| PASS | 0 | `make demo-lane-b` |
| PASS | 2 | `make test-lane-c` |
| PASS | 0 | `make demo-lane-c` |
| PASS | 2 | `make test-lane-d` |
| PASS | 0 | `make demo-lane-d` |
| PASS | 4 | `make test-integration` |
| PASS | 0 | `make test-e2e-thin` |
| PASS | 0 | `make test-recovery` |
| PASS | 1 | `make test-tenant-isolation` |
| PASS | 0 | `make test-deletion-residue` |
| PASS | 0 | `make test-ai-regression` |
| PASS | 0 | `make test-load-pilot` |
| PASS | 0 | `make infra-format-check` |
| PASS | 78 | `make infra-validate` |
| PASS | 0 | `make infra-security-check` |
| PASS | 49 | `make infra-plan-dev` |
| PASS | 1 | `make contracts-check` |
| PASS | 4 | `make migration-check` |
| PASS | 9 | `make test-prior-lanes` |
| PASS | 0 | `make test-e2e-thin` |

The foundation run included 141 Python unit tests, 46 contract tests, all frontend workspace tests,
contract drift, module boundaries, and migration validation. The stage smoke test is collected by
`make test-integration` and safely skips unless an approved stage configuration and AWS identity are
explicitly supplied.

## Task Evidence

| Tasks | Evidence | Result |
|---|---|---|
| T160-T169 | `infra/modules/`, environment roots, `infra/tests/test_infrastructure_contract.py`, `make infra-validate`, `make infra-security-check`, `make infra-plan-dev` | PASS for static validation and no-apply plans |
| T170 | `.github/workflows/deploy.yml`, `backend/tests/contract/test_deploy_workflow.py` | PASS |
| T171 | `backend/alembic/versions/merge/m_001_lane_merge.py`, `scripts/check_migrations.sh` | PASS |
| T172-T175 | `backend/tests/integration/cross_module/` | PASS |
| T176 | `backend/src/interview_evidence/main.py`, `backend/tests/unit/test_main.py`, worker lifecycle test | PASS |
| T177 | both `featureRoutes.ts` registries and registry tests | PASS |
| T178 | `compose.yaml`, compose contract tests, 8/8 healthy services | PASS |
| T179-T182 | thin journey, tenant isolation, deletion residue, and human-control E2E suites | PASS |
| T183-T186 | fixed retrieval/question/Evidence corpora and versioned regression runner | PASS: retrieval 4/4, question 7/7, Evidence 6/6 |
| T187 | `tests/load/interview_load.py` | PASS: 5/5 completed, ratio 1.0, 640 cumulative Turns |
| T188 | `tests/load/evidence_seek.py` | PASS: max 0.000401 seconds, 0 ms seek error |
| T189 | `tests/e2e/test_stage_smoke.py` | PASS as an enabled, read-only stage gate; local run skipped by configuration |
| T190 | complete quickstart command record above | PASS |
| T191 | this report | PASS |

## Functional Requirement Coverage

| Requirements | Primary automated evidence | Result |
|---|---|---|
| FR-001-FR-005 | Korean UI journeys, thin E2E, human-control static/runtime checks, cross-store tenant isolation | PASS |
| FR-006-FR-012 | Lane A HTTP contracts, criterion/versioning/invitation tests, audit redaction, Lane A quickstart | PASS |
| FR-013-FR-015 | invitation access, consent policy/gate, A-to-B real boundary, thin journey | PASS |
| FR-016-FR-022 | submission contracts, document/code analysis units, partial analysis, retrieval isolation, Lane B quickstart | PASS |
| FR-023-FR-027 | applicant interview UI, session state/recording/transcription units, idempotency and recovery tests | PASS |
| FR-028-FR-030 | context reconciliation, question policy, B-to-C boundary, fixed question and retrieval regression | PASS |
| FR-031-FR-036 | WebSocket contracts, state sequence tests, checkpoint resume, degraded search/speech modes | PASS |
| FR-037-FR-041 | C-to-D boundary, timeline alignment, Evidence integrity, SourceReference/Evidence separation | PASS |
| FR-042-FR-045 | reporting contracts, report/review units, human-only decision integration, thin journey | PASS |
| FR-046-FR-048 | retention/deletion services, deletion manifest, full-store residue and retry suite, audit tests | PASS |
| FR-049-FR-050 | protected-value redaction, safe errors, bounded dependency failure tests, worker/deployment isolation | PASS |
| FR-051-FR-052 | versioned regression metrics, pilot load metrics, fixed corpora and threshold enforcement | PASS |

## Success Criteria Coverage

| Criterion | Evidence | Result |
|---|---|---|
| SC-001 | Lane A campaign quickstart and company UI journey are executable | Implementation PASS; 30-minute field observation remains a pilot metric |
| SC-002 | Retrieval corpus scored 1.0 against a 0.75 threshold | Automated proxy PASS; company relevance survey remains a pilot metric |
| SC-003 | Evidence timeline and direct seek path are implemented and measured | Implementation PASS; 50% reviewer-time reduction remains a pilot metric |
| SC-004 | Evidence regression accepted all valid/invalid anchor cases | PASS |
| SC-005 | Report-state tests require Evidence or explicit insufficient/follow-up state | PASS |
| SC-006 | Human review, override and immutable AI-original paths pass | Implementation PASS; satisfaction survey remains a pilot metric |
| SC-007 | Concurrent session completion ratio 1.0, required minimum 0.85 | PASS |
| SC-008 | Checkpoint recovery resumes without duplicate Turns | PASS |
| SC-009 | One-question policy, repeat request and applicant interview UI pass | Implementation PASS; comprehension survey remains a pilot metric |
| SC-010 | Consent is recorded and processing without valid consent is rejected | PASS |
| SC-011 | No AI route, worker or role can set the final hiring decision | PASS |
| SC-012 | Evidence seek maximum 0.000401 seconds, required maximum 2 seconds | PASS |
| SC-013 | Five concurrent sessions and 640 cumulative Turns completed without tenant mixing | PASS |
| SC-014 | Cross-route, worker, repository, search, object and hot-view isolation returned zero leaks | PASS |
| SC-015 | Deletion completion requires verified absence across every durable and derived target | PASS |
| SC-016 | Unsupported claims never became confirmed or partially confirmed Evidence | PASS |

## Quality Gate Coverage

| Gate | Automated evidence | Result |
|---|---|---|
| QG-01 | four real cross-module boundaries and `tests/e2e/test_thin_journey.py` | PASS |
| QG-02 | Evidence integrity unit tests and Evidence regression corpus | PASS |
| QG-03 | human-control E2E and human-only decision integration | PASS |
| QG-04 | route, repository, worker, object and hot-view tenant isolation | PASS |
| QG-05 | consent gate, retention/deletion services and audit tests | PASS |
| QG-06 | full-store deletion residue and retry verification | PASS |
| QG-07 | static/runtime no-nonverbal-scoring suite | PASS |
| QG-08 | idempotency, session recovery, WebSocket protocol and checkpoint tests | PASS |
| QG-09 | exact source location and SourceReference regression checks | PASS |
| QG-10 | applicant-scoped retrieval and cross-tenant search isolation | PASS |
| QG-11 | production-contract Compose stack, health checks and 8/8 healthy services | PASS |
| QG-12 | versioned fixed corpora and regression threshold runner | PASS |
| QG-13 | deploy workflow contract, API/worker images, stage smoke implementation | Implementation PASS; live stage Apply/smoke is an external protected-environment gate |
| QG-14 | private storage/database Terraform assertions, KMS/Secrets/WAF resources, stage security smoke assertions | PASS for code and plan; live stage verification is deployment-gated |
| QG-15 | commit/code-unit analysis, exact-symbol retrieval and source-location regression | PASS |
| QG-16 | separate state roots/roles, lockfile backends, protected resources, validate and no-apply dev plans | PASS for reproducibility checks; real Apply requires reviewed saved plan and human approval |

## Failure, Privacy and Regression Observations

- **Retry/idempotency**: duplicate answer completion and job replay produced one durable result;
  incompatible replays remained conflicts.
- **Recovery**: reconnect resumed from the latest final Turn and checkpoint without duplicate Turns.
- **Degraded modes**: search and speech failure produced explicit fallback states; no technical failure
  became competency Evidence.
- **Deletion**: completion remained false until relational, hot-view, object, search, summary and recent
  context targets all verified absence; retry remained idempotent.
- **Regression**: retrieval 4/4, questions 7/7 and Evidence 6/6 passed their versioned thresholds.
- **Load**: 5 concurrent sessions completed at 100%; the long-running scenario produced 240 Turns;
  the combined run produced 640 Turns with no tenant mixing.
- **Evidence seek**: 500 transcript segments over 200 iterations produced 0 ms seek-offset error and
  a maximum service-ready latency of 0.000401 seconds.
- **Stage smoke**: the read-only CloudFront, ALB/ECS, S3, DynamoDB, SQS, Aurora, KMS, Secrets Manager,
  OpenSearch Serverless, Bedrock guardrail and WAF checks are present but were not run without an
  approved stage account and explicit `IEP_RUN_STAGE_SMOKE=1` configuration.

## Review and Release Gates

- **Integration evidence reviewer**: Codex CLI coding agent, acting under repository-owner
  authorization in this thread on 2026-08-17.
- **Reviewer-owned readiness checklists**: `parallel-readiness.md` CHK001-CHK034 and
  `requirements.md` are complete.
- **Human-only product decision gate**: runtime tests use an authorized synthetic company principal;
  AI and system principals are rejected.
- **Stage/prod infrastructure approval**: not exercised locally. A named human approver must review
  the saved Terraform plan before Apply, as enforced by the deployment workflow.

There are no unresolved critical implementation gaps in the validated repository state. Remaining
field surveys, live stage Apply, live stage smoke and production approval are external acceptance or
release activities; they are not silently treated as completed by this report.
