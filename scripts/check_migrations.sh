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

"${python_cmd[@]}" "${repo_root}/scripts/check_migration_policy.py" --config "${config_path}"

migration_metadata="$(${python_cmd[@]} - "${config_path}" <<'PY'
import sys

from alembic.config import Config
from alembic.script import ScriptDirectory

script = ScriptDirectory.from_config(Config(sys.argv[1]))
head = script.get_current_head()
revision = script.get_revision(head)
print(head)
print(" ".join(revision._normalized_down_revisions))
PY
)"
final_head="$(sed -n '1p' <<<"${migration_metadata}")"
parent_heads="$(sed -n '2p' <<<"${migration_metadata}")"

temporary_root="$(mktemp -d "${TMPDIR:-/tmp}/iep-migrations.XXXXXX")"
trap 'rm -rf "${temporary_root}"' EXIT
export DATABASE_URL="sqlite:///${temporary_root}/empty-upgrade.db"

"${alembic_cmd[@]}" -c "${config_path}" upgrade head >/dev/null
upgraded_head="$("${alembic_cmd[@]}" -c "${config_path}" current)"
if ! grep -Eq "^${final_head} .*\(head\)" <<<"${upgraded_head}"; then
  echo "Empty-database upgrade did not reach migration head: ${final_head}" >&2
  exit 1
fi

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

export DATABASE_URL="sqlite:///${temporary_root}/previous-snapshot.db"
for revision in ${parent_heads}; do
  "${alembic_cmd[@]}" -c "${config_path}" upgrade "${revision}" >/dev/null
done
snapshot_heads="$("${alembic_cmd[@]}" -c "${config_path}" current)"
for revision in ${parent_heads}; do
  if ! grep -Eq "^${revision}( |$)" <<<"${snapshot_heads}"; then
    echo "Previous integration snapshot did not reach lane head: ${revision}" >&2
    exit 1
  fi
done

"${alembic_cmd[@]}" -c "${config_path}" upgrade head >/dev/null
merged_snapshot_head="$("${alembic_cmd[@]}" -c "${config_path}" current)"
if ! grep -Eq "^${final_head} .*\(head\)" <<<"${merged_snapshot_head}"; then
  echo "Previous integration snapshot did not upgrade to merge head: ${final_head}" >&2
  exit 1
fi

echo "Migration head ${final_head}, lane prefixes, labels, empty upgrade, previous snapshot upgrade, downgrade, and ORM drift check passed."
