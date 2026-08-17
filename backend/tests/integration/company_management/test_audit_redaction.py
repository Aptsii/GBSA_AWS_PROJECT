from __future__ import annotations

import json
import logging

from interview_evidence.company_management.api.company_routes import safe_audit_projection
from interview_evidence.company_management.workers.invitation_email import (
    InvitationEmailHandler,
)


def test_protected_values_are_removed_from_audit_projection() -> None:
    projection = safe_audit_projection(
        {
            "company_id": "0198b6c5-8800-7000-8000-000000000001",
            "invitation_id": "0198b6c5-8800-7000-8000-000000000007",
            "email": "candidate@example.com",
            "raw_token": "raw-secret-token",
            "signed_url": "https://example.com/private?signature=secret",
            "result": "accepted",
        }
    )

    rendered = json.dumps(projection)
    assert projection == {
        "company_id": "0198b6c5-8800-7000-8000-000000000001",
        "invitation_id": "0198b6c5-8800-7000-8000-000000000007",
        "result": "accepted",
    }
    assert "candidate@example.com" not in rendered
    assert "raw-secret-token" not in rendered
    assert "signature=secret" not in rendered


def test_invitation_email_worker_never_logs_recipient_or_token(caplog: object) -> None:
    logger = logging.getLogger("test.invitation-email")
    handler = InvitationEmailHandler(logger=logger)
    event = {
        "event_id": "0198b6c5-8800-7000-8000-000000000011",
        "company_id": "0198b6c5-8800-7000-8000-000000000001",
        "payload": {
            "invitation_id": "0198b6c5-8800-7000-8000-000000000007",
            "email": "candidate@example.com",
            "raw_token": "raw-secret-token",
            "link_resolution_id": "0198b6c5-8800-7000-8000-000000000012",
        },
    }

    with caplog.at_level(logging.INFO, logger=logger.name):  # type: ignore[attr-defined]
        receipt = handler.handle(event)

    rendered = caplog.text  # type: ignore[attr-defined]
    assert receipt["status"] == "queued"
    assert "candidate@example.com" not in rendered
    assert "raw-secret-token" not in rendered
