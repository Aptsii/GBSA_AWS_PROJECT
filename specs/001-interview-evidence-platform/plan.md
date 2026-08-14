# Implementation Plan: Interview Evidence Platform

**Branch**: `001-interview-evidence-platform` | **Date**: 2026-08-14 |
**Spec**: [spec.md](./spec.md)

**Input**: Feature specification from
`/specs/001-interview-evidence-platform/spec.md` and source planning document v1.4.

## Summary

Build a Korean-language, AWS-native structured interview SaaS that turns company criteria,
applicant materials, a recoverable live interview, and human review into a traceable Evidence
chain. The implementation is a monorepo containing two React SPAs, one FastAPI modular monolith,
asynchronous workers, and Terraform-managed AWS infrastructure.

Development is contract-first and split into four exclusive ownership lanes. A small foundation
wave freezes shared schemas, repository structure, test fixtures, and CI before the four lane
branches start from the same commit. Each lane can then implement against published contracts and
deterministic fakes without editing another lane's owned paths.

## Technical Context

**Language/Version**: Python 3.12+; TypeScript 5+; Terraform 1.10+

**Primary Dependencies**: FastAPI, Pydantic, SQLAlchemy 2, Alembic, boto3; React 18+,
Vite, React Router, TanStack Query, Zustand; AWS Provider and OpenSearch Provider

**Storage**: Aurora PostgreSQL Serverless v2 for durable relational truth and Evidence;
DynamoDB for hot conversation context; S3 for documents, code snapshots and media;
OpenSearch Serverless and Bedrock Knowledge Bases for vector, lexical and hybrid retrieval

**Testing**: pytest, pytest-asyncio and contract/integration fixtures; Vitest, React Testing
Library and Playwright; Terraform validate/test, TFLint and security scanning; fixed AI and
retrieval regression datasets

**Target Platform**: Modern desktop browsers; Linux containers on ECS Fargate; AWS
`ap-northeast-2` by default, with cross-region model use requiring separate privacy approval

**Project Type**: Web SaaS monorepo with two SPAs, one modular-monolith API, workers and
infrastructure code

**Performance Goals**: Evidence-linked video starts within 2 seconds; interview pipeline starts
immediately after answer completion and records stage p50/p95; stable operation for five companies
and five concurrent interviews

**Constraints**: Korean-only pilot; public repositories only; answer completion is explicit;
no voluntary re-recording; AI cannot decide hiring; consent and tenant isolation are mandatory;
source material is not assessment Evidence; local flows preserve production contracts

**Scale/Scope**: 1-5 pilot companies, 1-5 simultaneous interviews, hundreds of retained
interviews; scale beyond 100 concurrent interviews is deferred

## Constitution Check

*GATE: Passed before Phase 0 research and re-checked after Phase 1 design.*

| Principle | Plan Evidence | Status |
|---|---|---|
| Evidence before scores and human control | Evidence foreign keys, report state constraints, separate SourceReference and human-only decision endpoint | PASS |
| Tenant isolation and privacy | Mandatory tenant context in every repository/event/search contract; deletion manifest spans all stores | PASS |
| Contract-first modular ownership | Four exclusive path lanes, contract freeze gate, fragment ownership and no private cross-imports | PASS |
| Test-first traceability and quality gates | Contract tests precede adapters; tasks map FR/SC/QG IDs; end-to-end quickstart is a merge gate | PASS |
| Recoverable, idempotent interview state | Versioned state machine, idempotency keys, outbox reconciliation and degraded modes | PASS |
| Fixed product and technology constraints | Required React/FastAPI/AWS/Terraform topology is preserved | PASS |
| Four-lane workflow | Foundation commit, worktree instructions, merge order and integration owner are defined | PASS |

**Post-design re-check**: PASS. Contracts, data ownership, migration ownership and validation
scenarios make every constitutional rule actionable. No exception or complexity waiver is required.

## Architecture and Boundaries

```text
Company SPA --------------------> FastAPI modular monolith <---------------- Applicant SPA
  Lane A + D                       shared shell/contracts                      Lane A+B+C
                                      |
        +-----------------------------+-----------------------------+
        |                             |                             |
 company_management            submission_analysis          interview_engine
      Lane A                         Lane B                       Lane C
        |                             |                             |
        +---------------------- versioned events -------------------+
                                      |
                                  reporting
                                    Lane D

Workers consume versioned messages and call only their owning module's public application service.
Durable cross-module transitions use an outbox. No module reads another module's tables directly.
```

### Module Rules

1. A module exposes only `api.py`, `contracts.py`, and declared domain events to other modules.
2. Routers call their own application services; they never call repositories from another module.
3. All persistence methods receive a typed `TenantContext`. Absence is a type and runtime error.
4. Cross-module references store stable UUIDs and versions; ownership remains with the source module.
5. Synchronous calls are limited to user-facing reads and commands that need an immediate answer.
   Long work and cross-store synchronization use versioned, idempotent events.
