# Interview Evidence Platform

A Korean-language structured interview platform for IT and software roles. It combines fixed
company criteria, applicant-submission analysis, a recoverable live interview, and answer-linked
Evidence for human review. AI supports interviewing and assessment, but cannot make a final hiring
decision.

## Repository layout and ownership

| Path                                                                            | Responsibility                                | Owner       |
| ------------------------------------------------------------------------------- | --------------------------------------------- | ----------- |
| `apps/company-console/src/features/company/` and `hiring/`                      | Company, criteria, campaigns, and invitations | Lane A      |
| `apps/applicant-interview/src/features/access/`                                 | Applicant access and consent                  | Lane A      |
| `apps/applicant-interview/src/features/submissions/`                            | Submission analysis and retrieval UI          | Lane B      |
| `apps/applicant-interview/src/features/interview/`                              | Live interview and recovery UI                | Lane C      |
| `apps/company-console/src/features/review/`                                     | Evidence review and human decision UI         | Lane D      |
| `backend/src/interview_evidence/company_management/`                            | Company and hiring domain                     | Lane A      |
| `backend/src/interview_evidence/submission_analysis/` and `workers/analysis/`   | Submission and analysis domain                | Lane B      |
| `backend/src/interview_evidence/interview_engine/` and `workers/interview/`     | Live interview domain                         | Lane C      |
| `backend/src/interview_evidence/reporting/` and `workers/reporting/`            | Reporting and deletion domain                 | Lane D      |
| root configuration, app shells, `shared/`, contract roots, CI, and shared tests | Composition and cross-lane gates              | Integration |
| `infra/`                                                                        | AWS infrastructure                            | Lane A      |

Cross-module calls use only published contracts and events. Every repository, search, object, and
worker operation carries tenant context. A submitted source can explain a question, while only a
final applicant answer can become assessment Evidence.

## Prerequisites

- Python 3.12+
- Node.js 22.12+ and pnpm 11.21.0
- Docker with Compose
- Terraform 1.10+
- `uv` 0.10.9 or a compatible locked-environment release

No permanent AWS credentials are required for local unit or contract tests. Copy `.env.example` to
`.env` only for local development, supply the blank `IEP_` secret and identity values outside
source control, and never place secrets in committed files.

## Local setup

```bash
make bootstrap
make compose-up
```

The Compose stack supplies PostgreSQL, S3/SQS emulation, DynamoDB, and OpenSearch. The API
composition root and both image targets are present. The worker entrypoint deliberately fails
closed until T176 registers the lane handlers, so it cannot appear healthy while doing no work.

Common checks:

```bash
make format-check
make lint
make typecheck
make test
make artifacts-check
```

Contract generation is exposed through `make generate`; `make artifacts-check` regenerates the
canonical fragments in memory and rejects missing, extra, or byte-drifted generated artifacts.
Every command named in the quickstart is reserved in the Makefile. Commands owned by later lane or
integration tasks fail with a clear message until their implementation lands.

Build the two backend image targets with:

```bash
make image-api
make image-worker
```

Stop local dependencies with `make compose-down`. The complete lane and merged validation journeys
are documented in
[`specs/001-interview-evidence-platform/quickstart.md`](specs/001-interview-evidence-platform/quickstart.md).

## Working agreement

Read `AGENTS.md` and the feature artifacts before changing implementation. Work only on assigned
task IDs and owned paths. Do not hand-edit generated contracts, weaken consent or tenant gates, log
protected applicant content, or allow automated final hiring decisions.
