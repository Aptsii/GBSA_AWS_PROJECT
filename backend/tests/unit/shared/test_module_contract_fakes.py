from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.tenant import TenantContext, TenantScopeViolation
from jsonschema import Draft202012Validator, FormatChecker

from tests.fixtures.shared.factories import (
    COMPANY_ID,
    make_other_tenant_context,
    make_tenant_context,
)
from tests.fixtures.shared.module_fakes import (
    DeterministicModuleFakes,
    FakeFailureMode,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
MODULE_ROOT = REPOSITORY_ROOT / "packages" / "contracts" / "modules" / "v1"
CATALOG_PATH = MODULE_ROOT / "catalog.json"
SCHEMA_BUNDLE = REPOSITORY_ROOT / "packages" / "contracts" / "generated" / "schema-bundle.json"


def _context(factory: Any = make_tenant_context) -> TenantContext:
    return TenantContext(**factory())


def _catalog() -> dict[str, Any]:
    value: dict[str, Any] = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    return value


def _validator(definition: str) -> Draft202012Validator:
    bundle: dict[str, Any] = json.loads(SCHEMA_BUNDLE.read_text(encoding="utf-8"))
    return Draft202012Validator(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$ref": f"#/$defs/{definition}",
            "$defs": bundle["$defs"],
        },
        format_checker=FormatChecker(),
    )


def test_fake_covers_every_catalog_interface_with_schema_conforming_output() -> None:
    fake = DeterministicModuleFakes(company_id=COMPANY_ID)
    context = _context()
    catalog = _catalog()
    expected_interfaces = {
        interface for snapshot in catalog["snapshots"] for interface in snapshot["interfaces"]
    }

    assert fake.interfaces == expected_interfaces
    for snapshot in catalog["snapshots"]:
        for interface in snapshot["interfaces"]:
            result = getattr(fake, interface)(context, opaque_input="foundation-fixture")
            _validator(snapshot["name"]).validate(result)
            assert result["company_id"] == COMPANY_ID


def test_fake_returns_defensive_deterministic_copies() -> None:
    fake = DeterministicModuleFakes(company_id=COMPANY_ID)
    context = _context()

    first = fake.get_campaign_snapshot(context, campaign_id="campaign-foundation")
    second = fake.get_campaign_snapshot(context, campaign_id="campaign-foundation")
    assert first == second
    assert first is not second

    first["company_id"] = "changed-by-consumer"
    assert (
        fake.get_campaign_snapshot(context, campaign_id="campaign-foundation")["company_id"]
        == COMPANY_ID
    )


def test_fake_denies_wrong_tenant_before_configured_failure() -> None:
    fake = DeterministicModuleFakes(
        company_id=COMPANY_ID,
        failures={"get_campaign_snapshot": FakeFailureMode.NOT_FOUND},
    )

    with pytest.raises(TenantScopeViolation):
        fake.get_campaign_snapshot(
            _context(make_other_tenant_context), campaign_id="campaign-foundation"
        )


@pytest.mark.parametrize(
    ("mode", "expected_code"),
    [
        (FakeFailureMode.NOT_FOUND, ErrorCode.RESOURCE_NOT_FOUND),
        (FakeFailureMode.RETRYABLE, ErrorCode.DEPENDENCY_UNAVAILABLE),
        (FakeFailureMode.NON_RETRYABLE, ErrorCode.INTERNAL_ERROR),
    ],
)
def test_fake_supports_catalog_safe_failure_modes(
    mode: FakeFailureMode, expected_code: ErrorCode
) -> None:
    fake = DeterministicModuleFakes(
        company_id=COMPANY_ID,
        failures={"get_campaign_snapshot": mode},
    )

    with pytest.raises(SafeApplicationError) as caught:
        fake.get_campaign_snapshot(_context(), campaign_id="campaign-foundation")

    assert caught.value.code is expected_code
    assert "campaign-foundation" not in str(caught.value)


def test_fake_replays_same_idempotent_call_and_rejects_changed_request() -> None:
    fake = DeterministicModuleFakes(company_id=COMPANY_ID)
    context = _context()

    first = fake.advance_invitation_state(
        context,
        invitation_id="invitation-foundation",
        to_state="opened",
        idempotency_key="client-key-foundation",
    )
    replay = fake.advance_invitation_state(
        context,
        invitation_id="invitation-foundation",
        to_state="opened",
        idempotency_key="client-key-foundation",
    )
    assert replay == first

    with pytest.raises(SafeApplicationError) as caught:
        fake.advance_invitation_state(
            context,
            invitation_id="invitation-foundation",
            to_state="consented",
            idempotency_key="client-key-foundation",
        )

    assert caught.value.code is ErrorCode.IDEMPOTENCY_CONFLICT
    assert "client-key-foundation" not in repr(fake)
