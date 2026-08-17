---
description: "Dependency-ordered, four-lane implementation tasks"
---

# Tasks: Interview Evidence Platform

**Input**: Design documents from `/specs/001-interview-evidence-platform/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/](./contracts/),
[parallel-workstreams.md](./parallel-workstreams.md)

**Tests**: Required by Constitution Principle IV. For each domain rule or contract, commit the test
before or with implementation and observe it fail against the previous state.

**Organization**: Setup and Foundation are integration-owned. After `foundation-v1`, US1/US2/US3/US4
map one-to-one to Lane A/B/C/D and run in four worktrees.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it writes a different owned file and has no incomplete dependency.
- **[Story]**: User story mapping for traceability.
- Every description names the owner, requirement/gate coverage and an exact file path.

## Phase 1: Setup (Integration Owner)

**Purpose**: Create the shared monorepo skeleton without implementing domain behavior.

- [X] T001 Integration — Define JavaScript workspaces and root scripts in `package.json`
- [X] T002 [P] Integration — Define the locked Python workspace, FastAPI and test dependencies in `pyproject.toml`
- [X] T003 [P] Integration — Define local PostgreSQL, DynamoDB, S3/SQS emulation and search services in `compose.yaml`
- [X] T004 Integration — Add the documented bootstrap, generation and test entry points to `Makefile`
- [X] T005 [P] Integration — Document safe local configuration with no credentials in `.env.example`
- [X] T006 [P] Integration — Scaffold the company Vite application and feature slots in `apps/company-console/package.json`
- [X] T007 [P] Integration — Scaffold the applicant Vite application and feature slots in `apps/applicant-interview/package.json`
- [X] T008 [P] Integration — Scaffold the Python package and API/worker entry points in `backend/src/interview_evidence/__init__.py`
- [X] T009 [P] Lane A — Create the approved Terraform directory roots in `infra/README.md` (PD-26, QG-16)
- [X] T010 [P] Integration — Create shared end-to-end, fixture, regression and load test roots in `tests/README.md`
- [X] T011 [P] Integration — Configure editor, Markdown, Python, TypeScript and Terraform formatting in `.editorconfig`
- [X] T012 [P] Integration — Add API and worker container build targets in `backend/Containerfile`
- [X] T013 Integration — Document directory ownership and local setup in `README.md`
- [X] T014 Integration — Add baseline format, type, unit and artifact-drift jobs in `.github/workflows/ci.yml`

**Checkpoint**: All planned paths exist; no domain behavior has been implemented.

---

## Phase 2: Foundation (Blocks All Four Lanes)

**Purpose**: Freeze contracts, shared primitives, fakes, migration rules and CI before branching.

**Critical**: Complete and review `checklists/parallel-readiness.md`, then tag one common
`foundation-v1` commit. No lane branches from an earlier commit.

- [X] T015 Integration — Copy and split the canonical REST contract into lane fragments under `packages/contracts/openapi/root.yaml` (FR-005, QG-04)
- [X] T016 [P] Integration — Encode the WebSocket envelope and message schemas in `packages/contracts/events/websocket/v1/` (FR-032-FR-035, QG-08)
- [X] T017 [P] Integration — Encode the async envelope and domain event schemas in `packages/contracts/events/common/v1/envelope.json` (FR-050)
- [X] T018 Integration — Generate and commit Python/TypeScript contract types from canonical schemas in `packages/contracts/generated/README.md`
- [X] T019 Integration — Add generated-type and canonical-contract drift tests in `backend/tests/contract/test_generated_contract_drift.py`
- [X] T020 [P] Integration — Implement opaque IDs, clocks and CommandMeta primitives in `backend/src/interview_evidence/shared/ids.py`
- [X] T021 [P] Integration — Implement required TenantContext and scope guards in `backend/src/interview_evidence/shared/tenant.py` (FR-005, QG-04)
- [X] T022 [P] Integration — Implement the safe error envelope and error catalog in `backend/src/interview_evidence/shared/errors.py` (FR-049)
- [X] T023 [P] Integration — Implement typed configuration with secret-safe rendering in `backend/src/interview_evidence/shared/config.py` (FR-049)
- [X] T024 [P] Integration — Define company/applicant principal interfaces and deterministic auth fakes in `backend/src/interview_evidence/shared/security/principals.py` (FR-006, FR-013)
- [X] T025 [P] Integration — Define storage, queue, AI, search, speech and email ports plus fakes in `backend/src/interview_evidence/shared/aws_clients/ports.py`
- [X] T026 Integration — Implement OutboxEvent and ProcessedMessage primitives in `backend/src/interview_evidence/shared/messaging/outbox.py` (FR-032, FR-050)
- [X] T027 [P] Integration — Implement the protected audit append interface in `backend/src/interview_evidence/shared/audit.py` (FR-048, FR-049)
- [X] T028 Integration — Configure four Alembic version locations and branch labels in `backend/alembic.ini` (QG-16)
- [X] T029 Integration — Add lane-head, prefix, downgrade and ORM drift validation in `scripts/check_migrations.sh` (QG-16)
- [X] T030 [P] Integration — Add forbidden cross-module import rules in `scripts/check_module_boundaries.py`
- [X] T031 [P] Integration — Create tenant, criterion, invitation, strategy, session and report contract fixtures in `tests/fixtures/shared/factories.py`
- [X] T032 Integration — Create root router composition without domain-private imports in `backend/src/interview_evidence/main.py`
- [X] T033 [P] Integration — Create feature-route registries for both SPAs in `apps/company-console/src/app/featureRoutes.ts` and `apps/applicant-interview/src/app/featureRoutes.ts`
- [X] T034 Integration — Add structured logging, trace propagation and prohibited-field tests in `backend/src/interview_evidence/shared/observability.py` (FR-049, FR-051)
- [X] T035 Integration — Add the complete foundation gate and tag verification in `scripts/verify_foundation.sh`

**Checkpoint**: Contract generation is clean, fakes conform, boundary and migration checks pass, and
all four worktrees can start from the same `foundation-v1` commit.

---

## Phase 3: User Story 1 — Company Criteria and Invitation (Lane A, Priority P1)

**Goal**: A company creates a fixed criterion version and campaign, invites an applicant, and records
identity and consent with complete tenant isolation.

**Independent Test**: Run `make test-lane-a demo-lane-a` with only shared fakes for B/C/D.

### Tests for User Story 1

- [ ] T036 [P] [US1] Lane A — Add HTTP contract tests for company, position, criteria, campaign, invitation and applicant access routes in `backend/tests/contract/company_management/test_http_contract.py` (FR-006-FR-015)
- [ ] T037 [P] [US1] Lane A — Add repository and route cross-tenant denial tests in `backend/tests/integration/company_management/test_tenant_isolation.py` (FR-005, SC-014, QG-04)
- [ ] T038 [P] [US1] Lane A — Add published criterion immutability and campaign version-pin tests in `backend/tests/unit/company_management/test_criterion_versioning.py` (FR-010)
- [ ] T039 [P] [US1] Lane A — Add invitation entropy, hash-only persistence, expiry, reuse and state-transition tests in `backend/tests/unit/company_management/test_invitation_access.py` (FR-011-FR-013)
- [ ] T040 [P] [US1] Lane A — Add consent-before-processing and withdrawal authorization tests in `backend/tests/unit/company_management/test_consent_policy.py` (FR-014-FR-015, SC-010, QG-05)
- [ ] T041 [P] [US1] Lane A — Add safe audit/log projection tests in `backend/tests/integration/company_management/test_audit_redaction.py` (FR-048-FR-049)
- [ ] T042 [P] [US1] Lane A — Add company position/campaign journey component tests in `apps/company-console/src/features/hiring/__tests__/campaignJourney.test.tsx` (SC-001)
- [ ] T043 [P] [US1] Lane A — Add applicant token exchange, identity and consent component tests in `apps/applicant-interview/src/features/access/__tests__/accessJourney.test.tsx` (FR-013-FR-015)

### Implementation for User Story 1

- [ ] T044 [US1] Lane A — Create company-domain tables and constraints in `backend/alembic/versions/company/a_001_company_hiring.py` (FR-005-FR-012)
- [ ] T045 [P] [US1] Lane A — Implement Company, CompanyUser and Position domain models in `backend/src/interview_evidence/company_management/domain/company.py` (FR-006-FR-007)
- [ ] T046 [P] [US1] Lane A — Implement CompetencyModelVersion and EvaluationCriterion invariants in `backend/src/interview_evidence/company_management/domain/criteria.py` (FR-008-FR-010)
- [ ] T047 [P] [US1] Lane A — Implement Campaign, Invitation and state transitions in `backend/src/interview_evidence/company_management/domain/hiring.py` (FR-011-FR-012)
- [ ] T048 [P] [US1] Lane A — Implement ConsentRecord, ApplicantProfile and processing authorization in `backend/src/interview_evidence/company_management/domain/applicant_access.py` (FR-013-FR-015)
- [ ] T049 [US1] Lane A — Implement tenant-mandatory company repositories in `backend/src/interview_evidence/company_management/repositories/postgres.py` (FR-005, QG-04)
- [ ] T050 [P] [US1] Lane A — Implement company principal validation and auth adapter in `backend/src/interview_evidence/company_management/adapters/company_auth.py` (FR-006)
- [ ] T051 [P] [US1] Lane A — Implement raw-token exchange, hash verification and scoped applicant session adapter in `backend/src/interview_evidence/company_management/adapters/applicant_session.py` (FR-011, FR-013)
- [ ] T052 [US1] Lane A — Implement company/position application services and public module exports in `backend/src/interview_evidence/company_management/application/company_service.py` (FR-006-FR-007)
- [ ] T053 [US1] Lane A — Implement criterion draft/publish/version services in `backend/src/interview_evidence/company_management/application/criteria_service.py` (FR-008-FR-010)
- [ ] T054 [US1] Lane A — Implement campaign/invitation issuance and state-history services in `backend/src/interview_evidence/company_management/application/hiring_service.py` (FR-011-FR-012)
- [ ] T055 [US1] Lane A — Implement identity and consent services with outbox events in `backend/src/interview_evidence/company_management/application/applicant_access_service.py` (FR-013-FR-015)
- [ ] T056 [US1] Lane A — Implement company and hiring API fragment with protected-resource audit events in `backend/src/interview_evidence/company_management/api/company_routes.py` (FR-006-FR-012, FR-048)
- [ ] T057 [US1] Lane A — Implement applicant access API fragment in `backend/src/interview_evidence/company_management/api/applicant_routes.py` (FR-013-FR-015)
- [ ] T058 [P] [US1] Lane A — Implement Korean company, position and campaign screens in `apps/company-console/src/features/hiring/index.tsx` (FR-001, FR-007-FR-012, SC-001)
- [ ] T059 [P] [US1] Lane A — Implement Korean token exchange, identity and consent screens in `apps/applicant-interview/src/features/access/index.tsx` (FR-001, FR-013-FR-015, SC-010)
- [ ] T060 [P] [US1] Lane A — Implement invitation email event handler without exposing raw tokens in logs in `backend/src/interview_evidence/company_management/workers/invitation_email.py` (FR-011, FR-049)
- [ ] T061 [P] [US1] Lane A — Implement retention-expiry events and owned relational/audit deletion targets in `backend/src/interview_evidence/company_management/application/deletion_targets.py` (FR-046-FR-047)
- [ ] T062 [US1] Lane A — Define dev company/tenant identity and retention inputs in `infra/environments/dev/foundation/variables.tf` (PD-03, PD-26, QG-13-QG-16)
- [ ] T063 [US1] Lane A — Complete the isolated Lane A journey in `backend/tests/integration/company_management/test_lane_a_quickstart.py` (US1, QG-04-QG-05)

**Checkpoint**: Lane A works against B/C/D fakes and exports only the frozen module contract.

---

## Phase 4: User Story 2 — Applicant Materials and Strategy (Lane B, Priority P1)

**Goal**: A consented applicant submits documents and a public repository; analysis creates
traceable source chunks and a versioned interview strategy.

**Independent Test**: Run `make test-lane-b demo-lane-b` with Lane A authorization fixtures and
Lane C/D fakes.

### Tests for User Story 2

- [ ] T064 [P] [US2] Lane B — Add submission HTTP contract tests in `backend/tests/contract/submission_analysis/test_http_contract.py` (FR-016-FR-022)
- [ ] T065 [P] [US2] Lane B — Add consent and invitation authorization rejection tests in `backend/tests/integration/submission_analysis/test_consent_gate.py` (FR-015)
- [ ] T066 [P] [US2] Lane B — Add document extraction, chunk locator and content-hash tests in `backend/tests/unit/submission_analysis/test_document_chunking.py` (FR-017-FR-018, QG-09)
- [ ] T067 [P] [US2] Lane B — Add tenant/applicant pre-filter and cross-scope retrieval tests in `backend/tests/integration/submission_analysis/test_retrieval_isolation.py` (FR-005, SC-014, QG-10)
- [ ] T068 [P] [US2] Lane B — Add candidate commit, AST ownership region and low-confidence behavior tests in `backend/tests/unit/submission_analysis/test_git_ownership.py` (FR-019-FR-020, QG-15)
- [ ] T069 [P] [US2] Lane B — Add vector, lexical, exact-symbol and weighting tests in `backend/tests/unit/submission_analysis/test_hybrid_retriever.py` (FR-019, SC-002)
- [ ] T070 [P] [US2] Lane B — Add strategy schema, fixed-criterion and source-provenance tests in `backend/tests/unit/submission_analysis/test_strategy_generation.py` (FR-021, QG-09)
- [ ] T071 [P] [US2] Lane B — Add partial/failure/retry/DLQ state tests in `backend/tests/integration/submission_analysis/test_partial_analysis.py` (FR-022, FR-050)
- [ ] T072 [P] [US2] Lane B — Add submission/readiness UI tests in `apps/applicant-interview/src/features/submissions/__tests__/submissionJourney.test.tsx` (FR-016, FR-022)

### Implementation for User Story 2

- [ ] T073 [US2] Lane B — Create submission, Git analysis, chunk and strategy tables in `backend/alembic/versions/submission/b_001_submission_analysis.py` (FR-016-FR-022)
- [ ] T074 [P] [US2] Lane B — Implement Submission and SubmissionAnalysis state models in `backend/src/interview_evidence/submission_analysis/domain/submission.py` (FR-016-FR-018, FR-022)
- [ ] T075 [P] [US2] Lane B — Implement SubmissionChunk and source locator models in `backend/src/interview_evidence/submission_analysis/domain/source.py` (FR-017, FR-030)
- [ ] T076 [P] [US2] Lane B — Implement GitRepositoryAnalysis, GitCommitAnalysis and CandidateCodeUnit in `backend/src/interview_evidence/submission_analysis/domain/git_analysis.py` (FR-019-FR-020)
- [ ] T077 [P] [US2] Lane B — Implement InterviewStrategy and fixed-criterion invariants in `backend/src/interview_evidence/submission_analysis/domain/strategy.py` (FR-021)
- [ ] T078 [US2] Lane B — Implement tenant-mandatory submission repositories in `backend/src/interview_evidence/submission_analysis/repositories/postgres.py` (FR-005)
- [ ] T079 [P] [US2] Lane B — Implement scoped original/derived object storage adapter in `backend/src/interview_evidence/submission_analysis/adapters/object_storage.py` (FR-017, FR-047)
- [ ] T080 [P] [US2] Lane B — Implement file, URL, size, media and secret-risk validation in `backend/src/interview_evidence/submission_analysis/application/submission_validator.py` (FR-016, FR-049)
- [ ] T081 [P] [US2] Lane B — Implement document/Textract extraction adapter in `backend/src/interview_evidence/workers/analysis/document_extract.py` (FR-018)
- [ ] T082 [US2] Lane B — Implement section/page/location-aware chunking in `backend/src/interview_evidence/workers/analysis/document_chunker.py` (FR-017-FR-018)
- [ ] T083 [P] [US2] Lane B — Implement bounded, isolated public repository fetch and exclusions in `backend/src/interview_evidence/workers/analysis/git_fetch.py` (FR-019, FR-049)
- [ ] T084 [US2] Lane B — Implement per-commit diff and candidate identity matching in `backend/src/interview_evidence/workers/analysis/git_commits.py` (FR-019-FR-020)
- [ ] T085 [US2] Lane B — Implement AST symbol expansion, ownership regions and related-test discovery in `backend/src/interview_evidence/workers/analysis/code_units.py` (FR-019-FR-020, QG-15)
- [ ] T086 [P] [US2] Lane B — Implement vector and lexical search ports/adapters in `backend/src/interview_evidence/submission_analysis/adapters/search.py` (FR-019, QG-10)
- [ ] T087 [US2] Lane B — Implement tenant-first hybrid ranking and exact-symbol boosts in `backend/src/interview_evidence/submission_analysis/application/retrieval.py` (FR-019-FR-020)
- [ ] T088 [US2] Lane B — Implement structured strategy generation and validation in `backend/src/interview_evidence/submission_analysis/application/strategy_service.py` (FR-021)
- [ ] T089 [US2] Lane B — Implement idempotent analysis job handlers and outbox status events in `backend/src/interview_evidence/workers/analysis/handlers.py` (FR-022, FR-032, FR-050)
- [ ] T090 [US2] Lane B — Implement upload, submission and readiness route fragments with protected-resource audit events in `backend/src/interview_evidence/submission_analysis/api/applicant_routes.py` (FR-016-FR-022, FR-048)
- [ ] T091 [P] [US2] Lane B — Implement Korean applicant upload, public repository and partial-status UI in `apps/applicant-interview/src/features/submissions/index.tsx` (FR-001, FR-016, FR-022)
- [ ] T092 [P] [US2] Lane B — Implement owned object/search/analysis deletion targets in `backend/src/interview_evidence/submission_analysis/application/deletion_targets.py` (FR-047, QG-06)
- [ ] T093 [US2] Lane B — Complete the isolated Lane B journey in `backend/tests/integration/submission_analysis/test_lane_b_quickstart.py` (US2, QG-09-QG-10, QG-15)

**Checkpoint**: Lane B creates a strategy against A fixtures, with reproducible SourceReferences and
no cross-tenant search results.

---

## Phase 5: User Story 3 — Recoverable Live Interview (Lane C, Priority P1)

**Goal**: A prepared applicant completes an idempotent, server-authoritative interview that recovers
from connection and dependency failures.

**Independent Test**: Run `make test-lane-c demo-lane-c` with a frozen Strategy fixture and
deterministic speech/search/model fakes.

### Tests for User Story 3

- [ ] T094 [P] [US3] Lane C — Add WebSocket message/envelope compatibility tests in `backend/tests/contract/interview_engine/test_websocket_contract.py` (FR-032-FR-035)
- [ ] T095 [P] [US3] Lane C — Add allowed and rejected session transition tests in `backend/tests/unit/interview_engine/test_session_state_machine.py` (FR-033)
- [ ] T096 [P] [US3] Lane C — Add duplicate answer, upload and job idempotency tests in `backend/tests/integration/interview_engine/test_idempotency.py` (FR-026, FR-032, QG-08)
- [ ] T097 [P] [US3] Lane C — Add Aurora/outbox/DynamoDB reconciliation and fallback tests in `backend/tests/integration/interview_engine/test_context_reconciliation.py` (FR-034)
- [ ] T098 [P] [US3] Lane C — Add reconnect, stale sequence and no-duplicate-Turn tests in `backend/tests/integration/interview_engine/test_session_recovery.py` (FR-034, SC-008, QG-08)
- [ ] T099 [P] [US3] Lane C — Add search, model, speech and upload failure-mode tests in `backend/tests/integration/interview_engine/test_degraded_modes.py` (FR-035, FR-050)
- [ ] T100 [P] [US3] Lane C — Add media chunk sequence, digest and resume tests in `backend/tests/unit/interview_engine/test_recording_chunks.py` (FR-031-FR-034)
- [ ] T101 [P] [US3] Lane C — Add forbidden/duplicate/multi-question/fixed-axis policy tests in `backend/tests/unit/interview_engine/test_question_policy.py` (FR-024-FR-025, FR-029, QG-07)
- [ ] T102 [P] [US3] Lane C — Add partial-versus-final speech result tests in `backend/tests/unit/interview_engine/test_transcription.py` (FR-026, FR-031)
- [ ] T103 [P] [US3] Lane C — Add applicant session-store recovery tests in `apps/applicant-interview/src/features/interview/__tests__/sessionStore.test.ts` (FR-033-FR-035)
- [ ] T104 [P] [US3] Lane C — Add browser device, answer completion, reconnect and text-only tests in `apps/applicant-interview/src/features/interview/__tests__/interviewJourney.spec.ts` (FR-023-FR-036)

### Implementation for User Story 3

- [ ] T105 [US3] Lane C — Create session, Turn, checkpoint and recording-chunk tables in `backend/alembic/versions/interview/c_001_interview_session.py` (FR-031-FR-034)
- [ ] T106 [P] [US3] Lane C — Implement InterviewSession and state invariants in `backend/src/interview_evidence/interview_engine/domain/session.py` (FR-033)
- [ ] T107 [P] [US3] Lane C — Implement Turn, checkpoint and media-chunk invariants in `backend/src/interview_evidence/interview_engine/domain/turn.py` (FR-026, FR-031-FR-034)
- [ ] T108 [US3] Lane C — Implement tenant-mandatory session repositories in `backend/src/interview_evidence/interview_engine/repositories/postgres.py` (FR-005)
- [ ] T109 [US3] Lane C — Implement compare-and-transition session state machine in `backend/src/interview_evidence/interview_engine/application/state_machine.py` (FR-033)
- [ ] T110 [P] [US3] Lane C — Implement scoped command and upload idempotency store in `backend/src/interview_evidence/interview_engine/application/idempotency.py` (FR-032)
- [ ] T111 [US3] Lane C — Implement durable checkpoints and recovery snapshots in `backend/src/interview_evidence/interview_engine/application/checkpoints.py` (FR-034)
- [ ] T112 [P] [US3] Lane C — Implement DynamoDB recent-context hot-view adapter in `backend/src/interview_evidence/interview_engine/adapters/recent_context.py` (FR-028, FR-034)
- [ ] T113 [US3] Lane C — Implement outbox-based hot-view reconciliation and Aurora fallback in `backend/src/interview_evidence/interview_engine/application/context_reconciliation.py` (FR-034)
- [ ] T114 [P] [US3] Lane C — Implement streaming speech recognition adapter and confidence handling in `backend/src/interview_evidence/interview_engine/adapters/transcribe.py` (FR-026, FR-031)
- [ ] T115 [US3] Lane C — Implement token-budgeted ContextBuilder with summaries and remaining criteria in `backend/src/interview_evidence/interview_engine/application/context_builder.py` (FR-028)
- [ ] T116 [P] [US3] Lane C — Implement Lane B retrieval consumer with no-result fallback in `backend/src/interview_evidence/interview_engine/adapters/retrieval_client.py` (FR-028, FR-030, FR-035)
- [ ] T117 [US3] Lane C — Implement structured next-question generation in `backend/src/interview_evidence/interview_engine/application/question_generator.py` (FR-024-FR-025, FR-028)
- [ ] T118 [US3] Lane C — Implement deterministic question policy and secondary safety checks in `backend/src/interview_evidence/interview_engine/application/question_policy.py` (FR-029, QG-07)
- [ ] T119 [P] [US3] Lane C — Implement speech synthesis, viseme and text-only fallback adapter in `backend/src/interview_evidence/interview_engine/adapters/polly.py` (FR-025, FR-035)
- [ ] T120 [P] [US3] Lane C — Implement recording chunk upload authorization and verification in `backend/src/interview_evidence/interview_engine/application/recording_service.py` (FR-031-FR-034)
- [ ] T121 [US3] Lane C — Implement answer-finalize-to-next-question orchestration in `backend/src/interview_evidence/interview_engine/application/interview_service.py` (FR-024-FR-036)
- [ ] T122 [US3] Lane C — Implement the protocol stream endpoint in `backend/src/interview_evidence/interview_engine/api/websocket.py` (FR-025-FR-035)
- [ ] T123 [US3] Lane C — Implement equipment, session, resume and media-intent routes with protected-resource audit events in `backend/src/interview_evidence/interview_engine/api/applicant_routes.py` (FR-023, FR-031-FR-035, FR-048)
- [ ] T124 [P] [US3] Lane C — Implement device and network readiness UI in `apps/applicant-interview/src/features/interview/EquipmentCheck.tsx` (FR-023)
- [ ] T125 [P] [US3] Lane C — Implement chunked recorder, audio worklet and local retry buffer in `apps/applicant-interview/src/features/interview/media.ts` (FR-026-FR-027, FR-031)
- [ ] T126 [US3] Lane C — Implement server-sequence Zustand store and resume reconciliation in `apps/applicant-interview/src/features/interview/sessionStore.ts` (FR-032-FR-035)
- [ ] T127 [US3] Lane C — Implement Korean AI disclosure, question, answer, processing, pause and completion room UI in `apps/applicant-interview/src/features/interview/InterviewRoom.tsx` (FR-001-FR-002, FR-024-FR-036)
- [ ] T128 [P] [US3] Lane C — Implement 2D avatar speech-mark synchronization and text-only mode in `apps/applicant-interview/src/features/interview/Avatar.tsx` (FR-025, FR-035)
- [ ] T129 [P] [US3] Lane C — Implement owned Turn/checkpoint/hot-view/media-chunk deletion targets in `backend/src/interview_evidence/interview_engine/application/deletion_targets.py` (FR-047, QG-06)
- [ ] T130 [US3] Lane C — Complete the isolated reconnect/degraded Lane C journey in `backend/tests/integration/interview_engine/test_lane_c_quickstart.py` (US3, SC-007-SC-008, QG-08)

**Checkpoint**: Lane C completes one interview against fakes, survives reconnect and produces no
duplicate Turn or assessment signal from technical failures.

---

## Phase 6: User Story 4 — Evidence Review and Human Decision (Lane D, Priority P1)

**Goal**: A company reviews transcript/video-linked Evidence, preserves AI and human versions, records
a human-only decision, and verifies privacy deletion.

**Independent Test**: Run `make test-lane-d demo-lane-d` with a completed-session fixture.

### Tests for User Story 4

- [ ] T131 [P] [US4] Lane D — Add report, timeline, review, final-decision and deletion HTTP contract tests in `backend/tests/contract/reporting/test_http_contract.py` (FR-037-FR-048)
- [ ] T132 [P] [US4] Lane D — Add confirmed/partial Evidence constraints and invalid-range tests in `backend/tests/unit/reporting/test_evidence_integrity.py` (FR-039-FR-041, SC-016, QG-02)
- [ ] T133 [P] [US4] Lane D — Add SourceReference-versus-Evidence separation tests in `backend/tests/unit/reporting/test_source_evidence_separation.py` (FR-040-FR-041)
- [ ] T134 [P] [US4] Lane D — Add transcript, media manifest, missing-range and session-clock tests in `backend/tests/integration/reporting/test_timeline_alignment.py` (FR-037-FR-038)
- [ ] T135 [P] [US4] Lane D — Add immutable AI original and append-only human override tests in `backend/tests/unit/reporting/test_human_review.py` (FR-043-FR-044)
- [ ] T136 [P] [US4] Lane D — Add AI/system-role final-decision denial tests in `backend/tests/integration/reporting/test_human_only_decision.py` (FR-003, FR-045, SC-011, QG-03)
- [ ] T137 [P] [US4] Lane D — Add deletion enumeration, retry and residue-verification tests in `backend/tests/integration/reporting/test_deletion_manifest.py` (FR-046-FR-047, SC-015, QG-05-QG-06)
- [ ] T138 [P] [US4] Lane D — Add cross-tenant report, Evidence, media locator and deletion denial tests in `backend/tests/integration/reporting/test_tenant_isolation.py` (FR-005, SC-014, QG-04)
- [ ] T139 [P] [US4] Lane D — Add report/timeline/human-review component tests in `apps/company-console/src/features/review/__tests__/reviewJourney.test.tsx` (FR-037-FR-045)
- [ ] T140 [P] [US4] Lane D — Add Evidence-to-video start-within-two-seconds browser test in `apps/company-console/src/features/review/__tests__/evidenceSeek.spec.ts` (FR-038, SC-012)

### Implementation for User Story 4

- [ ] T141 [US4] Lane D — Create transcript, media, report, Evidence, review and deletion tables in `backend/alembic/versions/reporting/d_001_reporting.py` (FR-037-FR-048)
- [ ] T142 [P] [US4] Lane D — Implement TranscriptSegment, RecordingAsset and SessionEvent models in `backend/src/interview_evidence/reporting/domain/timeline.py` (FR-037-FR-038)
- [ ] T143 [P] [US4] Lane D — Implement Report, ReportItem and Evidence invariants in `backend/src/interview_evidence/reporting/domain/report.py` (FR-039-FR-042)
- [ ] T144 [P] [US4] Lane D — Implement HumanReview and human-only final decision model in `backend/src/interview_evidence/reporting/domain/review.py` (FR-043-FR-045)
- [ ] T145 [P] [US4] Lane D — Implement DeletionRequest, Manifest and Target state model in `backend/src/interview_evidence/reporting/domain/deletion.py` (FR-046-FR-047)
- [ ] T146 [US4] Lane D — Implement tenant-mandatory reporting repositories in `backend/src/interview_evidence/reporting/repositories/postgres.py` (FR-005)
- [ ] T147 [US4] Lane D — Implement final-Turn transcript ingestion and correction history in `backend/src/interview_evidence/reporting/application/transcript_service.py` (FR-037)
- [ ] T148 [US4] Lane D — Implement recording validation, media post-processing and manifest generation in `backend/src/interview_evidence/workers/reporting/media.py` (FR-037-FR-038)
- [ ] T149 [US4] Lane D — Implement structured report generation and state assignment in `backend/src/interview_evidence/workers/reporting/report.py` (FR-039-FR-042)
- [ ] T150 [US4] Lane D — Implement transactional Evidence validation and rejection in `backend/src/interview_evidence/reporting/application/evidence_service.py` (FR-039-FR-041, QG-02)
- [ ] T151 [US4] Lane D — Implement append-only human assessment, note, bookmark and final-decision services in `backend/src/interview_evidence/reporting/application/review_service.py` (FR-043-FR-045)
- [ ] T152 [US4] Lane D — Implement transcript keyword and criterion timeline projection in `backend/src/interview_evidence/reporting/application/timeline_service.py` (FR-037-FR-038)
- [ ] T153 [P] [US4] Lane D — Implement scoped short-lived playback locator adapter in `backend/src/interview_evidence/reporting/adapters/playback.py` (FR-038, FR-049)
- [ ] T154 [US4] Lane D — Consume retention-expired events and implement cross-lane deletion orchestration in `backend/src/interview_evidence/reporting/application/deletion_service.py` (FR-046-FR-047, QG-05-QG-06)
- [ ] T155 [US4] Lane D — Implement report, timeline, review and privacy route fragments with protected-resource audit events in `backend/src/interview_evidence/reporting/api/company_routes.py` (FR-037-FR-048)
- [ ] T156 [P] [US4] Lane D — Implement Korean report list/detail and criterion state UI in `apps/company-console/src/features/review/ReportView.tsx` (FR-001, FR-039-FR-045)
- [ ] T157 [P] [US4] Lane D — Implement synchronized transcript, video, search, bookmark and Evidence seek UI in `apps/company-console/src/features/review/TimelineView.tsx` (FR-037-FR-038, SC-012)
- [ ] T158 [P] [US4] Lane D — Implement review history, final decision and deletion status UI in `apps/company-console/src/features/review/HumanReview.tsx` (FR-043-FR-047)
- [ ] T159 [US4] Lane D — Complete the isolated Evidence/review/deletion Lane D journey in `backend/tests/integration/reporting/test_lane_d_quickstart.py` (US4, QG-02-QG-07)

**Checkpoint**: Lane D rejects unsupported assessments, preserves AI originals, accepts only human
decisions and cannot complete deletion while any target remains.

---

## Phase 7: Integration, AWS Parity and Cross-Cutting Gates

**Purpose**: Merge in A→B→C→D order, replace fakes one boundary at a time, and satisfy all release gates.

### Infrastructure and Deployment (Lane A Owns `infra/`)

- [ ] T160 [P] Lane A — Implement reusable VPC, subnet, endpoint and security-group resources in `infra/modules/network/main.tf` (QG-14, QG-16)
- [ ] T161 [P] Lane A — Implement private S3 origins, CloudFront OAC, WAF, DNS and certificate resources in `infra/modules/edge/main.tf` (QG-14)
- [ ] T162 [P] Lane A — Implement ECR, ALB, ECS API/worker services and autoscaling ownership rules in `infra/modules/compute/main.tf` (PD-05, QG-13)
- [ ] T163 [P] Lane A — Implement Aurora, DynamoDB, S3, KMS and Secrets Manager resources in `infra/modules/data/main.tf` (PD-21, PD-23, QG-14)
- [ ] T164 [P] Lane A — Implement SQS/DLQ, Step Functions and EventBridge resources in `infra/modules/async-workflow/main.tf` (FR-050)
- [ ] T165 [P] Lane A — Implement OpenSearch Serverless, index mapping, Bedrock Knowledge Base and guardrail resources in `infra/modules/ai-search/main.tf` (PD-06, PD-22, QG-15)
- [ ] T166 [P] Lane A — Implement Cognito and SES resources with least-privilege roles in `infra/modules/identity/main.tf` (PD-13, PD-24)
- [ ] T167 [P] Lane A — Implement CloudWatch, X-Ray, alarms, budgets and audit resources in `infra/modules/observability/main.tf` (FR-051)
- [ ] T168 Lane A — Compose separated dev roots and S3 lockfile backends in `infra/environments/dev/foundation/main.tf`, `infra/environments/dev/data-ai/main.tf`, and `infra/environments/dev/application/main.tf` (PD-26, QG-16)
- [ ] T169 [P] Lane A — Add stage and prod roots with independent state, roles, KMS and data stores in `infra/environments/stage/main.tf` and `infra/environments/prod/main.tf` (QG-16)
- [ ] T170 Integration — Add saved-plan, approval, migration, ECS and frontend deployment stages in `.github/workflows/deploy.yml` (QG-13-QG-16)

### Merge Train and Real Adapters (Integration Owner)

- [ ] T171 Integration — Merge lane Alembic heads and prove empty/previous-snapshot upgrade in `backend/alembic/versions/merge/m_001_lane_merge.py` (QG-16)
- [ ] T172 Integration — Replace Lane A campaign/consent fakes for Lane B and add real boundary tests in `backend/tests/integration/cross_module/test_a_to_b.py`
- [ ] T173 Integration — Replace Lane B strategy/retrieval fakes for Lane C and add real boundary tests in `backend/tests/integration/cross_module/test_b_to_c.py`
- [ ] T174 Integration — Replace Lane C Turn/media fakes for Lane D and add real boundary tests in `backend/tests/integration/cross_module/test_c_to_d.py`
- [ ] T175 Integration — Connect Lane D report/deletion projections to Lane A company views in `backend/tests/integration/cross_module/test_d_to_a.py`
- [ ] T176 Integration — Wire all router fragments and worker handlers in `backend/src/interview_evidence/main.py`
- [ ] T177 Integration — Wire all feature routes without changing lane feature internals in `apps/company-console/src/app/featureRoutes.ts` and `apps/applicant-interview/src/app/featureRoutes.ts`
- [ ] T178 Integration — Complete local production-contract composition and health checks in `compose.yaml` (QG-11)

### Full Quality Gates

- [ ] T179 [P] Integration — Add the company-to-human-decision thin journey in `tests/e2e/test_thin_journey.py` (FR-001-FR-052, QG-01)
- [ ] T180 [P] Integration — Add cross-route, worker, search, object and hot-view tenant isolation suite in `tests/e2e/test_tenant_isolation.py` (SC-014, QG-04, QG-10)
- [ ] T181 [P] Integration — Add full-store deletion residue and retry suite in `tests/e2e/test_deletion_residue.py` (SC-015, QG-05-QG-06)
- [ ] T182 [P] Integration — Add no-AI-final-decision and no-nonverbal-scoring static/runtime suite in `tests/e2e/test_human_control.py` (SC-011, QG-03, QG-07)
- [ ] T183 [P] Lane B — Add fixed Korean document/code retrieval corpus and expected sources in `tests/regression/retrieval/cases.jsonl` (SC-002, QG-09-QG-10, QG-15)
- [ ] T184 [P] Lane C — Add fixed safe-question, duplicate, forbidden and degraded-mode corpus in `tests/regression/questions/cases.jsonl` (FR-029, QG-12)
- [ ] T185 [P] Lane D — Add Evidence-state and unsupported-claim regression corpus in `tests/regression/evidence/cases.jsonl` (SC-004-SC-005, SC-016, QG-02, QG-12)
- [ ] T186 Integration — Add configuration-version regression runner and thresholds in `tests/regression/run_regression.py` (FR-051-FR-052, QG-12)
- [ ] T187 [P] Lane C — Add five-concurrent-session and long-running pipeline load scenarios in `tests/load/interview_load.py` (SC-007, SC-013)
- [ ] T188 [P] Lane D — Add Evidence seek performance measurement in `tests/load/evidence_seek.py` (SC-012)
- [ ] T189 Integration — Add stage CloudFront-to-AWS-service smoke journey in `tests/e2e/test_stage_smoke.py` (QG-13-QG-14)
- [ ] T190 Integration — Run and record every command/outcome from `specs/001-interview-evidence-platform/quickstart.md`
- [ ] T191 Integration — Record FR/SC/QG-to-test coverage and zero unresolved critical gaps in `specs/001-interview-evidence-platform/validation-report.md`
- [ ] T192 Integration — Run `$speckit-converge` and append every remaining spec/plan/code gap to `specs/001-interview-evidence-platform/tasks.md`

**Final Checkpoint**: QG-01 through QG-16 pass, contract generation is clean, all migrations have one
merged head, all four lane suites and the thin end-to-end journey pass, and no critical convergence
gap remains.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**: starts immediately; Integration Owner coordinates root files.
- **Phase 2 Foundation**: depends on Setup and blocks all user-story implementation.
- **Phases 3-6**: start simultaneously from the same `foundation-v1` commit:
  - Phase 3 / US1 = Lane A
  - Phase 4 / US2 = Lane B
  - Phase 5 / US3 = Lane C
  - Phase 6 / US4 = Lane D
- **Phase 7 Integration**: lane work may be reviewed while others continue, but the merge train
  follows A → B → C → D.

### User Story Dependencies

- **US1 / Lane A**: no runtime dependency on other stories; uses report/analysis/interview projections as fakes.
- **US2 / Lane B**: consumes frozen campaign/criterion/consent contracts; can finish against fixtures.
- **US3 / Lane C**: consumes frozen strategy/retrieval contracts; can finish against fixtures.
- **US4 / Lane D**: consumes frozen Turn/media/source contracts; can finish against fixtures.
- Real producer replacement occurs only in T172-T175, after each producing lane merges.

### Within Each Lane

1. Complete and observe failing contract/domain tests.
2. Add the lane-prefixed migration and domain models.
3. Implement repositories and adapters behind frozen ports.
4. Implement application services and policy rules.
5. Implement route/event fragments and owned UI.
6. Run the lane quickstart against fakes.
7. Update from the integration branch and run the same tests against real merged producers.

## Parallel Opportunities

- T002-T012 are independent setup files after T001 defines root conventions.
- T016-T017 and T020-T025 are independent foundation artifacts before composition tasks.
- After T035, all tasks in Phases 3, 4, 5 and 6 run as four parallel workstreams.
- Within a lane, test files marked [P] can be authored in parallel before implementation.
- Domain model files marked [P] are exclusive and can be implemented after their tests exist.
- T160-T167 Terraform modules are independent; only T168 composes them.
- T179-T185 are independent cross-cutting test/data artifacts before the final report.

## Four-Person Invocation

After the start gate is reviewed, each person opens their worktree and gives Codex one bounded task:

```text
Person 1 / Lane A:
$speckit-implement Implement only unchecked tasks whose description starts "Lane A —" in
specs/001-interview-evidence-platform/tasks.md. Do not edit integration-owned or other-lane paths.

