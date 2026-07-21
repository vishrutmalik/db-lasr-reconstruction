"""Security master row models (canonical_schemas.md §1; CI-003/CI-049 edges)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from lasr.data.schemas import IdentifierMapRow, ListingIntervalRow, SecurityRow

pytestmark = pytest.mark.unit

KT = datetime(2012, 1, 31, 21, 0, tzinfo=UTC)


def _listing(**overrides: Any) -> ListingIntervalRow:
    base: dict[str, Any] = {
        "security_id": "SEC-000001",
        "exchange": "XNYS",
        "mic": None,
        "country": "US",
        "trading_currency": "USD",
        "listing_date": date(1990, 1, 2),
        "delisting_date": None,
        "delisting_return": None,
        "is_primary": True,
        "knowledge_time": KT,
    }
    base.update(overrides)
    return ListingIntervalRow(**base)


class TestSecurityRow:
    def test_valid_row(self) -> None:
        row = SecurityRow(
            security_id="SEC-000001",
            issuer_id="ISS-1",
            security_type="common",
            share_class=None,  # FM-07 ambiguity — nullable
            first_knowledge_time=KT,
        )
        assert row.security_type == "common"

    def test_unknown_security_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SecurityRow(
                security_id="SEC-000001",
                issuer_id="ISS-1",
                security_type="preferred",  # not in the §1.1 closed set
                first_knowledge_time=KT,
            )

    def test_extra_field_rejected(self) -> None:
        """MP §26: unknown keys are errors, never silently ignored."""
        with pytest.raises(ValidationError, match="extra"):
            SecurityRow(
                security_id="SEC-000001",
                issuer_id="ISS-1",
                security_type="common",
                first_knowledge_time=KT,
                isin="US0000000000",  # no identifier fields on the spine
            )

    def test_naive_knowledge_time_rejected(self) -> None:
        with pytest.raises(ValidationError, match="naive"):
            SecurityRow(
                security_id="SEC-000001",
                issuer_id="ISS-1",
                security_type="common",
                first_knowledge_time=datetime(2012, 1, 31, 21, 0),
            )


class TestIdentifierMapRow:
    def test_symbol_change_intervals(self) -> None:
        """LT-018 fixture shape: one interval closes, another opens."""
        old = IdentifierMapRow(
            security_id="SEC-000001",
            id_scheme="ticker",
            id_value="OLD",
            valid_from=date(1990, 1, 2),
            valid_to=date(2005, 6, 30),
            knowledge_time=KT,
        )
        new = IdentifierMapRow(
            security_id="SEC-000001",
            id_scheme="ticker",
            id_value="NEW",
            valid_from=date(2005, 7, 1),
            valid_to=None,
            knowledge_time=KT,
        )
        assert old.security_id == new.security_id  # position identity preserved

    def test_inverted_interval_rejected(self) -> None:
        with pytest.raises(ValidationError, match="precedes"):
            IdentifierMapRow(
                security_id="SEC-000001",
                id_scheme="ticker",
                id_value="X",
                valid_from=date(2005, 7, 1),
                valid_to=date(2005, 6, 30),
                knowledge_time=KT,
            )


class TestListingIntervalRow:
    def test_still_listed_row(self) -> None:
        assert _listing().delisting_date is None

    def test_delisted_row_with_derived_return(self) -> None:
        row = _listing(delisting_date=date(2001, 9, 28), delisting_return=-0.35)
        assert row.delisting_return == -0.35

    def test_ci003_delisting_before_listing_rejected(self) -> None:
        with pytest.raises(ValidationError, match="CI-003"):
            _listing(delisting_date=date(1989, 12, 29))

    def test_ci049_return_without_delisting_rejected(self) -> None:
        """The derived delisting_return view only exists at delisting."""
        with pytest.raises(ValidationError, match="CI-049"):
            _listing(delisting_return=-0.5)

    def test_return_below_total_loss_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _listing(delisting_date=date(2001, 9, 28), delisting_return=-1.5)

    def test_non_iso4217_currency_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _listing(trading_currency="usd")
