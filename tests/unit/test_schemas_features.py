"""Feature values + MP §18 FeatureSpec registry record (canonical_schemas.md §8/§9).

Binds CI-005 (knowledge >= observation on stored features) and the MP §18
field completeness of the registry record.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from lasr.data.schemas import FeatureSpec, FeatureValueRow

pytestmark = pytest.mark.unit

OBS = datetime(2012, 1, 31, 21, 0, tzinfo=UTC)


def _value_row(**overrides: Any) -> FeatureValueRow:
    base: dict[str, Any] = {
        "feature_id": "earnings_yield",
        "feature_version": 1,
        "security_id": "SEC-000001",
        "observation_time": OBS,
        "knowledge_time": OBS + timedelta(days=1),
        "value": 0.045,
    }
    base.update(overrides)
    return FeatureValueRow(**base)


def _spec(**overrides: Any) -> FeatureSpec:
    base: dict[str, Any] = {
        "feature_id": "earnings_yield",
        "version": 1,
        "category": "value",
        "direction": "higher_is_better",
        "required_fields": ("net_income", "market_cap"),
        "formula": "net_income / market_cap",
        "units": "ratio",
        "frequency": "monthly",
        "min_coverage": 0.6,
        "publication_lag": timedelta(days=1),
        "missing_policy": "exclude",
        "outlier_policy": "none_rank_handles",
        "neutralize": True,
        "monotonicity": "increasing",
        "evidence_source": "P3 Fig 2 row 7",
        "availability": "direct",
        "provenance": "EXPLICIT",
    }
    base.update(overrides)
    return FeatureSpec(**base)


class TestFeatureValueRow:
    def test_valid_row(self) -> None:
        assert _value_row().value == 0.045

    def test_ci005_knowledge_before_observation_rejected(self) -> None:
        """Publication lag can only push knowledge later, never earlier."""
        with pytest.raises(ValidationError, match="CI-005"):
            _value_row(knowledge_time=OBS - timedelta(seconds=1))

    def test_version_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _value_row(feature_version=0)

    def test_pre_neutralization_store_has_no_rank_column(self) -> None:
        """L-FEAT stores pre-rank, pre-neutralization values only
        (system_design.md §2; CR-004/CI-029)."""
        assert set(FeatureValueRow.model_fields) == {
            "feature_id",
            "feature_version",
            "security_id",
            "observation_time",
            "knowledge_time",
            "value",
        }


class TestFeatureSpec:
    def test_mp18_field_list_complete(self) -> None:
        assert tuple(f.name for f in dataclasses.fields(FeatureSpec)) == (
            "feature_id",
            "version",
            "category",
            "direction",
            "required_fields",
            "formula",
            "units",
            "frequency",
            "min_coverage",
            "publication_lag",
            "missing_policy",
            "outlier_policy",
            "neutralize",
            "monotonicity",
            "evidence_source",
            "availability",
            "provenance",
        )

    def test_valid_spec_constructs_and_is_frozen(self) -> None:
        spec = _spec()
        with pytest.raises(dataclasses.FrozenInstanceError):
            spec.version = 2  # type: ignore[misc]

    def test_min_coverage_out_of_range_rejected(self) -> None:
        with pytest.raises(ValueError, match="min_coverage"):
            _spec(min_coverage=1.5)

    def test_negative_publication_lag_rejected(self) -> None:
        with pytest.raises(ValueError, match="publication_lag"):
            _spec(publication_lag=timedelta(days=-1))

    def test_undocumented_formula_rejected(self) -> None:
        with pytest.raises(ValueError, match="formula"):
            _spec(formula="")

    def test_missing_evidence_source_rejected(self) -> None:
        with pytest.raises(ValueError, match="evidence_source"):
            _spec(evidence_source="")

    def test_ci028_technical_exemption_flag_expressible(self) -> None:
        spec = _spec(
            feature_id="price_momentum_12m",
            category="technical",
            neutralize=False,  # CI-028 exemption bit
            provenance="INFERRED",
        )
        assert spec.neutralize is False

    def test_roundtrip_via_asdict(self) -> None:
        spec = _spec()
        assert FeatureSpec(**dataclasses.asdict(spec)) == spec
