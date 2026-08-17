from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MODULE_EXAMPLES = REPOSITORY_ROOT / "packages" / "contracts" / "modules" / "v1" / "examples"

COMPANY_ID = "018f2000-0000-7000-8000-000000000100"
OTHER_COMPANY_ID = "018f2000-0000-7000-8000-000000000900"
USER_ID = "018f2000-0000-7000-8000-000000000101"
OTHER_USER_ID = "018f2000-0000-7000-8000-000000000901"
MODEL_ID = "018f2000-0000-7000-8000-000000000202"
CRITERION_ID = "018f2000-0000-7000-8000-000000000203"
INVITATION_ID = "018f2000-0000-7000-8000-000000000210"
APPLICANT_ID = "018f2000-0000-7000-8000-000000000211"
STRATEGY_ID = "018f2000-0000-7000-8000-000000000221"
SESSION_ID = "018f2000-0000-7000-8000-000000000230"
REPORT_ID = "018f2000-0000-7000-8000-000000000240"


def _load_example(name: str) -> dict[str, Any]:
    value: dict[str, Any] = json.loads(
        (MODULE_EXAMPLES / f"{name}.json").read_text(encoding="utf-8")
    )
    return deepcopy(value)


def make_tenant_context() -> dict[str, Any]:
    return {
        "company_id": COMPANY_ID,
        "actor_type": "company_user",
        "actor_id": USER_ID,
        "request_id": "018f2000-0000-7000-8000-000000000102",
        "trace_id": "trace-foundation-0001",
    }


def make_other_tenant_context() -> dict[str, Any]:
    return {
        "company_id": OTHER_COMPANY_ID,
        "actor_type": "company_user",
        "actor_id": OTHER_USER_ID,
        "request_id": "018f2000-0000-7000-8000-000000000902",
        "trace_id": "trace-foundation-9001",
    }


def make_criterion_snapshot() -> dict[str, Any]:
    return _load_example("CriterionVersionSnapshot")


def make_invitation_snapshot() -> dict[str, Any]:
    return _load_example("InvitationAuthorizationSnapshot")


def make_strategy_snapshot() -> dict[str, Any]:
    return _load_example("StrategySnapshot")


def make_session_snapshot() -> dict[str, Any]:
    return _load_example("SessionSnapshot")


def make_report_snapshot() -> dict[str, Any]:
    return _load_example("ReportSnapshot")
