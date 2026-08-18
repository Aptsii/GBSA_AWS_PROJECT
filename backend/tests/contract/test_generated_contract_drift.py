from __future__ import annotations

import copy
import json
import runpy
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CONTRACTS_ROOT = REPOSITORY_ROOT / "packages" / "contracts"
SOURCE_OPENAPI = (
    REPOSITORY_ROOT / "specs" / "001-interview-evidence-platform" / "contracts" / "openapi.yaml"
)
GENERATOR = CONTRACTS_ROOT / "scripts" / "generate_contracts.py"

EXPECTED_WEBSOCKET_MESSAGES = {
    "answer.complete",
    "answer.text.submit",
    "audio.chunk.begin",
    "client.ack",
    "error",
    "heartbeat.ping",
    "question.preparing",
    "question.ready",
    "question.repeat",
    "resume.snapshot",
    "session.completed",
    "session.paused",
    "session.resume",
    "session.start",
    "session.state_changed",
    "transcript.final",
    "transcript.partial",
}
EXPECTED_ASYNC_EVENTS = {
    "deletion.requested",
    "deletion.target_requested",
    "deletion.target_verified",
    "interview.completed",
    "interview.session_paused",
    "interview.turn_finalized",
    "invitation.consent_completed",
    "invitation.email_requested",
    "media.postprocess_requested",
    "report.generation_requested",
    "report.ready",
    "retention.expired",
    "strategy.ready",
    "submission.analysis_completed",
    "submission.analysis_requested",
}
EXPECTED_MODULE_SNAPSHOTS = {
    "AuditAppendReceipt",
    "CampaignSnapshot",
    "CompanyDeletionTargetEnumerationSnapshot",
    "CompanyDeletionTargetReceipt",
    "ConsentAuthorizationSnapshot",
    "CriterionVersionSnapshot",
    "DeletionStatusSnapshot",
    "FinalTurnSnapshot",
    "FinalTurnPageSnapshot",
    "InterviewDeletionTargetEnumerationSnapshot",
    "InterviewDeletionTargetReceipt",
    "InvitationAuthorizationSnapshot",
    "InvitationStateTransitionSnapshot",
    "RecordingChunkSetSnapshot",
    "ReportSnapshot",
    "RetrievedContextSnapshot",
    "ReviewProjectionSnapshot",
    "SessionSnapshot",
    "SourceReferenceSnapshot",
    "StrategySnapshot",
    "SubmissionDeletionTargetEnumerationSnapshot",
    "SubmissionDeletionTargetReceipt",
    "SubmissionAnalysisStatusSnapshot",
}
EXPECTED_MODULE_INTERFACES = {
    "advance_invitation_state",
    "append_audit_event",
    "authorize_invitation",
    "delete_interview_target",
    "delete_company_target",
    "delete_submission_target",
    "enumerate_interview_deletion_targets",
    "enumerate_company_deletion_targets",
    "enumerate_submission_deletion_targets",
    "get_analysis_status",
    "get_campaign_snapshot",
    "get_consent_authorization",
    "get_criterion_version",
    "get_deletion_status",
    "get_final_turn",
    "get_report",
    "get_review_projection",
    "get_session_snapshot",
    "get_strategy_snapshot",
    "list_final_turns",
    "request_deletion",
    "resolve_recording_chunks",
    "resolve_source_reference",
    "retrieve_context",
}


