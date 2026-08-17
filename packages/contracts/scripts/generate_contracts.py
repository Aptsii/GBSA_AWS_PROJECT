#!/usr/bin/env python3
"""Deterministically compose canonical contracts and generate language bindings."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import yaml

LANE_DIRECTORY = {
    "A": "company",
    "B": "submission",
    "C": "interview",
    "D": "reporting",
}
LANE_ORDER = tuple(LANE_DIRECTORY.values())
JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def _yaml_bytes(value: Any) -> bytes:
    return yaml.safe_dump(
        value,
        allow_unicode=True,
        sort_keys=False,
        width=100,
    ).encode()


def _pointer_token(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _schema_refs(value: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, list):
        for item in value:
            refs.update(_schema_refs(item))
    elif isinstance(value, dict):
        ref = value.get("$ref")
        prefix = "#/components/schemas/"
        if isinstance(ref, str) and ref.startswith(prefix):
            refs.add(ref.removeprefix(prefix))
        for item in value.values():
            refs.update(_schema_refs(item))
    return refs


def _schema_closure(seed: Iterable[str], schemas: Mapping[str, Any]) -> set[str]:
    closure = set(seed)
    pending = list(closure)
    while pending:
        name = pending.pop()
        for dependency in _schema_refs(schemas[name]):
            if dependency not in closure:
                closure.add(dependency)
                pending.append(dependency)
    return closure


def render_openapi_files(repository_root: Path) -> dict[Path, bytes]:
    source_path = (
        repository_root / "specs" / "001-interview-evidence-platform" / "contracts" / "openapi.yaml"
    )
    source = yaml.safe_load(source_path.read_text(encoding="utf-8"))
    if not isinstance(source, dict):
        raise ValueError("canonical OpenAPI document must be a mapping")

    components = source["components"]
    schemas = components["schemas"]
    grouped_paths: dict[str, dict[str, Any]] = {lane: {} for lane in LANE_ORDER}

    for route, path_item in source["paths"].items():
        owners = {
            operation["x-owner-lane"]
            for operation in path_item.values()
            if isinstance(operation, dict) and "x-owner-lane" in operation
        }
        if len(owners) != 1:
            raise ValueError(f"route must have exactly one owner lane: {route}")
        owner = owners.pop()
        grouped_paths[LANE_DIRECTORY[owner]][route] = copy.deepcopy(path_item)

    lane_schemas: dict[str, set[str]] = {}
    for lane, paths in grouped_paths.items():
        seeds = _schema_refs(paths)
        seeds.update(_schema_refs(components["responses"]))
        lane_schemas[lane] = _schema_closure(seeds, schemas)

    schema_owner: dict[str, str] = {}
    for schema_name in schemas:
        schema_owner[schema_name] = next(
            (lane for lane in LANE_ORDER if schema_name in lane_schemas[lane]),
            "company",
        )

    openapi_root = repository_root / "packages" / "contracts" / "openapi"
    rendered: dict[Path, bytes] = {}
    for lane in LANE_ORDER:
        fragment = {
            "paths": grouped_paths[lane],
            "components": {
                "securitySchemes": copy.deepcopy(components["securitySchemes"]),
                "parameters": copy.deepcopy(components["parameters"]),
                "responses": copy.deepcopy(components["responses"]),
                "schemas": {
                    name: copy.deepcopy(schema)
                    for name, schema in schemas.items()
                    if name in lane_schemas[lane]
                },
            },
        }
        rendered[openapi_root / "paths" / lane / "contract.yaml"] = _yaml_bytes(fragment)

    root = {key: copy.deepcopy(source[key]) for key in ("openapi", "info", "servers", "tags")}
    root_paths: dict[str, Any] = {}
    for route, path_item in source["paths"].items():
        owner = next(
            operation["x-owner-lane"]
            for operation in path_item.values()
            if isinstance(operation, dict) and "x-owner-lane" in operation
        )
        lane = LANE_DIRECTORY[owner]
        root_paths[route] = {"$ref": f"./paths/{lane}/contract.yaml#/paths/{_pointer_token(route)}"}
    root["paths"] = root_paths
    root["components"] = {
        "securitySchemes": copy.deepcopy(components["securitySchemes"]),
        "parameters": copy.deepcopy(components["parameters"]),
        "responses": copy.deepcopy(components["responses"]),
        "schemas": {
            name: {
                "$ref": (
                    f"./paths/{schema_owner[name]}/contract.yaml"
                    f"#/components/schemas/{_pointer_token(name)}"
                )
            }
            for name in schemas
        },
    }
    rendered[openapi_root / "root.yaml"] = _yaml_bytes(root)
    return rendered


def _load_document(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text) if path.suffix in {".yaml", ".yml"} else json.loads(text)


def _json_pointer(document: Any, pointer: str) -> Any:
    current = document
    if not pointer:
        return current
    if not pointer.startswith("/"):
        raise ValueError(f"invalid JSON pointer: {pointer}")
    for raw_part in pointer[1:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        current = current[int(part)] if isinstance(current, list) else current[part]
    return current


def _resolve_ref(ref: str, current_path: Path) -> tuple[Any, Path, str]:
    file_part, _, pointer = ref.partition("#")
    target_path = (current_path.parent / file_part).resolve() if file_part else current_path
    document = _load_document(target_path)
    return _json_pointer(document, pointer), target_path, pointer


def _merge_schema(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(dict(left))
    for key, right_value in right.items():
        if key == "required":
            merged[key] = list(dict.fromkeys([*merged.get(key, []), *right_value]))
        elif key == "properties" and isinstance(merged.get(key), dict):
            properties = copy.deepcopy(merged[key])
            for property_name, property_schema in right_value.items():
                if property_name in properties:
                    properties[property_name] = _merge_schema(
                        properties[property_name],
                        property_schema,
                    )
                else:
                    properties[property_name] = copy.deepcopy(property_schema)
            merged[key] = properties
        elif key in merged and isinstance(merged[key], dict) and isinstance(right_value, dict):
            merged[key] = _merge_schema(merged[key], right_value)
        else:
            merged[key] = copy.deepcopy(right_value)
    return merged


def _dereference(
    value: Any,
    current_path: Path,
    active_refs: frozenset[str] = frozenset(),
) -> Any:
    if isinstance(value, list):
        return [_dereference(item, current_path, active_refs) for item in value]
    if not isinstance(value, dict):
        return value

    if "$ref" in value:
        resolved, target_path, pointer = _resolve_ref(value["$ref"], current_path)
        ref_key = f"{target_path}#{pointer}"
        if ref_key in active_refs:
            return {}
        dereferenced = _dereference(resolved, target_path, active_refs | {ref_key})
        siblings = {
            key: _dereference(item, current_path, active_refs)
            for key, item in value.items()
            if key != "$ref"
        }
        if isinstance(dereferenced, dict):
            return _merge_schema(dereferenced, siblings)
        return dereferenced

    dereferenced = {
        key: _dereference(item, current_path, active_refs)
        for key, item in value.items()
        if key != "$defs"
    }
    all_of = dereferenced.pop("allOf", None)
    if all_of:
        merged: dict[str, Any] = {}
        for part in all_of:
            if not isinstance(part, dict):
                raise ValueError("allOf entries must be schemas")
            merged = _merge_schema(merged, part)
        dereferenced = _merge_schema(merged, dereferenced)
    return dereferenced


def _catalog_models(catalog_path: Path, collection: str) -> dict[str, Any]:
    catalog = _load_document(catalog_path)
    models: dict[str, Any] = {}
    for entry in catalog[collection]:
        schema, schema_path, pointer = _resolve_ref(entry["schema"], catalog_path)
        ref_key = f"{schema_path}#{pointer}"
        models[entry["model_name"] if "model_name" in entry else entry["name"]] = _dereference(
            schema, schema_path, frozenset({ref_key})
        )
    return models


def _all_models(repository_root: Path) -> dict[str, Any]:
    source_openapi = (
        repository_root / "specs" / "001-interview-evidence-platform" / "contracts" / "openapi.yaml"
    )
    openapi = _load_document(source_openapi)
    models = {
        name: _dereference(schema, source_openapi)
        for name, schema in openapi["components"]["schemas"].items()
    }
    contracts_root = repository_root / "packages" / "contracts"
    catalogs = (
        (contracts_root / "events" / "websocket" / "v1" / "catalog.json", "messages"),
        (contracts_root / "events" / "catalog.v1.json", "events"),
        (contracts_root / "modules" / "v1" / "catalog.json", "snapshots"),
    )
    for catalog_path, collection in catalogs:
        for name, schema in _catalog_models(catalog_path, collection).items():
            if name in models:
                raise ValueError(f"duplicate generated model name: {name}")
            models[name] = schema
    return models


def _minimum_instance(schema: Any, full_instance: Any) -> Any:
    """Prune a known-valid instance to the fields required by its schema."""
    if not isinstance(schema, dict):
        return copy.deepcopy(full_instance)

    schema_type = schema.get("type")
    if schema_type == "object" or "properties" in schema:
        required = schema.get("required", [])
        properties = schema.get("properties", {})
        return {
            name: _minimum_instance(properties.get(name, {}), full_instance[name])
            for name in required
        }
    if schema_type == "array":
        minimum_count = schema.get("minItems", 0)
        return [
            _minimum_instance(schema.get("items", {}), item)
            for item in full_instance[:minimum_count]
        ]
    return copy.deepcopy(full_instance)


def render_event_compatibility_files(repository_root: Path) -> dict[Path, bytes]:
    """Render the seven required consumer-compatibility scenarios for every event version."""
    catalog_path = repository_root / "packages" / "contracts" / "events" / "catalog.v1.json"
    catalog = _load_document(catalog_path)
    rendered: dict[Path, bytes] = {}
    wrong_tenant_company_id = "018f1000-0000-7000-8000-999999999999"

    for entry in catalog["events"]:
        schema, schema_path, pointer = _resolve_ref(entry["schema"], catalog_path)
        ref_key = f"{schema_path}#{pointer}"
        dereferenced_schema = _dereference(schema, schema_path, frozenset({ref_key}))
        full_message = _load_document((catalog_path.parent / entry["example"]).resolve())
        minimum_message = _minimum_instance(dereferenced_schema, full_message)
        unsupported_message = copy.deepcopy(full_message)
        unsupported_message["event_version"] = entry["event_version"] + 1

        if full_message["company_id"] == wrong_tenant_company_id:
            raise ValueError("compatibility wrong-tenant context must differ from event company_id")

        compatibility = {
            "event_type": entry["event_type"],
            "event_version": entry["event_version"],
            "messages": {
                "full": full_message,
                "minimum": minimum_message,
                "unsupported_version": unsupported_message,
            },
            "scenarios": {
                "duplicate": {
                    "delivery_count": 2,
                    "expectation": "idempotent_replay",
                    "message": "full",
                },
                "full": {"expectation": "accepted", "message": "full"},
                "minimum": {"expectation": "accepted", "message": "minimum"},
                "non_retryable_failure": {
                    "expectation": "rejected",
                    "failure_code": "BUSINESS_REJECTION",
                    "message": "full",
                    "retryable": False,
                },
                "retryable_failure": {
                    "expectation": "retry",
                    "failure_code": "DEPENDENCY_TIMEOUT",
                    "message": "full",
                    "retryable": True,
                },
                "unsupported_version": {
                    "error_code": "UNSUPPORTED_EVENT_VERSION",
                    "expectation": "quarantined",
                    "message": "unsupported_version",
                },
                "wrong_tenant": {
                    "error_code": "TENANT_SCOPE_MISMATCH",
                    "expectation": "rejected",
                    "message": "full",
                    "tenant_context_company_id": wrong_tenant_company_id,
                },
            },
        }
        output_path = (catalog_path.parent / entry["compatibility"]).resolve()
        rendered[output_path] = _json_bytes(compatibility)
    return rendered


def _pascal_case(value: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", value)
    if not words:
        return "Anonymous"
    candidate = "".join(word[0].upper() + word[1:] for word in words)
    return f"Model{candidate}" if candidate[0].isdigit() else candidate


def _python_literal(value: Any) -> str:
    if value is None:
        return "None"
    if value is True:
        return "True"
    if value is False:
        return "False"
    return repr(value)


class PythonRenderer:
    def __init__(self) -> None:
        self._definitions: dict[str, str] = {}
        self._in_progress: set[str] = set()

    def type_expression(self, schema: Any, name_hint: str) -> str:
        if not isinstance(schema, dict):
            return "Any"
        if "const" in schema:
            return f"Literal[{_python_literal(schema['const'])}]"
        if "enum" in schema:
            literals = ", ".join(_python_literal(item) for item in schema["enum"])
            return f"Literal[{literals}]"
        if "oneOf" in schema:
            types = [
                self.type_expression(item, f"{name_hint}Option{index}")
                for index, item in enumerate(schema["oneOf"], start=1)
            ]
            return " | ".join(dict.fromkeys(types))

        schema_type = schema.get("type")
        if isinstance(schema_type, list):
            types = [
                self.type_expression({**schema, "type": item}, name_hint) for item in schema_type
            ]
            return " | ".join(dict.fromkeys(types))
        if schema_type == "string":
            return "str"
        if schema_type == "integer":
            return "int"
        if schema_type == "number":
            return "float"
        if schema_type == "boolean":
            return "bool"
        if schema_type == "null":
            return "None"
        if schema_type == "array":
            item_type = self.type_expression(schema.get("items", {}), f"{name_hint}Item")
            return f"list[{item_type}]"
        if schema_type == "object" or "properties" in schema:
            properties = schema.get("properties", {})
            if not properties:
                additional = schema.get("additionalProperties")
                if isinstance(additional, dict):
                    return f"dict[str, {self.type_expression(additional, name_hint + 'Value')}]"
                return "dict[str, Any]"
            return self._typed_dict(schema, _pascal_case(name_hint))
        return "Any"

    def _typed_dict(self, schema: Mapping[str, Any], name: str) -> str:
        if name in self._definitions or name in self._in_progress:
            return name
        self._in_progress.add(name)
        required = set(schema.get("required", []))
        fields: list[tuple[str, str, bool]] = []
        for property_name, property_schema in schema.get("properties", {}).items():
            child_name = f"{name}{_pascal_case(property_name)}"
            fields.append(
                (
                    property_name,
                    self.type_expression(property_schema, child_name),
                    property_name in required,
                )
            )
        lines = [f"class {name}(TypedDict, total=False):"]
        for property_name, property_type, is_required in fields:
            wrapper = "Required" if is_required else "NotRequired"
            lines.append(f"    {property_name}: {wrapper}[{property_type}]")
        self._definitions[name] = "\n".join(lines)
        self._in_progress.remove(name)
        return name

    def render(self, models: Mapping[str, Any]) -> bytes:
        aliases: list[str] = []
        exported: list[str] = []
        for raw_name, schema in models.items():
            name = _pascal_case(raw_name)
            expression = self.type_expression(schema, name)
            exported.append(name)
            if expression != name:
                aliases.append(f"{name}: TypeAlias = {expression}")

        header = (
            '"""Generated contract types. DO NOT EDIT.\n\n'
            "Run packages/contracts/scripts/generate_contracts.py instead.\n"
            '"""\n\n'
            "from __future__ import annotations\n\n"
            "from typing import Any, Literal, NotRequired, Required, TypeAlias, TypedDict\n"
        )
        blocks = [header, *self._definitions.values(), *aliases]
        exports = "__all__ = [\n" + "".join(f'    "{name}",\n' for name in exported) + "]"
        return ("\n\n".join([*blocks, exports]) + "\n").encode()