6. Shared code is limited to technical primitives: settings, tenant context, auth claims, IDs,
   event envelope, outbox, observability, error envelope and AWS client interfaces.
7. Business enums and schemas belong to their domain contract fragment, not to a general
   `shared` dumping ground.

## Four-Lane Ownership

| Lane | Domain responsibility | Exclusive implementation paths | May consume |
|---|---|---|---|
| A — Platform & Hiring | repository bootstrap, company auth, tenant context, positions, criteria, campaigns, invitations, consent shell, shared AWS and Terraform foundation | `apps/company-console/src/features/company/`, `apps/company-console/src/features/hiring/`, `apps/applicant-interview/src/features/access/`, `backend/src/interview_evidence/company_management/`, `backend/alembic/versions/company/`, `infra/` | Published submission, interview and report status contracts |
| B — Submission & RAG | upload workflow, document/Git analysis, chunking, hybrid retrieval, strategy generation, analysis workers | `apps/applicant-interview/src/features/submissions/`, `backend/src/interview_evidence/submission_analysis/`, `backend/src/interview_evidence/workers/analysis/`, `backend/alembic/versions/submission/` | Campaign/criterion and consent contracts |
| C — Live Interview | applicant room shell, device/media, session state, STT-search-LLM-TTS orchestration, checkpoints and recovery | `apps/applicant-interview/src/features/interview/`, `backend/src/interview_evidence/interview_engine/`, `backend/src/interview_evidence/workers/interview/`, `backend/alembic/versions/interview/` | Strategy and criterion contracts |
| D — Evidence & Review | transcript/timeline, media post-processing, reports, Evidence, human review, retention/deletion orchestration | `apps/company-console/src/features/review/`, `backend/src/interview_evidence/reporting/`, `backend/src/interview_evidence/workers/reporting/`, `backend/alembic/versions/reporting/` | Completed-session, source and criterion contracts |

### Integration-Owned Paths

The integration owner is the only writer to the following paths after the foundation commit:

- root workspace and tool configuration: `package.json`, lockfiles, `pyproject.toml`,
  `compose.yaml`, `Makefile`
- application shells and route registries:
  `apps/*/src/app/`, `backend/src/interview_evidence/main.py`
- technical shared primitives: `backend/src/interview_evidence/shared/`
- contract roots and generated outputs: `packages/contracts/`
- cross-lane fixtures and full journey tests: `tests/e2e/`, `tests/fixtures/shared/`
- migration configuration and merge heads: `backend/alembic.ini`,
  `backend/alembic/env.py`, `backend/alembic/versions/merge/`
- CI definitions and root documentation

Lane contributors propose a contract change as a small patch or issue; the integration owner applies
it after affected-lane review. Domain-owned contract fragments remain editable only by their lane.

## Project Structure

### Documentation (this feature)

```text
specs/001-interview-evidence-platform/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── parallel-workstreams.md
├── contracts/
│  ├── openapi.yaml
│  ├── websocket.md
│  ├── async-events.md
│  └── module-boundaries.md
├── checklists/
│  ├── requirements.md
│  └── parallel-readiness.md
└── tasks.md
```

### Source Code (repository root)

```text
apps/
├── company-console/
│  ├── src/
│  │  ├── app/                       # integration-owned shell
│  │  └── features/
│  │     ├── company/                # Lane A
│  │     ├── hiring/                 # Lane A
│  │     └── review/                 # Lane D
│  └── tests/
└── applicant-interview/
   ├── src/
   │  ├── app/                       # integration-owned shell
   │  └── features/
   │     ├── access/                 # Lane A
   │     ├── submissions/            # Lane B
   │     └── interview/              # Lane C
   └── tests/

packages/
├── contracts/
│  ├── openapi/
│  │  ├── root.yaml                  # integration-owned
│  │  └── paths/{company,submission,interview,reporting}/
│  ├── events/{common,submission,interview,reporting}/
│  └── generated/{python,typescript}/
└── test-fixtures/

backend/
├── src/interview_evidence/
│  ├── main.py                       # integration-owned composition root
│  ├── company_management/           # Lane A
│  ├── submission_analysis/          # Lane B
│  ├── interview_engine/             # Lane C
│  ├── reporting/                    # Lane D
│  ├── workers/
│  │  ├── analysis/                  # Lane B
│  │  ├── interview/                 # Lane C
│  │  └── reporting/                 # Lane D
│  └── shared/                       # integration-owned technical primitives
├── alembic/
│  └── versions/{company,submission,interview,reporting,merge}/
└── tests/{unit,contract,integration}/

infra/
├── bootstrap/{state-backend,pipeline-role}/
├── modules/{network,edge,compute,data,async-workflow,ai-search,identity,observability}/
└── environments/{dev,stage,prod}/{foundation,data-ai,application}/

tests/
├── e2e/
├── fixtures/shared/
├── regression/{questions,retrieval,evidence}/
└── load/
```

