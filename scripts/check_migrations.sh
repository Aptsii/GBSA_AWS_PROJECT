#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
config_path="${FOUNDATION_ALEMBIC_CONFIG:-${repo_root}/backend/alembic.ini}"
backend_root="$(cd "$(dirname "${config_path}")" && pwd)"

if [[ -x "${repo_root}/.venv/bin/alembic" ]]; then
  alembic_cmd=("${repo_root}/.venv/bin/alembic")
  python_cmd=("${repo_root}/.venv/bin/python")
else
  alembic_cmd=(uv run alembic)
  python_cmd=(uv run python)
fi

expected_heads=(
  "a_:company"
  "b_:submission"
  "c_:interview"
  "d_:reporting"
)

"${python_cmd[@]}" "${repo_root}/scripts/check_migration_policy.py" --config "${config_path}"

actual_heads="$("${alembic_cmd[@]}" -c "${config_path}" heads)"
head_revisions=()

for expected in "${expected_heads[@]}"; do
  prefix="${expected%%:*}"
  branch="${expected##*:}"
  matching_heads="$(grep -E "^[[:alnum:]_]+ \(${branch}\) \(head\)$" <<<"${actual_heads}" || true)"
  matching_count="$(grep -c . <<<"${matching_heads}" || true)"
  if [[ "${matching_count}" -ne 1 ]]; then
    echo "Expected exactly one migration head for ${branch}, found ${matching_count}." >&2
    exit 1
  fi
  revision="${matching_heads%% *}"
  if [[ "${revision}" != "${prefix}"* ]]; then
    echo "Migration head ${revision} has the wrong prefix for ${branch}." >&2
    exit 1
  fi
  head_revisions+=("${revision}")
done

head_count="$(grep -Ec '\(head\)$' <<<"${actual_heads}")"
if [[ "${head_count}" -ne 4 ]]; then
  echo "Expected exactly four migration heads, found ${head_count}." >&2
  exit 1
fi

temporary_root="$(mktemp -d "${TMPDIR:-/tmp}/iep-migrations.XXXXXX")"
trap 'rm -rf "${temporary_root}"' EXIT
export DATABASE_URL="sqlite:///${temporary_root}/migration-check.db"

"${alembic_cmd[@]}" -c "${config_path}" upgrade heads >/dev/null
upgraded_heads="$("${alembic_cmd[@]}" -c "${config_path}" current)"
for revision in "${head_revisions[@]}"; do
  if ! grep -Eq "^${revision} .*\(head\)$" <<<"${upgraded_heads}"; then
    echo "Upgrade did not reach migration head: ${revision}" >&2
    exit 1
  fi
done

"${alembic_cmd[@]}" -c "${config_path}" check >/dev/null
"${alembic_cmd[@]}" -c "${config_path}" downgrade base >/dev/null
if [[ -n "$("${alembic_cmd[@]}" -c "${config_path}" current)" ]]; then
  echo "Downgrade did not return every lane to base." >&2
  exit 1
fi

remaining_schema_objects="$(${python_cmd[@]} -c '
import os
from sqlalchemy import create_engine, inspect

inspector = inspect(create_engine(os.environ["DATABASE_URL"]))
objects = sorted(
    [name for name in inspector.get_table_names() if name != "alembic_version"]
    + inspector.get_view_names()
)
print(",".join(objects))
')"
if [[ -n "${remaining_schema_objects}" ]]; then
  echo "Database schema objects remain after downgrade: ${remaining_schema_objects}" >&2
  exit 1
fi

echo "Migration heads (${head_revisions[*]}), prefixes, labels, downgrade, and ORM drift check passed."
