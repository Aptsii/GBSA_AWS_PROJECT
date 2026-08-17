#!/usr/bin/env python3
"""Fail-closed static ownership and destructive-change checks for Alembic revisions."""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.script import ScriptDirectory

LANE_PREFIXES = {
    "company": "a_",
    "submission": "b_",
    "interview": "c_",
    "reporting": "d_",
}
MERGE_LANE = "merge"
MERGE_PREFIX = "m_"
DESTRUCTIVE_SQL = re.compile(r"\b(?:DROP|TRUNCATE|DELETE\s+FROM)\b", re.IGNORECASE)


def _literal_assignment(tree: ast.Module, name: str) -> Any:
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == name for target in targets):
                value = node.value
                try:
                    return ast.literal_eval(value) if value is not None else None
                except (TypeError, ValueError):
                    return None
    return None


def _function(tree: ast.Module, name: str) -> ast.FunctionDef | None:
    return next(
        (node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name),
        None,
    )


def _string_constants(tree: ast.Module) -> dict[str, str]:
    constants: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant):
                if isinstance(node.value.value, str):
                    constants[target.id] = node.value.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                constants[node.target.id] = node.value.value
    return constants


def _string_expression(node: ast.AST, constants: dict[str, str]) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _string_expression(node.left, constants)
        right = _string_expression(node.right, constants)
        return left + right if left is not None and right is not None else None
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "text"
        and node.args
    ):
        return _string_expression(node.args[0], constants)
    return None


def _destructive_calls(upgrade: ast.FunctionDef, constants: dict[str, str]) -> list[str]:
    operations: list[str] = []
    for node in ast.walk(upgrade):
        if not isinstance(node, ast.Call):
            continue
        function_name = node.func.attr if isinstance(node.func, ast.Attribute) else None
        if function_name in {"drop_table", "drop_column", "drop_constraint"}:
            operations.append(function_name)
        elif function_name == "execute" and node.args:
            statement = _string_expression(node.args[0], constants)
            if statement is not None and DESTRUCTIVE_SQL.search(statement):
                operations.append("destructive SQL")
        elif function_name == "alter_column":
            keywords = {keyword.arg: keyword.value for keyword in node.keywords}
            if "type_" in keywords:
                operations.append("alter_column type change")
            nullable = keywords.get("nullable")
            if isinstance(nullable, ast.Constant) and nullable.value is False:
                operations.append("alter_column nullable=False")
    return operations


def validate_revision(path: Path, lane: str, prefix: str) -> list[str]:
    errors: list[str] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as error:
        return [f"{path}: cannot parse migration: {error}"]

    revision = _literal_assignment(tree, "revision")
    if not isinstance(revision, str):
        errors.append(f"{path}: revision must be a literal string")
    elif not revision.startswith(prefix):
        errors.append(f"{path}: revision {revision} has the wrong prefix for {lane}")

    down_revision = _literal_assignment(tree, "down_revision")
    parents = down_revision if isinstance(down_revision, tuple) else (down_revision,)
    for parent in parents:
        if parent is not None and (not isinstance(parent, str) or not parent.startswith(prefix)):
            errors.append(f"{path}: down_revision {parent!r} crosses the {lane} ownership lineage")

    branch_labels = _literal_assignment(tree, "branch_labels")
    if branch_labels not in (None, lane, (lane,)):
        errors.append(f"{path}: branch_labels must be absent or owned by {lane}")

    upgrade = _function(tree, "upgrade")
    downgrade = _function(tree, "downgrade")
    if upgrade is None:
        errors.append(f"{path}: migration must define upgrade()")
    if downgrade is None:
        errors.append(f"{path}: migration must define downgrade()")

    if upgrade is not None:
        destructive = _destructive_calls(upgrade, _string_constants(tree))
        note = _literal_assignment(tree, "data_migration_note")
        if destructive and (not isinstance(note, str) or not note.strip()):
            errors.append(
                f"{path}: destructive upgrade operations {destructive!r} require "
                "a non-empty data_migration_note"
            )
    return errors


def _is_noop(function: ast.FunctionDef) -> bool:
    return all(
        isinstance(statement, ast.Pass)
        or (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        )
        for statement in function.body
    )


