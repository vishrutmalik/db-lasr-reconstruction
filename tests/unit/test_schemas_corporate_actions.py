"""Corporate-action typed events (canonical_schemas.md §5).

Binds CI-049 (single terminal-return home, typed discontinuity
explanations — LT-018) and the documented U3 pre-announcement exception.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from lasr.data.schemas import (
    DELISTING_RETURN_AUTHORITATIVE_HOME,
    CorporateActionRow,
)

pytestmark = pytest.mark.unit

ANNOUNCED = datetime(2012, 1, 10, 14, 0, tzinfo=UTC)


def _action(**overrides: Any) -> CorporateActionRow:
    base: dict[str, Any] = {
        "action_id": "ACT-1",
        "security_id": "SEC-000001",
        "action_type": "split",
        "announcement_time": ANNOUNCED,
        "ex_date": date(2012, 2, 1),
        "effective_date": date(2012, 2, 1),
        "ratio_num": 2.0,
        "ratio_den": 1.0,
        "amount": None,
        "currency": None,
        "successor_security_id": None,
        "terminal_return": None,
    }
    base.update(overrides)
    return CorporateActionRow(**base)


class TestTypedEvents:
    def test_two_for_one_split(self) -> None:
        """CI-049 doc case: a 2:1 split is ratio 2/1 feeding adjustment_factors."""
        row = _action()
        assert (row.ratio_num, row.ratio_den) == (2.0, 1.0)

    def test_u3_exception_announcement_precedes_effective(self) -> None:
        row = _action()
        assert row.announcement_time.date() < row.effective_date

    @pytest.mark.parametrize("kind", ["split", "stock_dividend", "rights_issue"])
    def test_ratio_types_require_ratio(self, kind: str) -> None:
        with pytest.raises(ValidationError, match="ratio"):
            _action(action_type=kind, ratio_num=None, ratio_den=None)

    def test_cash_dividend_requires_amount_and_currency(self) -> None:
        row = _action(
            action_type="cash_dividend",
            ratio_num=None,
            ratio_den=None,
            amount=0.25,
            currency="USD",
        )
        assert row.amount == 0.25
        with pytest.raises(ValidationError, match="cash_dividend"):
            _action(
                action_type="cash_dividend",
                ratio_num=None,
                ratio_den=None,
                amount=None,
                currency=None,
            )

    def test_delisting_carries_terminal_return(self) -> None:
        """LT-009 delisting path: return realized exactly once, here."""
        row = _action(
            action_type="delisting",
            ratio_num=None,
            ratio_den=None,
            terminal_return=-0.35,
        )
        assert row.terminal_return == -0.35

    def test_merger_carries_terminal_return_and_successor(self) -> None:
        row = _action(
            action_type="merger",
            ratio_num=None,
            ratio_den=None,
            successor_security_id="SEC-000099",
            terminal_return=0.12,
        )
        assert row.successor_security_id == "SEC-000099"

    def test_ci049_terminal_return_on_wrong_type_rejected(self) -> None:
        """Single-home rule: no terminal return outside delisting/merger."""
        with pytest.raises(ValidationError, match="CI-049"):
            _action(terminal_return=0.1)  # on a split

    def test_successor_on_wrong_type_rejected(self) -> None:
        with pytest.raises(ValidationError, match="successor"):
            _action(
                action_type="cash_dividend",
                ratio_num=None,
                ratio_den=None,
                amount=0.25,
                currency="USD",
                successor_security_id="SEC-000099",
            )

    def test_terminal_return_below_total_loss_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _action(
                action_type="delisting",
                ratio_num=None,
                ratio_den=None,
                terminal_return=-1.01,
            )

    def test_zero_ratio_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _action(ratio_den=0.0)

    def test_n2_authoritative_home_constant(self) -> None:
        assert DELISTING_RETURN_AUTHORITATIVE_HOME == (
            "corporate_actions",
            "terminal_return",
        )
