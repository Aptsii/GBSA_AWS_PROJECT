SHELL := /bin/sh

UV ?= uv
PNPM ?= pnpm
DOCKER ?= docker
COMPOSE ?= docker compose
TERRAFORM ?= terraform

PYTHON_PATHS := backend/src backend/tests tests
CONTRACT_GENERATOR := packages/contracts/scripts/generate_contracts.py
CONTRACT_OUTPUT := packages/contracts/generated
TERRAFORM_ROOTS := \
	infra/environments/dev/foundation \
	infra/environments/dev/data-ai \
	infra/environments/dev/application \
	infra/environments/stage/foundation \
	infra/environments/stage/data-ai \
	infra/environments/stage/application \
	infra/environments/prod/foundation \
	infra/environments/prod/data-ai \
	infra/environments/prod/application
DEV_TERRAFORM_ROOTS := \
	infra/environments/dev/foundation \
	infra/environments/dev/data-ai \
	infra/environments/dev/application

.DEFAULT_GOAL := help

.PHONY: \
	help bootstrap python-install javascript-install \
	compose-up compose-down compose-logs \
	format format-check lint typecheck \
	test test-unit test-python test-javascript test-contract \
	generate contracts-generate contracts-check artifacts-check \
	boundaries-check migration-check test-foundation verify-foundation \
	image-api image-worker migrate seed-contract-fixtures \
	test-lane-a demo-lane-a test-lane-b demo-lane-b \
	test-lane-c demo-lane-c test-lane-d demo-lane-d \
	test-integration test-e2e-thin test-recovery test-tenant-isolation \
	test-e2e-browser browser-install \
	test-deletion-residue test-ai-regression test-load-pilot test-prior-lanes \
	infra-format-check infra-validate infra-security-check infra-plan-dev

define not_ready
	@printf '%s\n' 'Target $@ is reserved by the quickstart contract and is not available until its owning task is complete.' >&2
	@exit 2
endef

help:
	@printf '%s\n' \
		'bootstrap           Install locked Python and JavaScript dependencies' \
		'compose-up          Start local data and AWS-compatible services' \
		'compose-down        Stop local services' \
		'generate            Generate contract artifacts when the contract workspace exists' \
		'artifacts-check     Regenerate contracts and reject generated drift' \
		'format-check        Check Python, web, documentation, and Terraform formatting' \
		'lint                Run Python and web linters' \
		'typecheck           Run Python and TypeScript type checks' \
		'test                 Run the baseline unit and contract suites' \
		'test-foundation      Run all shared foundation checks' \
		'verify-foundation    Verify the clean pre-tag foundation gate' \
		'browser-install      Install Chromium for Compose browser E2E' \
		'test-e2e-browser     Run the Compose company-to-decision browser journey' \
		'image-api           Build the API container target' \
		'image-worker        Build the worker container target'

bootstrap: python-install javascript-install

python-install:
	$(UV) sync --frozen

javascript-install:
	$(PNPM) install --frozen-lockfile

compose-up:
	$(COMPOSE) up -d --wait

compose-down:
	$(COMPOSE) down

compose-logs:
	$(COMPOSE) logs --follow

migrate:
	cd backend && $(UV) run alembic -c alembic.ini upgrade heads

seed-contract-fixtures:
	AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test $(UV) run python scripts/seed_contract_fixtures.py

format:
	$(UV) run ruff format $(PYTHON_PATHS)
	$(UV) run ruff check --fix $(PYTHON_PATHS)
	$(PNPM) format
	$(TERRAFORM) fmt -recursive infra

format-check:
	$(UV) run ruff format --check $(PYTHON_PATHS)
	$(PNPM) format:check
	$(TERRAFORM) fmt -check -recursive infra

lint:
	$(UV) run ruff check $(PYTHON_PATHS)
	$(PNPM) lint

typecheck:
	$(UV) run mypy
	$(PNPM) typecheck

test: test-unit test-contract

test-unit: test-python test-javascript

test-python:
	$(UV) run pytest backend/tests/unit

test-javascript:
	$(PNPM) test

test-contract:
	$(UV) run pytest backend/tests/contract

generate: contracts-generate

contracts-generate:
	@if [ -f $(CONTRACT_GENERATOR) ]; then \
		$(UV) run python $(CONTRACT_GENERATOR); \
	else \
		printf '%s\n' 'Contract generation activates when the foundation contract workspace is added.'; \
	fi

contracts-check:
	@if [ -f $(CONTRACT_GENERATOR) ]; then \
		$(UV) run python $(CONTRACT_GENERATOR) --check; \
	else \
		printf '%s\n' 'Contract drift checking activates when the foundation contract workspace is added.'; \
	fi

artifacts-check: contracts-check

boundaries-check:
	$(UV) run python scripts/check_module_boundaries.py

migration-check:
	scripts/check_migrations.sh

test-foundation: test-unit test-contract artifacts-check boundaries-check migration-check

verify-foundation:
	scripts/verify_foundation.sh --pre-tag

test-lane-a:
	$(UV) run pytest backend/tests/contract/company_management backend/tests/unit/company_management backend/tests/integration/company_management
	$(PNPM) --filter @iep/company-console test -- src/features/hiring/__tests__/campaignJourney.test.tsx
	$(PNPM) --filter @iep/applicant-interview test -- src/features/access/__tests__/accessJourney.test.tsx

