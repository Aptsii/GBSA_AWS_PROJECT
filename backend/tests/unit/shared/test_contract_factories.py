from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from tests.fixtures.shared.factories import (
    COMPANY_ID,
    CRITERION_ID,
    OTHER_COMPANY_ID,
    make_criterion_snapshot,
    make_invitation_snapshot,
    make_other_tenant_context,
    make_report_snapshot,
    make_session_snapshot,
    make_strategy_snapshot,
    make_tenant_context,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
SCHEMA_BUNDLE = REPOSITORY_ROOT / "packages" / "contracts" / "generated" / "schema-bundle.json"
Factory = Callable[[], dict[str, Any]]


def _validator(definition: str) -> Draft202012Validator:
    if definition == "TenantContext":
        common_path = REPOSITORY_ROOT / "packages" / "contracts" / "modules" / "v1" / "common.json"
        common: dict[str, Any] = json.loads(common_path.read_text(encoding="utf-8"))
        definitions = common["$defs"]
    else:
        bundle: dict[str, Any] = json.loads(SCHEMA_BUNDLE.read_text(encoding="utf-8"))
        definitions = bundle["$defs"]
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$ref": f"#/$defs/{definition}",
        "$defs": definitions,
    }
    return Draft202012Validator(schema, format_checker=FormatChecker())


@pytest.mark.parametrize(
    ("definition", "factory"),
    [
        ("TenantContext", make_tenant_context),
        ("CriterionVersionSnapshot", make_criterion_snapshot),
        ("InvitationAuthorizationSnapshot", make_invitation_snapshot),
        ("StrategySnapshot", make_strategy_snapshot),
        ("SessionSnapshot", make_session_snapshot),
        ("ReportSnapshot", make_report_snapshot),
    ],
)
def test_each_factory_conforms_to_the_frozen_module_schema(
    definition: str, factory: Factory
) -> None:
    _validator(definition).validate(factory())


def test_factories_are_deterministic_and_tenant_consistent() -> None:
    snapshots = [
        make_criterion_snapshot(),
        make_invitation_snapshot(),
        make_strategy_snapshot(),
        make_session_snapshot(),
        make_report_snapshot(),
    ]

    assert make_tenant_context() == make_tenant_context()
    assert all(snapshot["company_id"] == COMPANY_ID for snapshot in snapshots)
    assert make_report_snapshot()["items"][0]["criterion_id"] == CRITERION_ID


def test_wrong_tenant_fixture_is_explicit_and_disjoint() -> None:
    own = make_tenant_context()
    other = make_other_tenant_context()

    assert own["company_id"] == COMPANY_ID
    assert other["company_id"] == OTHER_COMPANY_ID
    assert own["company_id"] != other["company_id"]
    assert own["actor_id"] != other["actor_id"]


def test_report_fixture_never_confirms_without_final_answer_evidence() -> None:
    report = make_report_snapshot()
    confirmed_items = {"confirmed", "partially_confirmed"}

    for item in report["items"]:
        if item["assessment_state"] in confirmed_items:
            assert item["evidence"]
            for evidence in item["evidence"]:
                assert evidence["answer_turn_status"] == "final"
                assert evidence["answer_turn_speaker"] == "applicant"
                assert evidence["evidence_type"] == "applicant_answer"
                assert evidence["transcript_segment_id"]
                assert evidence["video_end_ms"] > evidence["video_start_ms"]
                assert evidence["technical_failure_overlap"] is False
                assert "source_reference_id" not in evidence
