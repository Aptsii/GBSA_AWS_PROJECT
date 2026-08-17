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

LANE_PREFIXES = {
    "company": "a_",
    "submission": "b_",
    "interview": "c_",
    "reporting": "d_",
}
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


def check(config_path: Path) -> list[str]:
    config = Config(str(config_path))
    errors: list[str] = []
    seen_lanes: set[str] = set()
    for raw_location in config.get_version_locations_list() or []:
        location = Path(raw_location)
        lane = location.name
        prefix = LANE_PREFIXES.get(lane)
        if prefix is None:
            errors.append(f"{location}: unknown migration ownership directory")
            continue
        seen_lanes.add(lane)
        for path in sorted(location.glob("*.py")):
            if path.name != "__init__.py":
                errors.extend(validate_revision(path, lane, prefix))

    missing = set(LANE_PREFIXES) - seen_lanes
    if missing:
        errors.append(f"missing migration ownership directories: {sorted(missing)!r}")
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
