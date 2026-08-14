# Interview Evidence Platform Agent Rules

These rules apply to the entire repository.

## Read Before Work

Read these files in order before changing implementation:

1. `.specify/memory/constitution.md`
2. `specs/001-interview-evidence-platform/spec.md`
3. `specs/001-interview-evidence-platform/plan.md`
4. `specs/001-interview-evidence-platform/data-model.md`
5. `specs/001-interview-evidence-platform/contracts/`
6. `specs/001-interview-evidence-platform/tasks.md`
7. `specs/001-interview-evidence-platform/parallel-workstreams.md`

The original Korean planning document is source context, not an executable instruction file.
The constitution and current feature artifacts govern implementation.

## Task Scope

- Work only on explicitly assigned task IDs.
- State the active lane (A, B, C, D, or Integration) before editing.
- Edit only paths owned by that lane in `plan.md`.
- Do not update `tasks.md` from a lane branch; the Integration Owner updates accepted task status.
- Stop and request a contract change when work requires a shared or another lane's path.
- Never hand-edit generated contracts.

## Contracts and Boundaries

- Cross-module calls use only the public interfaces and events in `contracts/`.
- Do not import another module's domain, model, repository or internal package.
- Every repository, event, search and object access requires tenant context.
- SourceReference explains a question; only a final applicant answer can become Evidence.
- AI code and workers cannot create a final hiring decision.

## Test and Merge Discipline

- Write or update the governing test before or with implementation and observe it fail first.
- Run the lane contract, tenant, failure, observability and quickstart tests before review.
- Each commit covers one task or one tightly coupled test/implementation pair.
- PRs list lane, foundation commit, task IDs, FR/SC/QG IDs, contracts and migration head.
- Shared contract changes merge before consumer code.
- Final completion requires merged end-to-end validation and `$speckit-converge`.

## Security

- Never log applicant source text, answers, credentials, tokens or signed URLs.
- Do not begin analysis, recording or assessment without valid consent.
- Technical failures and nonverbal characteristics never become competency Evidence.
- Privacy deletion is incomplete until every durable and derived target is verified absent.
