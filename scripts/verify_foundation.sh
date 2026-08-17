#!/usr/bin/env bash
set -euo pipefail

readonly foundation_tag="foundation-v1"
readonly script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly repo_root="$(cd "${script_dir}/.." && pwd)"
readonly feature_dir="${repo_root}/specs/001-interview-evidence-platform"
readonly gates=(
  "dependency-locks"
  "format"
  "typecheck"
  "unit-tests"
  "contract-drift"
  "module-boundaries"
  "migration-branches"
  "container-definitions"
  "parallel-readiness"
  "task-status"
  "working-tree"
  "foundation-v1-tag"
)

usage() {
  printf 'Usage: %s --list | --pre-tag | --post-tag\n' "$0" >&2
}

fail() {
  printf 'Foundation gate failed: %s\n' "$1" >&2
  exit 1
}

run_gate() {
  local gate_name="$1"
  shift
  printf '[foundation] %s\n' "${gate_name}"
  "$@"
}

require_clean_tree() {
  local dirty_entries
  dirty_entries="$(git status --porcelain=v1 --untracked-files=all)"
  if [[ -n "${dirty_entries}" ]]; then
    printf '%s\n' "${dirty_entries}" >&2
    fail "working tree must contain no tracked or untracked changes"
  fi
}

require_review_state() {
  local unchecked_checklists
  unchecked_checklists="$(grep -RnsE '^- \[ \]' "${feature_dir}/checklists" || true)"
  if [[ -n "${unchecked_checklists}" ]]; then
    printf '%s\n' "${unchecked_checklists}" >&2
    fail "reviewer-owned checklists are incomplete"
  fi

  local unfinished_tasks
  unfinished_tasks="$(
    grep -nE '^- \[ \] T0(0[1-9]|[12][0-9]|3[0-4])([[:space:]]|$)' \
      "${feature_dir}/tasks.md" || true
  )"
  if [[ -n "${unfinished_tasks}" ]]; then
    printf '%s\n' "${unfinished_tasks}" >&2
    fail "T001-T034 must be accepted before the foundation gate"
  fi
}

require_foundation_artifacts() {
  local required_files=(
    ".editorconfig"
    ".github/workflows/ci.yml"
    "Makefile"
    "backend/Containerfile"
    "backend/alembic.ini"
    "backend/alembic/env.py"
    "backend/src/interview_evidence/main.py"
    "backend/src/interview_evidence/shared/audit.py"
    "backend/src/interview_evidence/shared/aws_clients/ports.py"
    "backend/src/interview_evidence/shared/config.py"
    "backend/src/interview_evidence/shared/errors.py"
    "backend/src/interview_evidence/shared/ids.py"
    "backend/src/interview_evidence/shared/messaging/outbox.py"
    "backend/src/interview_evidence/shared/observability.py"
    "backend/src/interview_evidence/shared/security/principals.py"
    "backend/src/interview_evidence/shared/tenant.py"
    "backend/tests/contract/test_generated_contract_drift.py"
    "packages/contracts/events/catalog.v1.json"
    "packages/contracts/events/common/v1/envelope.json"
    "packages/contracts/events/websocket/v1/catalog.json"
    "packages/contracts/generated/README.md"
    "packages/contracts/modules/v1/catalog.json"
    "packages/contracts/openapi/root.yaml"
    "packages/contracts/scripts/generate_contracts.py"
    "scripts/check_migrations.sh"
    "scripts/check_module_boundaries.py"
    "tests/fixtures/shared/factories.py"
    "apps/company-console/src/app/featureRoutes.ts"
    "apps/applicant-interview/src/app/featureRoutes.ts"
  )

  local artifact_file
  for artifact_file in "${required_files[@]}"; do
    [[ -f "${repo_root}/${artifact_file}" ]] || \
      fail "missing foundation artifact: ${artifact_file}"
  done

  [[ -d "${repo_root}/packages/contracts/generated/python" ]] || \
    fail "missing generated Python contracts"
  [[ -d "${repo_root}/packages/contracts/generated/typescript" ]] || \
    fail "missing generated TypeScript contracts"
  [[ -x "${repo_root}/scripts/check_migrations.sh" ]] || \
    fail "migration gate is not executable"
  [[ -x "${repo_root}/scripts/check_module_boundaries.py" ]] || \
    fail "boundary gate is not executable"
}

verify_tag_state() {
  local tag_verification_mode="$1"
  local candidate_commit
  candidate_commit="$(git rev-parse --verify 'HEAD^{commit}')"

  if [[ "${tag_verification_mode}" == "--pre-tag" ]]; then
    if git show-ref --verify --quiet "refs/tags/${foundation_tag}"; then
      fail "${foundation_tag} already exists; this script will not move or delete it"
    fi
    return
  fi

  local tag_ref="refs/tags/${foundation_tag}"
  git show-ref --verify --quiet "${tag_ref}" || fail "${foundation_tag} does not exist"
  [[ "$(git cat-file -t "${tag_ref}")" == "tag" ]] || \
    fail "${foundation_tag} must be an annotated or signed tag"
  [[ "$(git rev-parse --verify "${tag_ref}^{commit}")" == "${candidate_commit}" ]] || \
    fail "${foundation_tag} does not point to current HEAD"
}

if [[ $# -ne 1 ]]; then
  usage
  exit 2
fi

readonly verification_mode="$1"
case "${verification_mode}" in
  --list)
    printf '%s\n' "${gates[@]}"
    exit 0
    ;;
  --pre-tag | --post-tag)
    ;;
  *)
    usage
    exit 2
    ;;
esac

cd "${repo_root}"
git rev-parse --is-inside-work-tree >/dev/null || fail "not inside a Git repository"

for required_command in git make uv pnpm terraform docker; do
  command -v "${required_command}" >/dev/null || fail "missing required command: ${required_command}"
done

require_clean_tree
verify_tag_state "${verification_mode}"
require_review_state
require_foundation_artifacts

run_gate dependency-locks make bootstrap
run_gate format make format-check
run_gate format-lint make lint
run_gate typecheck make typecheck
run_gate contract-drift make artifacts-check
run_gate unit-tests make test
run_gate module-boundaries make boundaries-check
run_gate migration-branches make migration-check
run_gate compose-definition docker compose config --quiet
run_gate api-container docker build --check --file backend/Containerfile --target api .
run_gate worker-container docker build --check --file backend/Containerfile --target worker .

require_clean_tree
verify_tag_state "${verification_mode}"

readonly candidate_commit="$(git rev-parse --verify 'HEAD^{commit}')"
if [[ "${verification_mode}" == "--pre-tag" ]]; then
  printf 'Foundation candidate validated at %s.\n' "${candidate_commit}"
  printf 'Manual next step: git tag -a %s %s -m %q\n' \
    "${foundation_tag}" "${candidate_commit}" "Interview Evidence Platform foundation v1"
else
  printf '%s verified at %s.\n' "${foundation_tag}" "${candidate_commit}"
fi
