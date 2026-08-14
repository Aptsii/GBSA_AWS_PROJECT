# Four-Person Parallel Workstreams

**Purpose**: Give four contributors a conflict-minimized execution and merge protocol.

**Canonical task source**: [tasks.md](./tasks.md)

**Contract source**: [contracts/](./contracts/)

## Roles

| Person | Lane | Primary deliverable | Branch |
|---|---|---|---|
| Person 1 | A — Platform & Hiring | tenant-safe company, campaign, invitation and infrastructure foundation | `feature/001-lane-a-platform` |
| Person 2 | B — Submission & RAG | traceable document/code analysis and interview strategy | `feature/001-lane-b-analysis` |
| Person 3 | C — Live Interview | recoverable real-time interview and applicant room | `feature/001-lane-c-interview` |
| Person 4 | D — Evidence & Review | timeline, Evidence report, human review and deletion | `feature/001-lane-d-reporting` |

Person 1 acts as the initial integration owner for Wave 0 only. After `foundation-v1`, integration
ownership may rotate, but exactly one person owns shared paths in a wave.

## Start Gate

No lane starts implementation until all four contributors confirm:

- [ ] Constitution v1.0.0 reviewed
- [ ] `spec.md`, `plan.md`, `data-model.md` and all contracts reviewed
- [ ] Wave 0 CI passes
- [ ] generated Python and TypeScript contracts have no drift
- [ ] deterministic fakes exist for every cross-lane dependency
- [ ] one Alembic head exists for each lane branch
- [ ] `foundation-v1` commit hash is recorded in all four lane PRs

## Worktree Setup

Run this only after the foundation commit has been merged to `main` and tagged
`foundation-v1`:

```bash
# Run only when an origin remote exists:
git fetch origin
git worktree add ../iep-lane-a -b feature/001-lane-a-platform foundation-v1
git worktree add ../iep-lane-b -b feature/001-lane-b-analysis foundation-v1
git worktree add ../iep-lane-c -b feature/001-lane-c-interview foundation-v1
git worktree add ../iep-lane-d -b feature/001-lane-d-reporting foundation-v1
```

Each contributor works only in their worktree and only on task IDs assigned to their lane.

## Task Claiming

1. Select the next unblocked task with your lane marker in `tasks.md`.
2. Record the task ID in the branch or pull-request description; do not edit `tasks.md` from a
   lane branch.
3. Make the test or contract assertion fail before implementation when the task changes a domain
   rule.
4. Keep commits limited to one task or a tightly coupled test/implementation pair.
5. If an owned task requires a shared-path change, stop and submit a contract-change request to the
   integration owner instead of editing the shared path.

## Contract Change Protocol

A contract change request contains:

- affected contract and current version;
- additive, semantic or breaking classification;
- originating FR, SC and task IDs;
- affected lanes and required consumer changes;
- updated producer/consumer examples;
- migration and rollout compatibility;
- proposed fake and contract-test changes.

The integration owner merges the contract change first. All affected lanes update from that commit
before implementation resumes. Breaking changes require a new route/event/schema version; they do
not overwrite an active version.

## Pull Request Template

Every lane PR description includes:

```text
Lane:
Foundation commit:
Task IDs:
Requirement IDs:
Quality gates:
Owned paths changed:
Contract versions consumed:
Contract changes:
Migration revision/head:
Failure and recovery scenarios:
Observability added:
Local validation:
Known follow-up:
```

A lane PR with an unlisted shared-path edit, another lane's path, or generated contract drift is not
mergeable.

## Merge Train

1. Freeze lane branches briefly and update them from the current integration branch.
2. Merge Lane A; run foundation, tenant and invitation/consent tests.
3. Merge Lane B; replace campaign/consent fakes and run submission-to-strategy integration.
4. Merge Lane C; replace strategy fake and run start-to-completion plus reconnect integration.
5. Merge Lane D; replace completed-session fake and run report-to-Evidence-to-human-decision flow.
6. Create an Alembic merge revision and verify upgrade from an empty database and the previous
   integration snapshot.
7. Run the complete quickstart, isolation suite, deletion residue suite and contract drift check.
8. Run `$speckit-converge`; remaining gaps become new tasks, never undocumented patches.

The order controls semantic dependency, not authorship. Because paths are exclusive, a later lane can
finish and review before an earlier lane; it waits only in the merge train.

## Conflict Resolution

- **Same implementation file**: ownership table decides; the non-owner moves its code behind the
  owner's public contract.
- **Same contract fragment**: the fragment owner proposes; the integration owner composes.
- **Same database object**: the entity owner edits it; the consumer adds only its referencing
  relation or requests a source-domain change.
- **Different assumptions**: constitution, spec, data model and contract win in that order. If still
  ambiguous, stop the affected tasks and amend the design artifact before coding.
- **Generated file conflict**: discard manual generated edits and regenerate from the merged
  canonical contracts.

## Lane Completion Checklist

Each lane is complete only when:

- all assigned task tests pass;
- owned contract fragments conform to the frozen roots;
- no forbidden cross-module import exists;
- tenant and applicant scope tests pass;
- retry/idempotency and degraded paths are covered;
- logs contain no prohibited content;
- migration upgrade and downgrade are demonstrated;
- the lane's quickstart slice passes against fakes and then real merged producers;
- the PR documents all FR, SC and QG coverage.