demo-lane-a:
	$(UV) run pytest backend/tests/integration/company_management/test_lane_a_quickstart.py -q

test-lane-b:
	$(UV) run pytest backend/tests/contract/submission_analysis backend/tests/unit/submission_analysis backend/tests/integration/submission_analysis
	$(PNPM) --filter @iep/applicant-interview test -- src/features/submissions/__tests__/submissionJourney.test.tsx

demo-lane-b:
	$(UV) run pytest backend/tests/integration/submission_analysis/test_lane_b_quickstart.py -q

test-lane-c:
	$(UV) run pytest backend/tests/contract/interview_engine backend/tests/unit/interview_engine backend/tests/integration/interview_engine
	$(PNPM) --filter @iep/applicant-interview test -- src/features/interview/__tests__

demo-lane-c:
	$(UV) run pytest backend/tests/integration/interview_engine/test_lane_c_quickstart.py -q

test-lane-d:
	$(UV) run pytest backend/tests/contract/reporting backend/tests/unit/reporting backend/tests/integration/reporting
	$(PNPM) --filter @iep/company-console test -- src/features/review/__tests__

demo-lane-d:
	$(UV) run pytest backend/tests/integration/reporting/test_lane_d_quickstart.py -q

test-integration:
	$(UV) run pytest backend/tests/integration/cross_module backend/tests/unit/test_main.py tests/e2e/test_stage_smoke.py
	$(PNPM) --filter @iep/company-console test -- src/app/featureRoutes.test.ts
	$(PNPM) --filter @iep/applicant-interview test -- src/app/featureRoutes.test.ts

test-e2e-thin:
	$(UV) run pytest tests/e2e/test_thin_journey.py

browser-install:
	$(PNPM) exec playwright install chromium

test-e2e-browser:
	$(PNPM) exec playwright test --config tests/e2e/playwright.config.ts

test-recovery:
	$(UV) run pytest \
		backend/tests/integration/interview_engine/test_session_recovery.py \
		backend/tests/integration/interview_engine/test_idempotency.py \
		backend/tests/integration/interview_engine/test_degraded_modes.py

test-tenant-isolation:
	$(UV) run pytest \
		backend/tests/integration/company_management/test_tenant_isolation.py \
		backend/tests/integration/submission_analysis/test_retrieval_isolation.py \
		backend/tests/integration/reporting/test_tenant_isolation.py \
		tests/e2e/test_tenant_isolation.py

test-deletion-residue:
	$(UV) run pytest \
		backend/tests/integration/reporting/test_deletion_manifest.py \
		tests/e2e/test_deletion_residue.py

test-ai-regression:
	$(UV) run python tests/regression/run_regression.py

test-load-pilot:
	$(UV) run python tests/load/interview_load.py
	$(UV) run python tests/load/evidence_seek.py

test-prior-lanes:
	$(MAKE) test-lane-a
	$(MAKE) test-lane-b
	$(MAKE) test-lane-c
	$(MAKE) test-lane-d

infra-format-check:
	$(TERRAFORM) fmt -check -recursive infra

infra-validate:
	@set -eu; \
	for root in $(TERRAFORM_ROOTS); do \
		printf 'Validating %s\n' "$$root"; \
		data_dir="$$(mktemp -d)"; \
		TF_DATA_DIR="$$data_dir" $(TERRAFORM) -chdir="$$root" init \
			-backend=false -input=false -lockfile=readonly >/dev/null; \
		TF_DATA_DIR="$$data_dir" $(TERRAFORM) -chdir="$$root" validate; \
		rm -rf "$$data_dir"; \
	done

infra-security-check:
	$(UV) run pytest infra/tests

infra-plan-dev: seed-contract-fixtures
	@set -eu; \
	for root in $(DEV_TERRAFORM_ROOTS); do \
		printf 'Planning %s\n' "$$root"; \
		data_dir="$$(mktemp -d)"; \
		AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_REGION=ap-northeast-2 \
			TF_DATA_DIR="$$data_dir" $(TERRAFORM) -chdir="$$root" init \
			-reconfigure -input=false -lockfile=readonly \
			-backend-config=bucket=iep-local-terraform-state \
			-backend-config=endpoint=http://localhost:4566 \
			-backend-config=skip_credentials_validation=true \
			-backend-config=skip_metadata_api_check=true \
			-backend-config=skip_region_validation=true \
			-backend-config=skip_requesting_account_id=true \
			-backend-config=force_path_style=true >/dev/null; \
		plan_argument=""; \
		case "$$root" in \
			*/foundation) plan_argument='-var=company_tenant_identity={company_id="018f2000-0000-7000-8000-000000000100",company_user_id="018f2000-0000-7000-8000-000000000101",identity_subject="local-contract-admin"}' ;; \
		esac; \
		AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_REGION=ap-northeast-2 \
			TF_DATA_DIR="$$data_dir" $(TERRAFORM) -chdir="$$root" plan \
			-input=false -lock=false -refresh=false $$plan_argument \
			-out="/tmp/iep-$$(basename "$$root").tfplan" >/dev/null; \
		rm -f "/tmp/iep-$$(basename "$$root").tfplan"; \
		rm -rf "$$data_dir"; \
	done

image-api:
	$(DOCKER) build --file backend/Containerfile --target api --tag interview-evidence-api:local .

image-worker:
	$(DOCKER) build --file backend/Containerfile --target worker --tag interview-evidence-worker:local .
