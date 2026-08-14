# Phase 0 Research: Interview Evidence Platform

**Date**: 2026-08-14

**Status**: Complete — no unresolved clarifications

This document converts the fixed decisions in the source planning document and constitution into
implementation choices. It does not reopen product decisions PD-01 through PD-26.

## R-001 — Monorepo with a Modular Monolith

**Decision**: Keep both SPAs, the FastAPI application, workers, generated contracts, tests and
Terraform in one repository. Deploy the four backend domains as one API image while enforcing
source-level boundaries.

**Rationale**: The pilot needs consistent contracts and a simple operational unit more than
independent service scaling. One repository allows atomic contract generation and end-to-end tests,
while domain directories let four contributors work without touching the same files.

**Alternatives considered**:

- Four microservices: rejected because distributed transactions, deployment coordination and
  operational overhead are premature for five concurrent interviews.
- One unstructured application package: rejected because it provides no enforceable ownership or
  dependency boundary for parallel contributors.

## R-002 — Four Domain Ownership Lanes

**Decision**: Use Lane A (platform/company), Lane B (submission/RAG), Lane C (live interview), and
Lane D (Evidence/review). Assign exclusive source and migration paths to each lane.

**Rationale**: These boundaries match business capabilities and the source document's four backend
modules. They also minimize shared UI and backend files.

**Alternatives considered**:

- Split by frontend/backend/infrastructure/QA: rejected because each feature would require
  cross-person handoffs and shared-file edits throughout development.
- Split by screens: rejected because domain rules, data and async workers would have unclear owners.

## R-003 — Foundation Freeze Before Parallel Branching

**Decision**: Merge one foundation commit containing repository layout, canonical contracts,
generated types, fakes, migration configuration, CI and shared primitives before creating four lane
worktrees.

**Rationale**: Parallel development is predictable only when identifiers, schemas, error formats,
event envelopes and test seams are stable.

**Alternatives considered**:

- Let every lane define contracts independently: rejected due to semantic drift and late merge
  conflicts.
- Freeze contracts only at final integration: rejected because tests and adapters would target
  incompatible assumptions.

## R-004 — Contract Fragments with Generated Types

**Decision**: Store canonical HTTP, WebSocket and async schemas in `packages/contracts`. Keep the
composition roots integration-owned and lane-specific path/schema fragments lane-owned. Generate
Python and TypeScript types and fail CI on generated drift.

**Rationale**: Fragments keep ownership disjoint; generated types catch incompatibility before
runtime; a single root prevents duplicate route or schema names.

**Alternatives considered**:

- Hand-written types in each application: rejected because they can silently diverge.
- One large contract file edited by everyone: rejected because it becomes a merge-conflict hotspot.

## R-005 — Durable Domain Events with Outbox Reconciliation

**Decision**: Persist cross-module domain events in the same Aurora transaction as durable state,
then relay them through the standard async envelope. Consumers record idempotency before side effects.

**Rationale**: Aurora and DynamoDB, queues, search and object storage cannot share a transaction.
An outbox makes incomplete delivery observable and retryable without duplicating Turns or jobs.

**Alternatives considered**:

- Direct best-effort publish after commit: rejected because a process crash can lose the event.
- Distributed transactions: rejected because the selected AWS services do not share a practical
  transaction coordinator.

## R-006 — Aurora as Evidence Authority, Specialized Derived Stores

**Decision**: Use Aurora for identities, versions, state, Turns, transcript anchors, SourceReference,
Evidence, human review, audit and deletion state. Use DynamoDB as a rebuildable hot context view, S3
for immutable large objects, and OpenSearch/Knowledge Bases for rebuildable retrieval.

**Rationale**: Evidence and version history need relational constraints, while real-time context,
media and retrieval have different access and size characteristics.

**Alternatives considered**:

- Store everything in PostgreSQL: rejected because large media and vector/hot-context access do not
  fit the same operational model.
- Treat search or DynamoDB as the Evidence source: rejected because derived indexes and TTL views
  cannot guarantee the required relationship history.

## R-007 — Alembic Branch Labels Per Lane

**Decision**: Configure four Alembic version locations and branch labels. Each lane maintains one
head using a lane-prefixed revision ID; the integration owner creates merge revisions.

**Rationale**: A single migration directory would cause revision-name and head conflicts even when
domain tables are disjoint.

**Alternatives considered**:

- Central migration owner for every domain change: rejected because it serializes otherwise
  independent work.
- Separate databases per module: rejected because it adds service-level complexity and weakens
  Evidence relations in the pilot.

## R-008 — Server-Authoritative Interview State

**Decision**: Treat the browser as a media and interaction client. The server owns state, sequence,
idempotency and checkpoints; reconnect uses a server snapshot and the last acknowledged sequence.

**Rationale**: Browser local state can be stale after network loss or task replacement. Server
authority is required to prevent duplicate Turns and preserve Evidence order.

**Alternatives considered**:

