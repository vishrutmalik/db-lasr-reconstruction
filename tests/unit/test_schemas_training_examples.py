"""CI-018 training-example schema probes (canonical_schemas.md §10).

Binds: CI-018 (every audit field non-null — a schema test rejects rows
missing any field), CI-001 (max_feature_knowledge_time bound), CI-012
(timing-chain field relations), CI-015 (purge-status vocabulary incl. the
recorded ``overlap_permitted`` mode), CI-016 (label domain).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from lasr.data.schemas import TRAINING_EXAMPLES, TrainingExampleRow

pytestmark = pytest.mark.unit

AS_OF = datetime(2012, 4, 30, 21, 0, tzinfo=UTC)

#: CI-018's non-null list: these fields must be present and non-null on
#: every persisted example (nullable by design: target_transformed, label,
#: vol_window_spec, eligibility_reason).
REQUIRED_FIELDS = (
    "config_hash",
    "security_id",
    "as_of",
    "feature_observation_time",
    "knowledge_cutoff",
    "max_feature_knowledge_time",
    "decision_time",
    "execution_time",
    "target_start",
    "target_end",
    "target_raw",
    "comparison_group_id",
    "universe_id",
    "in_universe",
    "eligible",
    "sample_window_tags",
    "purge_status",
)


def _payload(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "config_hash": "cfg-6a3f",
        "security_id": "SEC-000001",
        "as_of": AS_OF,
        "feature_observation_time": AS_OF - timedelta(days=1),
        "knowledge_cutoff": AS_OF,
        "max_feature_knowledge_time": AS_OF - timedelta(hours=3),
        "decision_time": AS_OF,
        "execution_time": AS_OF,  # same_close mode: execution == decision
        "target_start": AS_OF,
        "target_end": AS_OF + timedelta(days=31),
        "target_raw": 0.0123,
        "target_transformed": None,
        "label": 1,
        "comparison_group_id": "universe:russell3000",
        "vol_window_spec": None,
        "universe_id": "russell3000",
        "in_universe": True,
        "eligible": True,
        "eligibility_reason": None,
        "sample_window_tags": ("trailing_12m", "seasonal_apr"),
        "purge_status": "clean",
    }
    base.update(overrides)
    return base


def _row(**overrides: Any) -> TrainingExampleRow:
    return TrainingExampleRow(**_payload(**overrides))


class TestCi018Completeness:
    def test_valid_row_constructs(self) -> None:
        assert _row().purge_status == "clean"

    @pytest.mark.parametrize("field", REQUIRED_FIELDS)
    def test_ci018_missing_field_rejected(self, field: str) -> None:
        payload = _payload()
        del payload[field]
        with pytest.raises(ValidationError):
            TrainingExampleRow(**payload)

    @pytest.mark.parametrize("field", REQUIRED_FIELDS)
    def test_ci018_null_field_rejected(self, field: str) -> None:
        with pytest.raises(ValidationError):
            _row(**{field: None})

    def test_schema_and_row_model_agree_on_required_set(self) -> None:
        required = tuple(c.name for c in TRAINING_EXAMPLES.columns if not c.nullable)
        assert required == REQUIRED_FIELDS


class TestAuditRelations:
    def test_ci001_feature_knowledge_beyond_cutoff_rejected(self) -> None:
        with pytest.raises(ValidationError, match="CI-001"):
            _row(max_feature_knowledge_time=AS_OF + timedelta(seconds=1))

    def test_knowledge_cutoff_must_equal_as_of(self) -> None:
        with pytest.raises(ValidationError, match="as_of"):
            _row(knowledge_cutoff=AS_OF - timedelta(hours=1))

    def test_ci012_feature_after_cutoff_rejected(self) -> None:
        with pytest.raises(ValidationError, match="CI-012"):
            _row(feature_observation_time=AS_OF + timedelta(days=1))

    def test_ci012_execution_must_equal_target_start(self) -> None:
        with pytest.raises(ValidationError, match="CI-012"):
            _row(execution_time=AS_OF + timedelta(days=1))

    def test_ci012_empty_target_window_rejected(self) -> None:
        with pytest.raises(ValidationError, match="CI-012"):
            _row(target_end=AS_OF)

    def test_delayed_execution_expressible(self) -> None:
        """CR-018 one_day_lag: execution (and target window) shift together."""
        start = AS_OF + timedelta(days=1)
        row = _row(
            execution_time=start,
            target_start=start,
            target_end=start + timedelta(days=31),
        )
        assert row.execution_time == row.target_start


class TestLabelDomain:
    def test_ci016_labels_plus_minus_one_or_excluded(self) -> None:
        assert _row(label=1).label == 1
        assert _row(label=-1).label == -1
        assert _row(label=None).label is None  # middle 40%: null, excluded

    @pytest.mark.parametrize("bad", [0, 2, -2])
    def test_ci016_out_of_domain_label_rejected(self, bad: int) -> None:
        with pytest.raises(ValidationError):
            _row(label=bad)


class TestPurgeStatus:
    def test_ci015_overlap_permitted_is_recorded_config(self) -> None:
        """OQ-P4-06/A-G011-38: permitted overlap is recorded, not implicit."""
        assert _row(purge_status="overlap_permitted").purge_status == (
            "overlap_permitted"
        )

    def test_unknown_purge_status_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _row(purge_status="ignored")
