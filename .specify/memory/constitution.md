<!--
Sync Impact Report
- Version change: template (unversioned) -> 1.0.0
- Added principles:
  - I. Evidence Before Scores and Human Final Control
  - II. Tenant Isolation and Privacy by Construction
  - III. Contract-First Modular Ownership
  - IV. Test-First Traceability and Quality Gates
  - V. Recoverable, Idempotent Interview State
- Added sections:
  - Fixed Product and Technology Constraints
  - Four-Lane Development and Integration Workflow
- Removed sections: none
- Deferred TODOs: none
-->
# Interview Evidence Platform Constitution

## Core Principles

### I. Evidence Before Scores and Human Final Control
Every AI assessment MUST trace to an actual applicant answer, transcript interval, video
interval, criterion version, and generation version. Submitted documents and code MAY explain
why a question was asked, but MUST NOT by themselves become assessment Evidence. A report item
marked `confirmed` or `partially_confirmed` MUST contain valid Evidence; missing evidence MUST
produce `insufficient_evidence` or `needs_follow_up`. AI code, roles, and workflows MUST NOT be
able to set a final hiring decision. This preserves the product's purpose as a decision-support
system whose conclusions remain reviewable and controlled by people.

### II. Tenant Isolation and Privacy by Construction
Every database repository operation, search query, object key, asynchronous message, and worker
job MUST carry and enforce `company_id`; applicant-scoped operations MUST additionally enforce the
applicant or invitation scope. Valid consent MUST exist before document analysis, recording, or AI
assessment begins. Retention expiry and deletion requests MUST remove both originals and every
derived representation from Aurora, DynamoDB, S3, OpenSearch, summaries, and embeddings, with a
verifiable deletion manifest. Logs MUST NOT contain applicant source text, answer text, tokens,
credentials, or signed URLs. These controls are release blockers, not later hardening tasks.

### III. Contract-First Modular Ownership
The system MUST preserve four domain boundaries: `company_management`, `submission_analysis`,
`interview_engine`, and `reporting`. Cross-module interaction MUST use versioned public contracts
or events; another module's persistence tables, internals, or private types MUST NOT be imported or
called directly. Shared REST, WebSocket, event, schema, and migration contracts MUST be approved
and merged before dependent parallel implementation starts. Each implementation task MUST name one
owner lane and an exclusive file scope. Changes to shared contracts require an explicit compatibility
note, affected-lane review, and contract-test updates. This is the primary safeguard that lets four
contributors develop independently and merge predictably.

### IV. Test-First Traceability and Quality Gates
Tests for domain rules, contracts, tenant isolation, state transitions, Evidence integrity, and
failure recovery MUST be written before or with implementation and MUST demonstrate a failing state
before the production change is considered complete. Every functional requirement and buildable
success criterion MUST map to one or more task and test IDs. Contract tests, integration tests, and
the documented end-to-end quickstart MUST pass before merge. The applicable quality gates QG-01
through QG-16 from the source plan MUST remain represented in automated tests or an explicitly
assigned verification task. No lane may declare completion on unit tests alone.

### V. Recoverable, Idempotent Interview State
Interview state MUST be server-authoritative, explicitly versioned, and changed only through allowed
state transitions. Answer completion, Turn creation, checkpoint updates, media chunk processing,
worker jobs, and event consumption MUST be idempotent. Aurora is the durable Evidence authority;
DynamoDB is a recoverable hot view synchronized through an outbox or equivalent retry mechanism.
External service failures and browser reconnections MUST resume from the last confirmed checkpoint
without duplicate Turns or treating technical failure as applicant performance. Structured metrics
MUST expose stage latency, retries, reconciliation lag, and degraded-mode use.

## Fixed Product and Technology Constraints

- Product scope is Korean-language IT/development recruiting for the pilot; non-IT roles,
  multilingual interviews, private repository authentication, broad ATS/HRIS integration, and
  automatic rejection are out of scope.
- The company console and applicant interview room MUST be separate React 18+ / TypeScript / Vite
  SPAs. The backend MUST use Python 3.12+, FastAPI, Pydantic, SQLAlchemy 2, and Alembic as a modular
  monolith on ECS Fargate.
- AWS production services MUST follow the approved boundaries: Aurora PostgreSQL Serverless v2 for
  durable relational truth, DynamoDB for hot conversation context, S3 for source/media objects,
  OpenSearch Serverless and Bedrock Knowledge Bases for retrieval, and Bedrock, Transcribe, Polly,
  Textract, SQS, Step Functions, and MediaConvert for their specified roles.
- Infrastructure MUST be Terraform HCL. Environment roots and remote state MUST be separated for
  `dev`, `stage`, and `prod`; Terraform MUST NOT execute application deployments, Alembic
  migrations, applicant indexing, or business workflows.
- Local integration MUST run through Docker Compose while preserving the same domain contracts and
  invariants as AWS. External AWS clients MUST have deterministic fakes or recorded contract fixtures.
- Expression, gaze, accent, gender, age, appearance, or technical disruption MUST NOT feed competency
  scoring. Objective session events MUST remain separate from assessment inputs.

## Four-Lane Development and Integration Workflow

1. **Foundation gate**: Before lane work starts, merge repository structure, shared IDs and enums,
   OpenAPI/WebSocket/event contracts, migration ownership rules, test fixtures, and CI checks.
2. **Exclusive lanes**:
   - Lane A owns platform, company and hiring management, authentication, tenant primitives, and
     Terraform foundations.
   - Lane B owns submission ingestion, document/Git analysis, chunking, retrieval, and strategy
     generation.
   - Lane C owns applicant media, real-time interview state, STT-to-question-to-TTS flow, and session
     recovery.
   - Lane D owns transcripts, timeline, reports, Evidence, human review, retention, and deletion.
3. **No shared-file freelancing**: Files declared shared in the plan MUST change through a small,
   dedicated integration change reviewed by every affected lane. Lane branches MUST NOT edit another
   lane's owned path without an ownership transfer recorded in `tasks.md`.
4. **Branch and merge discipline**: Each lane uses a separate branch or worktree from the same
   foundation commit, keeps commits task-scoped, rebases or merges the integration branch before
   review, and merges in dependency order documented in `tasks.md`.
5. **Definition of done**: A lane is complete only when its owned tasks, tests, contract conformance,
   quickstart slice, migration review, observability, and failure-path acceptance scenarios pass.
6. **Integration gate**: After all lanes merge, the team MUST run contract tests, migration checks,
   tenant-isolation tests, cross-module integration tests, and the full thin end-to-end journey.
   `$speckit-converge` or an equivalent reconciliation pass MUST append any remaining spec-to-code
   gaps before release.

## Governance

This constitution takes precedence over feature specs, implementation plans, task lists, and local
contributor preferences. A change requires a documented proposal, impact analysis across all four
lanes, affected contract and migration notes, and approval by the project maintainer. Amendments use
semantic versioning: MAJOR for incompatible governance changes or principle removal, MINOR for a new
principle or materially expanded obligation, and PATCH for clarification without changed obligations.

Every plan MUST include a Constitution Check before research and after design. Every pull request MUST
identify requirement IDs, task IDs, owner lane, changed contracts, migrations, and quality gates.
Reviewers MUST reject unexplained constitution violations. Emergency exceptions MUST be time-bounded,
recorded with an owner and removal task, and MUST NOT bypass human final control, tenant isolation,
consent, deletion, or Evidence integrity.

**Version**: 1.0.0 | **Ratified**: 2026-08-14 | **Last Amended**: 2026-08-14