Person 2 / Lane B:
$speckit-implement Implement only unchecked tasks whose description starts "Lane B —" in
specs/001-interview-evidence-platform/tasks.md. Use frozen fakes for unmerged producers.

Person 3 / Lane C:
$speckit-implement Implement only unchecked tasks whose description starts "Lane C —" in
specs/001-interview-evidence-platform/tasks.md. Use frozen fakes for unmerged producers.

Person 4 / Lane D:
$speckit-implement Implement only unchecked tasks whose description starts "Lane D —" in
specs/001-interview-evidence-platform/tasks.md. Use frozen fakes for unmerged producers.
```

The Integration Owner handles only tasks whose description starts `Integration —`; this role does
not authorize edits to a lane's exclusive implementation path.

## Parallel Example

```text
After foundation-v1:
  Worktree A -> T036-T063
  Worktree B -> T064-T093
  Worktree C -> T094-T130
  Worktree D -> T131-T159

Review can happen in any order.
Merge and real-adapter replacement happen A -> B -> C -> D using T171-T178.
```

## Implementation Strategy

### Thin Slice First

Each lane first implements the smallest path needed by its independent test:

- Lane A: criterion version → campaign → invitation → consent.
- Lane B: submitted fixtures → source retrieval → strategy.
- Lane C: start → answer → next question → reconnect → complete.
- Lane D: completed fixture → Evidence report → human decision → deletion.

Only after all four thin slices pass should a lane add breadth such as CSV scale, deeper Git context,
additional degraded modes or richer review UI.

### Merge Discipline

- One task or tightly coupled test/implementation pair per commit.
- Every PR lists lane, foundation hash, task IDs, FR/SC/QG IDs, contracts and migration head.
- No lane PR edits `tasks.md`, generated output, a shared root or another lane path.
- Shared contract changes merge separately before consumer implementation.
- A completed task checkbox is updated on the integration branch after its commit is accepted.
- Final completion requires the merged quickstart and convergence pass, not four isolated green lanes.