def validate_merge_revision(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as error:
        return [f"{path}: cannot parse migration: {error}"]

    revision = _literal_assignment(tree, "revision")
    if not isinstance(revision, str):
        errors.append(f"{path}: revision must be a literal string")
    elif not revision.startswith(MERGE_PREFIX):
        errors.append(f"{path}: revision {revision} has the wrong prefix for merge")

    down_revision = _literal_assignment(tree, "down_revision")
    if not isinstance(down_revision, tuple):
        errors.append(f"{path}: merge down_revision must be a tuple")
    else:
        parent_prefixes = [
            prefix
            for parent in down_revision
            if isinstance(parent, str)
            for prefix in LANE_PREFIXES.values()
            if parent.startswith(prefix)
        ]
        if len(down_revision) != len(LANE_PREFIXES) or sorted(parent_prefixes) != sorted(
            LANE_PREFIXES.values()
        ):
            errors.append(
                f"{path}: merge down_revision must contain exactly one parent "
                "from every lane"
            )

    if _literal_assignment(tree, "branch_labels") is not None:
        errors.append(f"{path}: merge branch_labels must be absent")

    for function_name in ("upgrade", "downgrade"):
        function = _function(tree, function_name)
        if function is None:
            errors.append(f"{path}: migration must define {function_name}()")
        elif not _is_noop(function):
            errors.append(f"{path}: merge {function_name}() must not change schema or data")
    return errors


def validate_merge_topology(config: Config) -> list[str]:
    errors: list[str] = []
    script = ScriptDirectory.from_config(config)
    revisions = list(script.walk_revisions(base="base", head="heads"))
    revision_ids = {revision.revision for revision in revisions}
    lane_heads: list[str] = []

    for prefix in LANE_PREFIXES.values():
        lane_revisions = {revision for revision in revision_ids if revision.startswith(prefix)}
        lane_parents = {
            parent
            for revision in revisions
            if revision.revision in lane_revisions
            for parent in revision._normalized_down_revisions
            if parent in lane_revisions
        }
        heads = sorted(lane_revisions - lane_parents)
        if len(heads) != 1:
            errors.append(f"expected one current lane head for {prefix}, found {heads!r}")
        else:
            lane_heads.append(heads[0])

    merge_revisions = [
        revision for revision in revisions if revision.revision.startswith(MERGE_PREFIX)
    ]
    if len(merge_revisions) != 1:
        errors.append(f"expected exactly one merge revision, found {len(merge_revisions)}")
        return errors

    merge_revision = merge_revisions[0]
    merge_parents = sorted(merge_revision._normalized_down_revisions)
    if merge_parents != sorted(lane_heads):
        errors.append(
            f"merge revision parents {merge_parents!r} do not match current lane heads "
            f"{sorted(lane_heads)!r}"
        )

    heads = sorted(script.get_heads())
    if heads != [merge_revision.revision]:
        errors.append(
            f"expected the merge revision to be the single final head, found {heads!r}"
        )
    return errors


def check(config_path: Path) -> list[str]:
    config = Config(str(config_path))
    errors: list[str] = []
    seen_locations: set[str] = set()
    for raw_location in config.get_version_locations_list() or []:
        location = Path(raw_location)
        lane = location.name
        seen_locations.add(lane)
        if lane == MERGE_LANE:
            for path in sorted(location.glob("*.py")):
                if path.name != "__init__.py":
                    errors.extend(validate_merge_revision(path))
            continue
        prefix = LANE_PREFIXES.get(lane)
        if prefix is None:
            errors.append(f"{location}: unknown migration ownership directory")
            continue
        for path in sorted(location.glob("*.py")):
            if path.name != "__init__.py":
                errors.extend(validate_revision(path, lane, prefix))

    missing = {*LANE_PREFIXES, MERGE_LANE} - seen_locations
    if missing:
        errors.append(f"missing migration ownership directories: {sorted(missing)!r}")
    if not errors:
        errors.extend(validate_merge_topology(config))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    errors = check(args.config.resolve())
    if errors:
        sys.stderr.write("\n".join(errors) + "\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
