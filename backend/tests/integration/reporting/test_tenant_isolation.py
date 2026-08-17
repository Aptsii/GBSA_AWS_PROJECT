from __future__ import annotations

import pytest
from interview_evidence.reporting.adapters.playback import PlaybackLocator
from interview_evidence.shared.tenant import TenantContext, TenantScopeViolation

from tests.fixtures.shared.factories import COMPANY_ID, OTHER_COMPANY_ID, make_other_tenant_context


def test_cross_tenant_media_locator_is_denied() -> None:
    with pytest.raises(TenantScopeViolation):
        PlaybackLocator().issue(
            TenantContext(**make_other_tenant_context()),
            company_id=COMPANY_ID,
            recording_asset_id="018f2000-0000-7000-8000-000000000254",
        )
    assert COMPANY_ID != OTHER_COMPANY_ID
