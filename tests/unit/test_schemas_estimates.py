"""Estimates/consensus rows: vintaged revisions (canonical_schemas.md §4).

Binds CI-002 for revisions (LT-010 pattern applied to estimates).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from lasr.core import SchemaValidationError
from lasr.data.schemas import (
    ESTIMATES_CONSENSUS,
    EstimateConsensusRow,
    validate_rows,
)

pytestmark = pytest.mark.unit

KT0 = datetime(2012, 1, 10, 12, 0, tzinfo=UTC)
KT1 = datetime(2012, 2, 20, 12, 0, tzinfo=UTC)


def _row(**overrides: Any) -> EstimateConsensusRow:
    base: dict[str, Any] = {
        "security_id": "SEC-000001",
        "metric": "EPS",
        "forecast_period": "FY+1",
        "stat": "mean",
        "value": 2.35,
        "knowledge_time": KT0,
        "vintage_seq": 0,
        "n_contributors": None,
    }
    base.update(overrides)
    return EstimateConsensusRow(**base)


class TestEstimateConsensusRow:
    def test_valid_consensus_row(self) -> None:
        assert _row().stat == "mean"

    def test_price_target_reuses_table(self) -> None:
        """§4: rating/target-price snapshots use metric keys, not new tables."""
        row = _row(metric="price_target", n_contributors=14)
        assert row.n_contributors == 14

    def test_unknown_stat_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _row(stat="mode")

    def test_negative_vintage_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _row(vintage_seq=-1)

    def test_negative_contributors_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _row(n_contributors=-1)

    def test_naive_knowledge_time_rejected(self) -> None:
        with pytest.raises(ValidationError, match="naive"):
            _row(knowledge_time=datetime(2012, 1, 10, 12, 0))


class TestRevisionBatchRules:
    def test_revision_is_new_vintage_with_later_knowledge(self) -> None:
        rows = [
            dict(_row().model_dump()),
            dict(_row(vintage_seq=1, knowledge_time=KT1, value=2.5).model_dump()),
        ]
        validate_rows(ESTIMATES_CONSENSUS, rows)  # must not raise

    def test_u2_revision_with_earlier_knowledge_rejected(self) -> None:
        rows = [
            dict(_row(knowledge_time=KT1).model_dump()),
            dict(_row(vintage_seq=1, knowledge_time=KT0).model_dump()),
        ]
        with pytest.raises(SchemaValidationError, match="CI-002"):
            validate_rows(ESTIMATES_CONSENSUS, rows)