def _typescript_literal(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


class TypeScriptRenderer:
    def type_expression(self, schema: Any, indent: int = 0) -> str:
        if not isinstance(schema, dict):
            return "unknown"
        if "const" in schema:
            return _typescript_literal(schema["const"])
        if "enum" in schema:
            return " | ".join(_typescript_literal(item) for item in schema["enum"])
        if "oneOf" in schema:
            types = [self.type_expression(item, indent) for item in schema["oneOf"]]
            return " | ".join(dict.fromkeys(types))

        schema_type = schema.get("type")
        if isinstance(schema_type, list):
            types = [self.type_expression({**schema, "type": item}, indent) for item in schema_type]
            return " | ".join(dict.fromkeys(types))
        if schema_type == "string":
            return "string"
        if schema_type in {"integer", "number"}:
            return "number"
        if schema_type == "boolean":
            return "boolean"
        if schema_type == "null":
            return "null"
        if schema_type == "array":
            item_type = self.type_expression(schema.get("items", {}), indent)
            return f"Array<{item_type}>"
        if schema_type == "object" or "properties" in schema:
            properties = schema.get("properties", {})
            if not properties:
                additional = schema.get("additionalProperties")
                value_type = (
                    self.type_expression(additional, indent)
                    if isinstance(additional, dict)
                    else "unknown"
                )
                return f"Record<string, {value_type}>"
            required = set(schema.get("required", []))
            pad = " " * indent
            child_pad = " " * (indent + 2)
            lines = ["{"]
            for property_name, property_schema in properties.items():
                optional = "" if property_name in required else "?"
                key = (
                    property_name
                    if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", property_name)
                    else json.dumps(property_name)
                )
                value_type = self.type_expression(property_schema, indent + 2)
                lines.append(f"{child_pad}{key}{optional}: {value_type};")
            lines.append(f"{pad}}}")
            return "\n".join(lines)
        return "unknown"

    def render(self, models: Mapping[str, Any]) -> bytes:
        blocks = [
            "// Generated contract types. DO NOT EDIT.",
            "// Run packages/contracts/scripts/generate_contracts.py instead.",
        ]
        for raw_name, schema in models.items():
            name = _pascal_case(raw_name)
            blocks.append(f"export type {name} = {self.type_expression(schema)};")
        return ("\n\n".join(blocks) + "\n").encode()


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _relative(repository_root: Path, path: Path) -> str:
    return path.resolve().relative_to(repository_root.resolve()).as_posix()


def _canonical_sources(
    repository_root: Path,
    openapi_files: Mapping[Path, bytes],
) -> dict[str, bytes]:
    contracts_root = repository_root / "packages" / "contracts"
    source_openapi = (
        repository_root / "specs" / "001-interview-evidence-platform" / "contracts" / "openapi.yaml"
    )
    sources = {_relative(repository_root, source_openapi): source_openapi.read_bytes()}
    generator_path = contracts_root / "scripts" / "generate_contracts.py"
    sources[_relative(repository_root, generator_path)] = generator_path.read_bytes()
    for root_name in ("events", "modules"):
        for path in sorted((contracts_root / root_name).rglob("*.json")):
            relative_parts = path.relative_to(contracts_root / root_name).parts
            if root_name == "events" and relative_parts[0] == "compatibility":
                continue
            sources[_relative(repository_root, path)] = path.read_bytes()
    for path, content in sorted(openapi_files.items(), key=lambda item: item[0].as_posix()):
        sources[_relative(repository_root, path)] = content
    return sources


def render_generated_files(repository_root: Path) -> dict[Path, bytes]:
    contracts_root = repository_root / "packages" / "contracts"
    generated_root = contracts_root / "generated"
    models = _all_models(repository_root)
    schema_bundle = {
        "$schema": JSON_SCHEMA_DIALECT,
        "title": "Interview Evidence Platform Generated Contract Bundle",
        "$defs": models,
    }
    readme = """# Generated Contract Bindings

These files are deterministic outputs of the canonical REST, WebSocket, asynchronous-event and
module-snapshot schemas in `packages/contracts`.

Do not edit files in this directory by hand. Run:

```text
python packages/contracts/scripts/generate_contracts.py
python packages/contracts/scripts/generate_contracts.py --check
```

The Python output uses standard-library `TypedDict`/`Literal` types. The TypeScript output uses
structural aliases, so consumers require no contract-generator runtime dependency.
"""
    rendered: dict[Path, bytes] = {
        generated_root
        / "python"
        / "interview_evidence_contracts"
        / "models.py": PythonRenderer().render(models),
        generated_root / "python" / "interview_evidence_contracts" / "__init__.py": (
            b'"""Generated Interview Evidence Platform contract types."""\n\n'
            b"from .models import *  # noqa: F403\n"
        ),
        generated_root / "python" / "interview_evidence_contracts" / "py.typed": b"",
        generated_root / "typescript" / "index.ts": TypeScriptRenderer().render(models),
        generated_root / "schema-bundle.json": _json_bytes(schema_bundle),
        generated_root / "README.md": readme.encode(),
    }
    openapi_files = render_openapi_files(repository_root)
    sources = _canonical_sources(repository_root, openapi_files)
    compatibility_files = render_event_compatibility_files(repository_root)
    manifest = {
        "generator": "packages/contracts/scripts/generate_contracts.py",
        "schema_version": 1,
        "sources": {name: _sha256(content) for name, content in sorted(sources.items())},
        "outputs": {
            _relative(repository_root, path): _sha256(content)
            for path, content in sorted(
                {**compatibility_files, **rendered}.items(),
                key=lambda item: item[0].as_posix(),
            )
        },
    }
    rendered[generated_root / "manifest.json"] = _json_bytes(manifest)
    return rendered


def _managed_files(repository_root: Path) -> dict[Path, bytes]:
    return {
        **render_openapi_files(repository_root),
        **render_event_compatibility_files(repository_root),
        **render_generated_files(repository_root),
    }


def _unexpected_files(repository_root: Path, expected: set[Path]) -> list[Path]:
    contracts_root = repository_root / "packages" / "contracts"
    managed_roots = (
        contracts_root / "openapi",
        contracts_root / "events" / "compatibility",
        contracts_root / "generated",
    )
    actual = {
        path.resolve()
        for root in managed_roots
        if root.exists()
        for path in root.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix not in {".pyc", ".pyo"}
    }
    return sorted(actual - {path.resolve() for path in expected})


def check_contracts(repository_root: Path) -> list[str]:
    expected = _managed_files(repository_root)
    errors: list[str] = []
    for path, content in expected.items():
        if not path.exists():
            errors.append(f"missing generated file: {_relative(repository_root, path)}")
        elif path.read_bytes() != content:
            errors.append(f"contract drift: {_relative(repository_root, path)}")
    for path in _unexpected_files(repository_root, set(expected)):
        errors.append(f"unexpected generated file: {_relative(repository_root, path)}")
    return errors


def write_contracts(repository_root: Path) -> None:
    expected = _managed_files(repository_root)
    for path, content in expected.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail when committed files drift")
    args = parser.parse_args(argv)
    repository_root = _repository_root()
    if args.check:
        errors = check_contracts(repository_root)
        if errors:
            sys.stderr.write("\n".join(errors) + "\n")
            return 1
        sys.stdout.write("Canonical and generated contracts are current.\n")
        return 0
    write_contracts(repository_root)
    sys.stdout.write("Canonical fragments and generated contract bindings updated.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
