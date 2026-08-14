# Terraform Infrastructure Layout

This directory reserves the Terraform roots and reusable modules for the Interview Evidence
Platform. T009 establishes ownership and state boundaries only; Terraform resources are added by
the later Lane A infrastructure tasks.

## Approved Directory Tree

```text
infra/
├── bootstrap/
│   ├── state-backend/
│   └── pipeline-role/
├── modules/
│   ├── network/
│   ├── edge/
│   ├── compute/
│   ├── data/
│   ├── async-workflow/
│   ├── ai-search/
│   ├── identity/
│   └── observability/
└── environments/
    ├── dev/
    │   ├── foundation/
    │   ├── data-ai/
    │   └── application/
    ├── stage/
    │   ├── foundation/
    │   ├── data-ai/
    │   └── application/
    └── prod/
        ├── foundation/
        ├── data-ai/
        └── application/
```

Placeholder `.gitkeep` files preserve these roots until their owning implementation tasks add HCL.
They do not represent implemented infrastructure.

## Root Responsibilities

### Bootstrap

- `bootstrap/state-backend/` creates the dedicated S3 state bucket and its encryption key before
  application environment roots use remote state. Its own state is migrated to the remote backend
  after bootstrap.
- `bootstrap/pipeline-role/` creates the environment deployment roles used by the reviewed
  Terraform plan and apply workflow. CI/CD uses short-lived role credentials, never committed
  access keys.

### Reusable Modules

| Module           | Responsibility                                                |
| ---------------- | ------------------------------------------------------------- |
| `network`        | VPC, subnets, endpoints and security groups                   |
| `edge`           | Private S3 origins, CloudFront, WAF, DNS and certificates     |
| `compute`        | ECR, ALB, ECS services and autoscaling boundaries             |
| `data`           | Aurora, DynamoDB, S3, KMS and Secrets Manager                 |
| `async-workflow` | SQS/DLQ, Step Functions and EventBridge                       |
| `ai-search`      | OpenSearch Serverless, Bedrock Knowledge Bases and guardrails |
| `identity`       | Cognito, SES and least-privilege roles                        |
| `observability`  | CloudWatch, X-Ray, alarms, budgets and audit resources        |

Provider configuration belongs in environment roots. Modules declare only their required provider
version ranges and receive provider instances from the root.

### Environment State Roots

Each of `dev`, `stage` and `prod` is a separate environment, not a Terraform workspace alias. Every
environment is split into three independently planned and stored state roots:

- `foundation`: network, edge, identity and shared security foundations;
- `data-ai`: long-lived databases, object stores, queues, search and AI infrastructure;
- `application`: compute resources and application-facing infrastructure composition.

The separation prevents frequent application changes from being planned together with long-lived
data resources. Each root uses a distinct S3 backend key, environment deployment role, KMS boundary
and data store. Production should use a separate AWS account; at minimum it must not share those
boundaries with non-production environments.

## State and Apply Rules

- Terraform `>= 1.10` is required. S3 native state locking uses `use_lockfile = true`; new roots do
  not introduce a DynamoDB state-lock table.
- Backend credentials and sensitive backend settings come from the CI role or local approved AWS
  profile. They are never hardcoded in HCL or backend arguments committed to the repository.
- Provider lock files are committed for reproducible plans. Remote state files, variable files with
  sensitive values, saved plans and local `.terraform/` directories are never committed.
- A reviewed saved plan and explicit human approval are required before apply outside disposable
  local validation. Stage and production plans use their own roles and state.
- Long-lived state buckets, production data stores and encryption keys require deletion protection,
  backup and recovery controls. `prevent_destroy` is a secondary safeguard, not a replacement for
  plan review.
- Outputs expose only resource IDs, ARNs and endpoints. They must not expose passwords, tokens,
  applicant data or other secrets.

## Management Boundary

Terraform owns infrastructure target state. It must not run Docker builds, application deployment,
Alembic migrations, applicant analysis/indexing or other business workflows through provisioners or
`local-exec`.

The application deployment pipeline owns image digests, ECS task-definition revisions, database
migrations and versioned prompt/model/search settings. Application workers own per-applicant
analysis and search indexing. Terraform lifecycle settings must prevent those owners from
continually overwriting one another, including deployed task revisions and autoscaled desired counts.

All supported AWS resources carry the common tags `Project`, `Environment`,
`ManagedBy=Terraform`, `DataClassification` and `CostCenter`.

## Ownership

Lane A exclusively owns `infra/`. Shared configuration, deployment workflows and application code
remain outside this directory and require their assigned integration or domain owner. No HCL is
implemented as part of T009.
