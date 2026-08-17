"""Public event-handler composition surface for company management."""

from __future__ import annotations

from interview_evidence.company_management.workers.invitation_email import (
    InvitationEmailHandler,
)


def create_invitation_email_handler() -> InvitationEmailHandler:
    return InvitationEmailHandler()
