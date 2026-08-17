#!/usr/bin/env python3
"""Reject imports that bypass another domain module's public boundary."""

from __future__ import annotations

import argparse
import ast
import importlib.util
import re
import sys
from pathlib import Path

MODULES = {
    "company_management",
    "submission_analysis",
    "interview_engine",
    "reporting",
}
PUBLIC_BOUNDARIES = {"api", "contracts", "events"}
WORKER_OWNERS = {
    "analysis": "submission_analysis",
    "interview": "interview_engine",
    "reporting": "reporting",
}
TABLE_OWNERS = {
    "company_management": {
        "companies",
        "company_users",
        "positions",
        "competency_model_versions",
        "evaluation_criteria",
        "campaigns",
        "invitations",
        "consent_records",
        "applicant_profiles",
    },
    "submission_analysis": {
        "submissions",
        "submission_analyses",
        "submission_chunks",
        "git_repository_analyses",
        "git_commit_analyses",
        "candidate_code_units",
        "interview_strategies",
    },
    "interview_engine": {
        "interview_sessions",
        "turns",
        "session_checkpoints",
        "recording_chunks",
    },
    "reporting": {
        "transcript_segments",
        "recording_assets",
        "session_events",
        "reports",
        "report_items",
        "evidence",
        "human_reviews",
        "deletion_requests",
        "deletion_targets",
    },
}
SQL_OPERATION = re.compile(r"\b(?:select|insert|update|delete|join|from)\b", re.IGNORECASE)


def owning_scope(path: Path, source_root: Path) -> tuple[str, str | None] | None:
    relative = path.relative_to(source_root)
    if not relative.parts:
        return None
    if relative.parts[0] in MODULES:
        return relative.parts[0], relative.parts[0]
    if len(relative.parts) > 1 and relative.parts[0] == "workers":
        worker = relative.parts[1]
        if worker in WORKER_OWNERS:
            return f"workers/{worker}", WORKER_OWNERS[worker]
        if len(relative.parts) == 2 and relative.name in {"__init__.py", "__main__.py"}:
            return "composition", None
    if relative.parts[0] == "shared" or relative.name in {"__init__.py", "main.py"}:
        return "composition", None
    return "unowned", None


def imported_module(name: str) -> tuple[str, str | None] | None:
    parts = name.split(".")
    if len(parts) < 2 or parts[0] != "interview_evidence" or parts[1] not in MODULES:
        return None
    boundary = parts[2] if len(parts) > 2 else None
    return parts[1], boundary


def current_package(path: Path, source_root: Path) -> str:
    relative = path.relative_to(source_root)
    package_parts = ["interview_evidence", *relative.parent.parts]
    return ".".join(package_parts)


def imported_names(
    node: ast.AST,
    package: str,
    *,
    constants: dict[str, str],
    dynamic_importers: set[str],
) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if not isinstance(node, ast.ImportFrom):
        if isinstance(node, ast.Call) and node.args:
            function_name = ""
            if isinstance(node.func, ast.Name):
                function_name = node.func.id
            elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                function_name = f"{node.func.value.id}.{node.func.attr}"
            argument = node.args[0]
            argument_value: str | None = None
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                argument_value = argument.value
            elif isinstance(argument, ast.Name):
                argument_value = constants.get(argument.id)
            if function_name in dynamic_importers and argument_value is not None:
                return [argument_value]
        return []

    module = node.module or ""
    if node.level:
        relative_name = f"{'.' * node.level}{module}"
        try:
            module = importlib.util.resolve_name(relative_name, package)
        except (ImportError, ValueError):
            return []
    if not module:
        return []
    return [module if alias.name == "*" else f"{module}.{alias.name}" for alias in node.names]


def module_constants(tree: ast.Module) -> dict[str, str]:
    constants: dict[str, str] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            constants[node.targets[0].id] = node.value.value
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            constants[node.target.id] = node.value.value
    return constants


def dynamic_importer_names(tree: ast.Module) -> set[str]:
    importers = {"__import__", "importlib.import_module"}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "importlib" and alias.asname:
                    importers.add(f"{alias.asname}.import_module")
        elif isinstance(node, ast.ImportFrom) and node.module == "importlib":
            for alias in node.names:
                if alias.name == "import_module":
                    importers.add(alias.asname or alias.name)
    return importers


def queried_cross_lane_tables(node: ast.AST, owner_module: str | None) -> list[tuple[str, str]]:
    if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
        return []
    if SQL_OPERATION.search(node.value) is None:
        return []
    return [
        (table, module)
        for module, tables in TABLE_OWNERS.items()
        if module != owner_module
        for table in tables
        if re.search(rf"\b{re.escape(table)}\b", node.value, re.IGNORECASE)
    ]


def violations(source_root: Path) -> list[str]:
    errors: list[str] = []
    for path in sorted(source_root.rglob("*.py")):
        scope = owning_scope(path, source_root)
        if scope is None:
            continue
        owner_label, owner_module = scope
        if owner_label == "unowned":
            errors.append(
                f"{path}:0: unowned source path must be assigned to a lane or Integration"
            )
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as error:
            errors.append(f"{path}:{error.lineno}: invalid syntax: {error.msg}")
            continue

        constants = module_constants(tree)
        dynamic_importers = dynamic_importer_names(tree)

        for node in ast.walk(tree):
            for name in imported_names(
                node,
                current_package(path, source_root),
                constants=constants,
                dynamic_importers=dynamic_importers,
            ):
                imported = imported_module(name)
                if imported is None:
                    continue
                target, boundary = imported
                if target != owner_module and boundary not in PUBLIC_BOUNDARIES:
                    errors.append(
                        f"{path}:{getattr(node, 'lineno', 0)}: "
                        f"{owner_label} cannot import {name}; "
                        f"use {target}.api, {target}.contracts, or {target}.events"
                    )
            for table, table_owner in queried_cross_lane_tables(node, owner_module):
                errors.append(
                    f"{path}:{getattr(node, 'lineno', 0)}: {owner_label} cannot query "
                    f"{table}; table is owned by {table_owner}"
                )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "source_root",
        nargs="?",
        default="backend/src/interview_evidence",
        type=Path,
    )
    args = parser.parse_args()
    errors = violations(args.source_root.resolve())
    if errors:
        sys.stdout.write("\n".join(errors) + "\n")
        return 1
    sys.stdout.write("Module boundary check passed.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