def _load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _json_pointer(document: Any, pointer: str) -> Any:
    current = document
    if not pointer:
        return current
    assert pointer.startswith("/")
    for raw_part in pointer[1:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        current = current[int(part)] if isinstance(current, list) else current[part]
    return current


def _resolve_ref(ref: str, current_path: Path) -> tuple[Any, Path]:
    file_part, _, pointer = ref.partition("#")
    target_path = (current_path.parent / file_part).resolve() if file_part else current_path
    document = _load_json(target_path)
    return _json_pointer(document, pointer), target_path


def _bundle_schema(value: Any, current_path: Path) -> Any:
    if isinstance(value, list):
        return [_bundle_schema(item, current_path) for item in value]
    if not isinstance(value, dict):
        return value

    if "$ref" in value:
        resolved, target_path = _resolve_ref(value["$ref"], current_path)
        bundled = _bundle_schema(resolved, target_path)
        siblings = {key: item for key, item in value.items() if key != "$ref"}
        if not siblings:
            return bundled
        return {
            "allOf": [bundled, _bundle_schema(siblings, current_path)],
        }

    return {key: _bundle_schema(item, current_path) for key, item in value.items()}


def _resolve_yaml_ref(ref: str, current_path: Path) -> Any:
    file_part, _, pointer = ref.partition("#")
    target_path = (current_path.parent / file_part).resolve() if file_part else current_path
    return _json_pointer(_load_yaml(target_path), pointer)


def _load_generator() -> ModuleType:
    module = ModuleType("contract_generator")
    module.__dict__.update(runpy.run_path(str(GENERATOR), run_name="contract_generator"))
    return module


def _assert_catalog_examples(catalog_path: Path, key: str) -> set[str]:
    catalog = _load_json(catalog_path)
    entries = catalog[key]
    assert isinstance(entries, list)
    names: set[str] = set()

    for entry in entries:
        assert isinstance(entry, dict)
        name = entry["message_type"] if key == "messages" else entry["event_type"]
        assert name not in names
        names.add(name)

        schema_ref = entry["schema"]
        schema_value, schema_path = _resolve_ref(schema_ref, catalog_path)
        schema = _bundle_schema(schema_value, schema_path)
        Draft202012Validator.check_schema(schema)

        example_path = (catalog_path.parent / entry["example"]).resolve()
        example = _load_json(example_path)
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(example)
        assert example["message_type" if key == "messages" else "event_type"] == name

    return names


def test_openapi_fragments_reproduce_the_canonical_contract() -> None:
    source = _load_yaml(SOURCE_OPENAPI)
    root_path = CONTRACTS_ROOT / "openapi" / "root.yaml"
    packaged = _load_yaml(root_path)

    assert packaged["openapi"] == source["openapi"]
    assert packaged["info"] == source["info"]
    assert packaged["servers"] == source["servers"]
    assert packaged["tags"] == source["tags"]

    assert set(packaged["paths"]) == set(source["paths"])
    for route, source_path_item in source["paths"].items():
        packaged_ref = packaged["paths"][route]
        assert set(packaged_ref) == {"$ref"}
        assert packaged_ref["$ref"].startswith("./paths/")
        assert _resolve_yaml_ref(packaged_ref["$ref"], root_path) == source_path_item

    source_components = source["components"]
    packaged_components = packaged["components"]
    for common_section in ("securitySchemes", "parameters", "responses"):
        assert packaged_components[common_section] == source_components[common_section]

    assert set(packaged_components["schemas"]) == set(source_components["schemas"])
    for name, source_schema in source_components["schemas"].items():
        packaged_ref = packaged_components["schemas"][name]
        assert set(packaged_ref) == {"$ref"}
        assert packaged_ref["$ref"].startswith("./paths/")
        assert _resolve_yaml_ref(packaged_ref["$ref"], root_path) == source_schema


def test_all_websocket_messages_have_explicit_valid_schemas_and_examples() -> None:
    catalog_path = CONTRACTS_ROOT / "events" / "websocket" / "v1" / "catalog.json"
    assert _assert_catalog_examples(catalog_path, "messages") == EXPECTED_WEBSOCKET_MESSAGES


def test_full_async_event_catalog_has_valid_tenant_scoped_examples() -> None:
    catalog_path = CONTRACTS_ROOT / "events" / "catalog.v1.json"
    assert _assert_catalog_examples(catalog_path, "events") == EXPECTED_ASYNC_EVENTS

    catalog = _load_json(catalog_path)
    for entry in catalog["events"]:
        example = _load_json((catalog_path.parent / entry["example"]).resolve())
        assert example["company_id"]
        serialized = json.dumps(example["payload"], sort_keys=True).lower()
        for prohibited in ("answer_text", "document_text", "signed_url", "token", "credential"):
            assert prohibited not in serialized


def test_deletion_events_expose_normalized_scope_and_owner_lane_routing() -> None:
    catalog_path = CONTRACTS_ROOT / "events" / "catalog.v1.json"
    catalog = _load_json(catalog_path)

    requested_entry = next(
        entry for entry in catalog["events"] if entry["event_type"] == "deletion.requested"
    )
    requested_schema_value, requested_schema_path = _resolve_ref(
        requested_entry["schema"], catalog_path
    )
    requested_schema = _bundle_schema(requested_schema_value, requested_schema_path)
    requested_validator = Draft202012Validator(requested_schema, format_checker=FormatChecker())
    requested_example = _load_json((catalog_path.parent / requested_entry["example"]).resolve())
    requested_validator.validate(requested_example)
    assert requested_example["payload"]["scope_type"] in {"applicant", "invitation"}

    unsupported_scope = copy.deepcopy(requested_example)
    unsupported_scope["payload"]["scope_type"] = "session"
    with pytest.raises(ValidationError):
        requested_validator.validate(unsupported_scope)

    target_entry = next(
        entry for entry in catalog["events"] if entry["event_type"] == "deletion.target_requested"
    )
    target_schema_value, target_schema_path = _resolve_ref(target_entry["schema"], catalog_path)
    target_schema = _bundle_schema(target_schema_value, target_schema_path)
    target_validator = Draft202012Validator(target_schema, format_checker=FormatChecker())
    target_example = _load_json((catalog_path.parent / target_entry["example"]).resolve())
    target_validator.validate(target_example)
    assert target_example["payload"]["owner_lane"] in {"A", "B", "C", "D"}

    unroutable = copy.deepcopy(target_example)
    del unroutable["payload"]["owner_lane"]
    with pytest.raises(ValidationError):
        target_validator.validate(unroutable)


def test_invitation_email_event_is_id_only_and_contains_no_delivery_secret() -> None:
    catalog_path = CONTRACTS_ROOT / "events" / "catalog.v1.json"
    catalog = _load_json(catalog_path)
    entry = next(
        entry for entry in catalog["events"] if entry["event_type"] == "invitation.email_requested"
    )
    example = _load_json((catalog_path.parent / entry["example"]).resolve())

    assert set(example["payload"]) == {
        "applicant_id",
        "campaign_id",
        "email_delivery_request_id",
        "expires_at",
        "invitation_id",
        "link_resolution_id",
        "template_id",
    }
    serialized = json.dumps(example["payload"], sort_keys=True).lower()
    for prohibited in (
        "answer_text",
        "credential",
        "document_text",
        "email_address",
        "one_time_link",
        "raw_link",
        "signed_url",
        "token",
    ):
        assert prohibited not in serialized


def test_each_async_event_version_has_seven_compatibility_scenarios() -> None:
    catalog_path = CONTRACTS_ROOT / "events" / "catalog.v1.json"
    catalog = _load_json(catalog_path)
    expected_scenarios = {
        "duplicate",
        "full",
        "minimum",
        "non_retryable_failure",
        "retryable_failure",
        "unsupported_version",
        "wrong_tenant",
    }

    for entry in catalog["events"]:
        schema_value, schema_path = _resolve_ref(entry["schema"], catalog_path)
        schema = _bundle_schema(schema_value, schema_path)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        compatibility = _load_json((catalog_path.parent / entry["compatibility"]).resolve())

        assert compatibility["event_type"] == entry["event_type"]
        assert compatibility["event_version"] == entry["event_version"]
        assert set(compatibility["scenarios"]) == expected_scenarios

        messages = compatibility["messages"]
        scenarios = compatibility["scenarios"]
        for scenario_name in (
            "minimum",
            "full",
            "duplicate",
            "wrong_tenant",
            "retryable_failure",
            "non_retryable_failure",
        ):
            message = messages[scenarios[scenario_name]["message"]]
            validator.validate(message)

        assert scenarios["minimum"]["expectation"] == "accepted"
        assert scenarios["full"]["expectation"] == "accepted"
        assert scenarios["duplicate"] == {
            "delivery_count": 2,
            "expectation": "idempotent_replay",
            "message": "full",
        }

        wrong_tenant = scenarios["wrong_tenant"]
        wrong_tenant_message = messages[wrong_tenant["message"]]
        assert wrong_tenant["tenant_context_company_id"] != wrong_tenant_message["company_id"]
        assert wrong_tenant["error_code"] == "TENANT_SCOPE_MISMATCH"
        assert wrong_tenant["expectation"] == "rejected"

        unsupported = scenarios["unsupported_version"]
        unsupported_message = messages[unsupported["message"]]
        assert unsupported["error_code"] == "UNSUPPORTED_EVENT_VERSION"
        assert unsupported["expectation"] == "quarantined"
        with pytest.raises(ValidationError):
            validator.validate(unsupported_message)

        retryable = scenarios["retryable_failure"]
        assert retryable["expectation"] == "retry"
        assert retryable["failure_code"] == "DEPENDENCY_TIMEOUT"
        assert retryable["retryable"] is True

        non_retryable = scenarios["non_retryable_failure"]
        assert non_retryable["expectation"] == "rejected"
        assert non_retryable["failure_code"] == "BUSINESS_REJECTION"
        assert non_retryable["retryable"] is False


def test_public_module_snapshots_are_machine_readable_and_tenant_scoped() -> None:
    catalog_path = CONTRACTS_ROOT / "modules" / "v1" / "catalog.json"
    catalog = _load_json(catalog_path)
    snapshots = catalog["snapshots"]
    assert {entry["name"] for entry in snapshots} == EXPECTED_MODULE_SNAPSHOTS
    interfaces = [interface for entry in snapshots for interface in entry["interfaces"]]
    assert set(interfaces) == EXPECTED_MODULE_INTERFACES
    assert len(interfaces) == len(set(interfaces))

    for entry in snapshots:
        schema_value, schema_path = _resolve_ref(entry["schema"], catalog_path)
        schema = _bundle_schema(schema_value, schema_path)
        Draft202012Validator.check_schema(schema)
        example = _load_json((catalog_path.parent / entry["example"]).resolve())
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(example)
        assert example["company_id"]


def test_report_snapshot_requires_final_applicant_answer_evidence() -> None:
    catalog_path = CONTRACTS_ROOT / "modules" / "v1" / "catalog.json"
    catalog = _load_json(catalog_path)
    report_entry = next(
        entry for entry in catalog["snapshots"] if entry["name"] == "ReportSnapshot"
    )
    schema_value, schema_path = _resolve_ref(report_entry["schema"], catalog_path)
    schema = _bundle_schema(schema_value, schema_path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    example = _load_json((catalog_path.parent / report_entry["example"]).resolve())

    validator.validate(example)
    confirmed_item = next(
        item
        for item in example["items"]
        if item["assessment_state"] in {"confirmed", "partially_confirmed"}
    )
    evidence = confirmed_item["evidence"][0]
    assert evidence["evidence_type"] == "applicant_answer"
    assert evidence["answer_turn_speaker"] == "applicant"
    assert evidence["answer_turn_status"] == "final"
    assert evidence["video_start_ms"] < evidence["video_end_ms"]
    assert evidence["technical_failure_overlap"] is False
    assert "source_reference" not in json.dumps(evidence, sort_keys=True).lower()

    invalid = copy.deepcopy(example)
    invalid["items"][0]["assessment_state"] = "confirmed"
    invalid["items"][0]["evidence"] = []
    with pytest.raises(ValidationError):
        validator.validate(invalid)


def test_generated_python_and_typescript_are_byte_for_byte_current() -> None:
    generator = _load_generator()
    rendered: Mapping[Path, bytes] = generator.render_generated_files(REPOSITORY_ROOT)
    assert rendered

    expected_paths = {path.resolve() for path in rendered}
    generated_root = CONTRACTS_ROOT / "generated"
    actual_paths = {
        path.resolve()
        for path in generated_root.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix not in {".pyc", ".pyo"}
    }
    assert actual_paths == expected_paths

    for path, expected_bytes in rendered.items():
        assert path.read_bytes() == expected_bytes, f"generated contract drift: {path}"


def test_generated_schema_bundle_is_a_valid_complete_registry() -> None:
    bundle = _load_json(CONTRACTS_ROOT / "generated" / "schema-bundle.json")
    Draft202012Validator.check_schema(bundle)
    definitions = bundle["$defs"]

    assert set(EXPECTED_MODULE_SNAPSHOTS) <= set(definitions)
    assert {
        "AnswerCompleteMessage",
        "InterviewCompletedEventV1",
        "ReportView",
    } <= set(definitions)


def test_generator_check_mode_reports_no_contract_drift() -> None:
    result = subprocess.run(  # noqa: S603 - fixed interpreter and repository-owned script
        [sys.executable, str(GENERATOR), "--check"],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
