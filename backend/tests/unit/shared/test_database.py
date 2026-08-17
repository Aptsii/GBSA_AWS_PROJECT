from __future__ import annotations

from interview_evidence.shared.database import Base, metadata


def test_all_lane_models_share_one_named_metadata_registry() -> None:
    assert Base.metadata is metadata
    assert metadata.naming_convention == {
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
