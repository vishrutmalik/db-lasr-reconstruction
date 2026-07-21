"""Fundamentals rows: U2/U3 vintage discipline (canonical_schemas.md §3).

Binds CI-002 (vintage substrate), CI-005 (knowledge_basis auditability),
LT-010 (restatement pattern), LT-021 (inverted-timestamp quarantine seed).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from lasr.core import SchemaValidationError
from lasr.data.schemas import FUNDAMENTALS, FundamentalRow, validate_rows

pytestmark = pytest.mark.unit

PERIOD_END = date(2011, 12, 31)
KT0 = datetime(2012, 2, 15, 12, 0, tzinfo=UTC)
KT1 = datetime(2012, 5, 10, 12, 0, tzinfo=UTC)


def _row(**overrides: Any) -> FundamentalRow:
    base: dict[str, Any] = {
        "security_id": "SEC-000001",
        "metric": "net_income",
        "fiscal_period": "FY2011",
        "period_end": PERIOD_END,
        "report_date": date(2012, 2, 15),
        "knowledge_time": KT0,
        "knowledge_basis": "published",
        "ingestion_time": KT0,
        "vintage_seq": 0,
        "value": 123.4,
        "unit": "millions",
        "currency": "USD",
        "consolidation_basis": None,
    }
    base.update(overrides)
    return FundamentalRow(**base)


class TestFundamentalRow:
    def test_valid_first_reported_row(self) -> None:
        assert _row().vintage_seq == 0

    def test_lag_rule_basis_expressible(self) -> None:
        """A-002: knowledge = period_end + configured lag, recorded per row."""
        row = _row(
            report_date=None,  # FM-10: provider UNAVAILABLE
            knowledge_basis="lag_rule",
            knowledge_time=datetime(2012, 3, 31, 0, 0, tzinfo=UTC),
        )
        assert row.knowledge_basis == "lag_rule"

    def test_u3_knowledge_before_period_end_rejected(self) -> None:
        """LT-021's inverted-timestamp seed: structurally invalid."""
        with pytest.raises(ValidationError, match="U3"):
            _row(knowledge_time=datetime(2011, 12, 30, 12, 0, tzinfo=UTC))

    def test_u3_report_before_period_end_rejected(self) -> None:
        with pytest.raises(ValidationError, match="U3"):
            _row(report_date=date(2011, 11, 30))

    def test_negative_vintage_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _row(vintage_seq=-1)

    def test_unknown_knowledge_basis_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _row(knowledge_basis="guessed")

    def test_non_iso4217_currency_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _row(currency="US$")


class TestVintageBatchRules:
    def test_lt010_restatement_is_new_vintage_with_later_knowledge(self) -> None:
        rows = [
            dict(_row().model_dump()),
            dict(
                _row(
                    vintage_seq=1, knowledge_time=KT1, ingestion_time=KT1, value=120.0
                ).model_dump()
            ),
        ]
        validate_rows(FUNDAMENTALS, rows)  # must not raise

    def test_u2_restatement_with_earlier_knowledge_rejected(self) -> None:
        """CI-002: knowledge_time strictly increasing in vintage_seq."""
        rows = [
            dict(
                _row(
                    knowledge_time=KT1,
                    ingestion_time=KT1,
                    report_date=date(2012, 5, 10),
                ).model_dump()
            ),
            dict(_row(vintage_seq=1).model_dump()),
        ]
        with pytest.raises(SchemaValidationError, match="CI-002"):
            validate_rows(FUNDAMENTALS, rows)

    def test_u2_duplicate_vintage_rejected(self) -> None:
        rows = [
            dict(_row().model_dump()),
            dict(_row(value=99.0, knowledge_time=KT1).model_dump()),
        ]
        with pytest.raises(SchemaValidationError, match="duplicate"):
            validate_rows(FUNDAMENTALS, rows)