- Restore only from browser storage: rejected because it is not trustworthy or complete.
- Keep session state only in API memory: rejected because Fargate task replacement would lose it.

## R-009 — Explicit Answer Completion

**Decision**: Finalize an answer only on the applicant's `answer.complete` command. Partial speech
results are display-only. Technical recovery is a separate state and never a voluntary re-record.

**Rationale**: This is a fixed product decision that removes ambiguity from silence detection and
keeps the interview comparable.

**Alternatives considered**:

- Automatic end-of-speech: rejected as the sole authority because pauses and Korean speech patterns
  can prematurely close an answer.
- Unlimited re-recording: rejected because it changes the intended interview conditions.

## R-010 — Application Policy Before Model Safety

**Decision**: Validate model output with typed schemas and deterministic application rules for
forbidden topics, one-question-only, duplicate detection, fixed criteria and Evidence. Use managed
model safety controls as a secondary layer.

**Rationale**: Product rules must be testable and stable across model changes. A probabilistic safety
layer cannot be the only enforcement mechanism.

**Alternatives considered**:

- Prompt-only enforcement: rejected because output can still violate constraints.
- Managed guardrail only: rejected because it does not encode all product-specific invariants.

## R-011 — Hybrid Retrieval for Candidate Code

**Decision**: Index per-commit changes and expanded code units. Combine semantic similarity,
lexical relevance, exact symbol/path matches and tenant/applicant filters. Persist the retrieval
result used by each question.

**Rationale**: Code questions need both semantic intent and exact identifiers. Commit metadata
identifies candidate contribution but must not become the interview subject itself.

**Alternatives considered**:

- Embed the whole repository: rejected because it loses contribution scope and precise provenance.
- Vector-only retrieval: rejected because exact symbol and path matches are important for code.
- Ask about commit messages or hashes: rejected because memorization does not test implementation
  understanding.

## R-012 — Two SPAs with Feature-Level Ownership

**Decision**: Build separate company and applicant SPAs. Keep app shells integration-owned and split
feature directories among lanes.

**Rationale**: Authentication, risk and user journeys differ. Feature-level directories avoid a
frontend owner becoming a bottleneck while preserving separate deployables.

**Alternatives considered**:

- One SPA with role switching: rejected because applicant access and company authentication have
  different trust boundaries.
- Separate repositories: rejected because generated contracts and coordinated end-to-end tests
  would be harder to keep atomic.

## R-013 — Direct, Chunked Media Upload

**Decision**: Upload browser media chunks directly to scoped, short-lived object upload locations.
Send speech-optimized audio through the session channel, and reconcile media sequence against the
server checkpoint.

**Rationale**: Routing full media through the API wastes compute and makes API availability a larger
recording risk. Chunking preserves completed sections during interruption.

**Alternatives considered**:

- Upload one file at interview end: rejected because a disconnect can lose the whole recording.
- Proxy every media byte through the API: rejected due to unnecessary bandwidth and memory pressure.

## R-014 — Local Contract Parity with Deterministic Fakes

**Decision**: Use Docker Compose for PostgreSQL, object/queue emulation, DynamoDB emulation and local
search. External AI clients expose interfaces with recorded deterministic fakes; a development
profile can call real approved AWS services for integration validation.

**Rationale**: Four contributors need fast, repeatable local tests without credentials, while the
source plan requires real AWS AI integration before release.

**Alternatives considered**:

- Require a live AWS account for all tests: rejected because it is slow, costly and non-deterministic.
- Use fakes only: rejected because service permissions, streaming and model behavior need staging
  validation.

## R-015 — Terraform and Application Deployment Have Separate Owners

**Decision**: Terraform owns infrastructure target state. The application pipeline owns image
digests, service revisions, database migrations, prompts/settings and business indexing.

**Rationale**: Mixed ownership creates perpetual drift and makes infrastructure plans capable of
re-running business mutations.

**Alternatives considered**:

- Run builds, migrations and indexing from Terraform provisioners: rejected because those operations
  are not declarative infrastructure.
- Let both Terraform and the deployment pipeline update the same task definition field: rejected
  because each would undo the other.

## R-016 — Quality Gates as Merge Evidence

**Decision**: Represent QG-01 through QG-16 in contract, integration, security, regression,
infrastructure or end-to-end tests. Each task declares the requirement and gate IDs it satisfies.

**Rationale**: Narrative quality goals do not protect parallel merges unless every lane produces
machine-readable or reviewer-verifiable evidence.

**Alternatives considered**:

- Run only unit tests per lane: rejected because most risks are cross-boundary.
- Defer all end-to-end testing to the end: rejected because incompatible lanes would be discovered
  too late.

## Resolved Unknowns

No `NEEDS CLARIFICATION` item remains. Parameters intentionally left configurable by the source
plan—chunk size, retrieval weights, recent-turn budget, timeouts, media chunk duration and AWS
capacity—will be versioned settings selected through regression and load tests rather than hardcoded
product requirements.
