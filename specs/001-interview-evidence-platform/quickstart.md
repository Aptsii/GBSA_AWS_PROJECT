# Quickstart Validation: Interview Evidence Platform

**Purpose**: Prove the thin end-to-end pilot and each lane independently.

This guide describes the commands and expected outcomes that implementation tasks must make real.
It contains no production implementation. Run from the repository root.

## Prerequisites

- Git with four-worktree support
- Docker with Compose
- Python 3.12+ and the repository's locked Python environment tool
- Node.js compatible with the committed workspace toolchain and the committed package manager
- Terraform 1.10+ for infrastructure validation
- An approved AWS development profile only for the optional live-AWS scenarios

No local unit or contract test requires permanent AWS credentials.

## 1. Bootstrap the Local Environment

```bash
make bootstrap
make compose-up
make migrate
make seed-contract-fixtures
```

Expected:

- both SPAs and the API health endpoints become ready;
- local PostgreSQL, object/queue emulation, DynamoDB emulation and search are healthy;
- four Alembic lane heads plus the current integration merge head are visible;
- the seeded companies and applicants use opaque IDs and no secret appears in console output.

## 2. Verify Contract and Ownership Gates

```bash
make contracts-generate
make contracts-check
make boundaries-check
make migration-check
```

Expected:

- generated Python and TypeScript contracts match canonical schemas;
- every route and event has exactly one owner lane;
- no backend module imports another module's private domain, model or repository path;
- every lane has at most one unmerged migration head;
- the working tree remains clean after generation.

## 3. Run the Foundation Test Set

```bash
make test-foundation
```

Expected:

- missing or wrong `TenantContext` is rejected;
- company and applicant authentication cannot cross invitation or tenant scope;
- error envelopes contain a safe request ID and no protected text;
- outbox duplicate delivery is idempotent;
- shared fakes conform to the same contracts as producers.

## 4. Validate Each Lane Independently

Each lane uses contract fakes for dependencies that have not merged.

### Lane A — Platform and Hiring

```bash
make test-lane-a
make demo-lane-a
```

Expected journey:

1. authenticate a company fixture;
2. create a position and criterion version;
3. publish the criterion version and campaign;
4. create an invitation and exchange its one-time token;
5. verify identity and record consent;
6. demonstrate that a second company cannot read any created object.

### Lane B — Submission and RAG

```bash
make test-lane-b
make demo-lane-b
```

Expected journey:

1. use a contract fixture for an authorized, consented invitation;
2. register a Korean PDF and a public test repository;
3. show per-source ready/partial/failed status;
4. retrieve a document chunk and an exact code symbol only inside applicant scope;
5. create a strategy linked to the fixed criterion version and source locations;
6. show that low ownership confidence produces a verification question, not a claim.

### Lane C — Live Interview

```bash
make test-lane-c
make demo-lane-c
```

Expected journey:

1. use a contract fixture for a ready strategy;
2. start a server-authoritative session;
3. present one question, stream an answer and finalize it;
4. repeat `answer.complete` with the same idempotency key and observe one Turn;
5. generate one safe next question;
6. disconnect, resume from the checkpoint and complete without duplicate Turns;
7. force retrieval and speech failures and observe safe fallback states.

### Lane D — Evidence and Review

```bash
make test-lane-d
make demo-lane-d
```

Expected journey:

1. use a completed-session fixture with final Turns, transcript and media ranges;
2. generate a report with confirmed, partial, insufficient and follow-up states;
3. reject a confirmed item with no valid applicant-answer Evidence;
4. seek from Evidence to the linked transcript and video range;
5. append a human override and preserve the AI original;
6. reject a final decision request without a human company principal;
7. run deletion and leave it incomplete until every store verifies absence.

## 5. Run the Merged Thin End-to-End Journey

```bash
make test-integration
make test-e2e-thin
```

Expected:

```text
company criterion
-> campaign and invitation
-> applicant token exchange, identity and consent
-> PDF/public Git submission and strategy
-> device check and interview start
-> one finalized applicant answer and one follow-up
-> reconnect and completion
-> transcript/media processing
-> report with answer Evidence
-> human review and final decision
```

At the end:

- SourceReference points to the exact submitted source used for the question;
- Evidence points only to a final applicant Turn and valid transcript/video interval;
- the criterion version is identical across campaign, strategy, session and report;
- AI has no route, role or worker path to the final decision;
- another tenant cannot retrieve any object, search result, hot-view item or signed media locator.

## 6. Run Failure, Privacy and Regression Gates

```bash
make test-recovery
make test-tenant-isolation
make test-deletion-residue
make test-ai-regression
make test-load-pilot
```

Expected:

- duplicate commands/jobs create no duplicate durable state;
- interrupted sessions resume from the last final Turn;
- every cross-tenant request and search returns no protected data;
- deletion verifies absence across relational, hot-view, object and search stores;
- forbidden, duplicate, multi-part and unsupported questions are blocked;
- fixed Korean and Korean/English-code fixtures preserve retrieval and Evidence thresholds;
- five concurrent interview journeys do not starve the real-time path.

## 7. Validate Infrastructure Without Applying

```bash
make infra-format-check
make infra-validate
make infra-security-check
make infra-plan-dev
```

Expected:

- environment and state keys are separated;
- no public S3 data bucket or public database is planned;
- state encryption, native lockfile use, IAM boundaries and deletion protection are present;
- Terraform does not run builds, database migrations, indexing or business workflows;
- image revisions and auto-scaled desired count do not cause Terraform ownership drift.

An apply is never part of local quickstart. Stage/prod apply requires the reviewed saved plan and
human approval defined by the deployment process.

## 8. Four-Branch Integration Drill

Follow [parallel-workstreams.md](./parallel-workstreams.md), then run after each lane merge:

```bash
make contracts-check
make migration-check
make test-prior-lanes
make test-e2e-thin
```

Expected:

- no manual edit to generated contracts;
- no unresolved same-lane or cross-lane migration head;
- all previously merged lane tests remain green;
- exactly one cross-lane fake is replaced at each planned integration step;
- final merged behavior matches the same contracts used by all lane branches.

## 9. Final Spec Convergence

After implementation and all gates:

```text
$speckit-converge
```

Any difference among spec, plan, tasks and implementation becomes a new task. Do not close a gap by
silently changing behavior or weakening the constitution.

## Requirement and Quality-Gate Evidence

The final validation report MUST include:

- executed commit hash and environment;
- task, FR, SC and QG IDs;
- contract and migration versions;
- pass/fail result with artifact location;
- retry, degraded-mode and deletion residue observations;
- reviewer identity for human-only release gates.