**Structure Decision**: Use a monorepo so generated contracts, shared fixtures and a single
integration pipeline remain atomic while domain implementation stays in exclusive subtrees. This
matches the deployment as one modular-monolith API without turning source ownership into separate
services.

## Contract and Schema Freeze

The foundation commit MUST contain:

1. stable UUID conventions and `TenantContext`;
2. the HTTP error envelope and pagination contract;
3. REST route names and request/response schema names from `contracts/openapi.yaml`;
4. the WebSocket envelope, sequence and idempotency rules from `contracts/websocket.md`;
5. the asynchronous event envelope, topic names and versioning rules from
   `contracts/async-events.md`;
6. entity ownership, foreign-key direction and state enums from `data-model.md`;
7. generated Python and TypeScript contract packages;
8. deterministic fakes for every cross-lane dependency;
9. CI checks for formatting, generated-contract drift, forbidden imports and migration heads.

After the freeze, additive optional fields are backward compatible. New required fields, changed
semantics, removed values, or renamed routes/events require a version bump, affected-lane approval,
updated fakes, and a separate integration-owned contract commit before lane implementation continues.

## Migration Strategy

- Alembic uses four version locations with branch labels `company`, `submission`,
  `interview`, and `reporting`.
- Revision IDs begin with `a_`, `b_`, `c_`, or `d_` according to lane. A lane writes only
  its directory and keeps one head in that branch.
- Cross-lane foreign keys are declared in `data-model.md`; the referencing lane owns creation and
  deletion behavior but cannot alter the referenced table.
- The integration owner creates merge revisions under `versions/merge/` after lane merges.
- CI rejects multiple unmerged heads in one lane, missing downgrade paths, destructive changes
  without a data migration note, and schema drift from ORM metadata.

## Delivery Waves and Merge Order

### Wave 0 — Shared Foundation

One short integration branch establishes the monorepo, contracts, generated types, fakes, test
harness, migration layout and CI. All four contributors review and branch from the tagged
`foundation-v1` commit.

### Wave 1 — Four Parallel Thin Slices

- Lane A: company → criterion version → campaign → invitation → consent authorization.
- Lane B: submitted fixture → analysis status → searchable source → interview strategy.
- Lane C: seeded strategy → start → one answer → next question → reconnect → complete.
- Lane D: completed-session fixture → transcript → Evidence report → human review → deletion manifest.

Each slice uses cross-lane fakes and passes its own contract, tenant, failure and observability tests.

### Wave 2 — Contract Integration

Merge order is A, B, C, D because later lanes consume earlier domain identifiers, but disjoint
ownership makes code conflicts unlikely. After each merge:

1. generate contracts and verify no drift;
2. run all prior lane tests;
3. merge Alembic heads;
4. replace exactly one fake with the real producer;
5. run the affected cross-module integration scenario.

### Wave 3 — Hardening

The four lanes continue in parallel on failure modes, privacy deletion, retrieval quality,
observability, accessibility and load. The integration branch then runs the complete quickstart,
QG-01 through QG-16, and a `$speckit-converge` reconciliation before release.

## Testing Strategy

- **Unit**: domain state machines, policy checks, ranking, Evidence rules and retention calculations.
- **Contract**: every HTTP, WebSocket and async schema in both Python and TypeScript; consumers test
  against producer fakes before real integration.
- **Integration**: repository adapters, tenant filters, outbox reconciliation, object ranges,
  retrieval scope and deletion across stores.
- **AI regression**: fixed Korean and Korean/English-code datasets; structured-output validation;
  low relevance, prompt injection and unsupported claim cases.
- **Browser**: company campaign, applicant upload/device flow, reconnect, Evidence seek and human edit.
- **Infrastructure**: static validation, policy/security scan, plan review and environment smoke tests.
- **End-to-end**: the thin journey in `quickstart.md` is mandatory after every lane merge.

Tests that define a new contract or invariant are committed before or with production code and must
be observed failing against the previous implementation.

## Operational Design

- JSON logs and traces use opaque IDs; no applicant name, source text, answer text, secret or signed
  URL is emitted.
- Metrics include per-stage latency, WebSocket connections, queue age, DLQ count, DB reconciliation
  lag, retrieval fallback, report Evidence rejection and deletion residue.
- Workers carry `company_id`, target ID, job type/version, idempotency key and trace ID only.
- Production stores are encrypted and private. Access uses short-lived roles, scoped signed URLs and
  audited application actions.
- Model, prompt, chunking, embedding and retrieval settings are versioned deployment artifacts with
  regression evidence.

## Complexity Tracking

No constitutional violation requires justification. The modular monolith, four domain lanes and
separate hot/search/object stores are directly required by real-time recovery, Evidence integrity,
large media handling and the fixed AWS decisions in the source planning document.
