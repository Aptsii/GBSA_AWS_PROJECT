from __future__ import annotations

import logging
from collections.abc import Mapping

from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import OpaqueId


class InvitationEmailHandler:
    def __init__(self, *, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger(__name__)

    def handle(self, event: Mapping[str, object]) -> dict[str, str]:
        event_id = OpaqueId(str(event.get("event_id", "")))
        company_id = OpaqueId(str(event.get("company_id", "")))
        payload = event.get("payload")
        if not isinstance(payload, Mapping):
            raise SafeApplicationError(ErrorCode.INVALID_REQUEST)
        invitation_id = OpaqueId(str(payload.get("invitation_id", "")))
        link_resolution_id = OpaqueId(str(payload.get("link_resolution_id", "")))
        self._logger.info(
            "invitation_email_queued event_id=%s company_id=%s "
            "invitation_id=%s link_resolution_id=%s",
            event_id,
            company_id,
            invitation_id,
            link_resolution_id,
        )
        return {
            "event_id": str(event_id),
            "invitation_id": str(invitation_id),
            "status": "queued",
        }
