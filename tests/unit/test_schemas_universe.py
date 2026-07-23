"""Universe membership intervals — CI-003 structural probes (LT-016 shape).

canonical_schemas.md §6.3: interval-by-construction, never a snapshot;
backfill from current constituents is impossible because a row *is* an
interval with its own knowledge_time.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from lasr.data.schemas import UNIVERSE_MEMBERSHIP_INTERVALS, UniverseMembershipRow

pytestmark = pytest.mark.unit

KT = datetime(2012, 6, 22, 21, 0, tzinfo=UTC)


def _member(**overrides: Any) -> UniverseMembershipRow:
    base: dict[str, Any] = {
        "universe_id": "russell3000",
        "security_id": "SEC-000001",
        "valid_from": date(2012, 6, 25),
        "valid_to": None,
        "knowledge_time": KT,
        "membership_basis": "index_vendor",
    }
    base.update(overrides)
    return UniverseMembershipRow(**base)


class TestCi003Structure:
    def test_valid_open_interval(self) -> None:
        assert _member().valid_to is None

    def test_closed_interval(self) -> None:
        row = _member(valid_to=date(2013, 6, 28))
        assert row.valid_to == date(2013, 6, 28)

    def test_ci003_inverted_interval_rejected(self) -> None:
        with pytest.raises(ValidationError, match="CI-003"):
            _member(valid_to=date(2012, 6, 24))

    def test_snapshot_shape_impossible_by_construction(self) -> None:
        """CI-003: a membership row without an interval start cannot exist."""
        payload = dict(_member().model_dump())
        del payload["valid_from"]
        with pytest.raises(ValidationError):
            UniverseMembershipRow(**payload)

    def test_membership_requires_knowledge_time(self) -> None:
        """U1: backfilled memberships still carry when-we-knew stamps."""
        payload = dict(_member().model_dump())
        payload["knowledge_time"] = None
        with pytest.raises(ValidationError):
            UniverseMembershipRow(**payload)

    def test_screen_rule_basis_first_class(self) -> None:
        """p4_msci_liquid screen writes the same table (OQ-P4-01/A-G011-48)."""
        row = _member(universe_id="msci_world_liquid80", membership_basis="screen_rule")
        assert row.membership_basis == "screen_rule"

    def test_unknown_basis_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _member(membership_basis="assumed")

    def test_schema_is_interval_keyed(self) -> None:
        assert UNIVERSE_MEMBERSHIP_INTERVALS.primary_key == (
            "universe_id",
            "security_id",
            "valid_from",
        )
