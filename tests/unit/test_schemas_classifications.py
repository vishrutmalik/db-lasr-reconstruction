"""Classification intervals + derived exposures (canonical_schemas.md §6.1/§6.2).

Binds CI-017 (as-of interval substrate), CR-015 (version-keyed region
schemes), CI-004 (window-end knowledge time on derived exposures).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from lasr.data.schemas import ClassificationIntervalRow, DerivedExposureRow

pytestmark = pytest.mark.unit

KT = datetime(2018, 9, 28, 21, 0, tzinfo=UTC)


def _classification(**overrides: Any) -> ClassificationIntervalRow:
    base: dict[str, Any] = {
        "security_id": "SEC-000001",
        "scheme": "gics_l1",
        "value": "45",
        "valid_from": date(2010, 1, 1),
        "valid_to": None,
        "knowledge_time": KT,
    }
    base.update(overrides)
    return ClassificationIntervalRow(**base)


def _exposure(**overrides: Any) -> DerivedExposureRow:
    base: dict[str, Any] = {
        "security_id": "SEC-000001",
        "event_date": date(2018, 9, 28),
        "knowledge_time": KT,
        "measure": "beta_3y_w",
        "value": 1.12,
        "market_proxy_id": "capweight_universe_mean",  # FM-22 proxy, recorded
        "window_spec": "156w",
    }
    base.update(overrides)
    return DerivedExposureRow(**base)


class TestClassificationIntervalRow:
    def test_gics_transition_expressible(self) -> None:
        """OQ-P4-17/A-G011-51: the 2018 GICS 10->11 change is two intervals."""
        before = _classification(valid_to=date(2018, 9, 28))
        after = _classification(value="50", valid_from=date(2018, 9, 29))
        assert before.valid_to is not None
        assert after.valid_from > before.valid_from

    def test_cr015_version_keyed_region_schemes_accepted(self) -> None:
        for scheme in ("region_p2", "region_p3", "region_p4"):
            assert _classification(scheme=scheme, value="AxJ").scheme == scheme

    def test_unknown_scheme_rejected(self) -> None:
        """CR-015: no shared/unversioned region scheme exists."""
        with pytest.raises(ValidationError):
            _classification(scheme="region")

    def test_inverted_interval_rejected(self) -> None:
        with pytest.raises(ValidationError, match="precedes"):
            _classification(valid_to=date(2009, 12, 31))


class TestDerivedExposureRow:
    def test_valid_exposure(self) -> None:
        assert _exposure().measure == "beta_3y_w"

    def test_version_required_measures(self) -> None:
        """E-P2-12 / E-P4-08 / nlasr_2020 §10 measure set."""
        for measure in ("beta_1y_d", "beta_3y_w", "vol_260w", "size_mcap"):
            assert _exposure(measure=measure).measure == measure
        with pytest.raises(ValidationError):
            _exposure(measure="beta_5y_m")

    def test_ci004_knowledge_before_window_end_rejected(self) -> None:
        with pytest.raises(ValidationError, match="CI-004"):
            _exposure(knowledge_time=datetime(2018, 9, 27, 21, 0, tzinfo=UTC))

    def test_missing_window_spec_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _exposure(window_spec="")
