SHELL := /bin/sh

UV ?= uv
PNPM ?= pnpm
DOCKER ?= docker
COMPOSE ?= docker compose
TERRAFORM ?= terraform

PYTHON_PATHS := backend/src backend/tests tests
CONTRACT_GENERATOR := packages/contracts/scripts/generate_contracts.py
CONTRACT_OUTPUT := packages/contracts/generated

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
	$(not_ready)

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

test-lane-a demo-lane-a:
	$(not_ready)

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

test-integration test-e2e-thin test-recovery test-tenant-isolation:
	$(not_ready)

test-deletion-residue test-ai-regression test-load-pilot test-prior-lanes:
	$(not_ready)

infra-format-check:
	$(TERRAFORM) fmt -check -recursive infra

infra-validate infra-security-check infra-plan-dev:
	$(not_ready)

image-api:
	$(DOCKER) build --file backend/Containerfile --target api --tag interview-evidence-api:local .

image-worker:
	$(DOCKER) build --file backend/Containerfile --target worker --tag interview-evidence-worker:local .
