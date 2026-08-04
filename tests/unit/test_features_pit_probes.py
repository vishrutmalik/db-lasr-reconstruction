"""PIT probes for the audited library (G022) — CI-004 append-future
invariance, CI-001 stored-row bounds, CI-042/CI-043 determinism.

The headline probe (CI-004 metamorphic / LT-019 shape): compute every
library feature at ``as_of`` over dataset A (history only), then over
dataset B = A plus

- price bars after ``as_of`` (absurd values),
- a late-arriving bar (event before ``as_of``, knowledge after),
- fundamental restatements + new fiscal-year statements knowable after
  ``as_of``,
- a new consensus vintage knowable after ``as_of``,

and require the stored rows to be BIT-IDENTICAL (values, observation and
knowledge stamps). Teeth: at a later ``as_of`` the added data must change
the answers — the probe cannot pass vacuously.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from test_features_fixtures import (
    AS_OF,
    build_engine_pair,
    estimate,
    fundamental,
    price_bar,
)

from lasr.data.schemas.base import Row
from lasr.features.engine import FeatureEngine
from lasr.features.library import (
    AUDITED_LIBRARY_LIST_ID,
    build_default_registry,
    library_feature_keys,
)

pytestmark = pytest.mark.unit

UNIVERSE = ("SEC-A", "SEC-B")
K_FY2019 = datetime(2020, 3, 31, 12, 0, tzinfo=UTC)
K_FY2020 = datetime(2021, 3, 31, 12, 0, tzinfo=UTC)
LATER_AS_OF = datetime(2022, 1, 15, 12, 0, tzinfo=UTC)


def _base_prices() -> list[Row]:
    """Full coverage for every price feature: a 12M-old base bar plus 20
    daily bars 2021-12-01..2021-12-20 (>=10 vol returns; >=5 ADV obs in
    [12-11, 12-31]; momentum recent/base lookups within staleness)."""
    bars: list[Row] = [
        price_bar(
            "SEC-A", date(2020, 12, 28), close=80.0, volume=800.0, market_cap=4000.0
        ),
        price_bar(
            "SEC-B", date(2020, 12, 28), close=40.0, volume=400.0, market_cap=2000.0
        ),
    ]
    for i in range(20):
        day = date(2021, 12, 1) + timedelta(days=i)
        bars.append(
            price_bar(
                "SEC-A",
                day,
                close=100.0 + i,
                volume=1000.0 + i,
                market_cap=5000.0 + 10 * i,
            )
        )
        bars.append(
            price_bar(
                "SEC-B",
                day,
                close=50.0 + 2 * i,
                volume=500.0 + i,
                market_cap=3000.0 + 5 * i,
            )
        )
    return bars


def _base_fundamentals() -> list[Row]:
    rows: list[Row] = []
    for sid, bv, ta, eps in (
        ("SEC-A", (400.0, 500.0), (800.0, 1000.0), 5.0),
        ("SEC-B", (200.0, 260.0), (600.0, 630.0), 2.5),
    ):
        rows += [
            fundamental(
                sid, "BOOK_VALUE", "FY2019", date(2019, 12, 31), bv[0], K_FY2019
            ),
            fundamental(
                sid, "BOOK_VALUE", "FY2020", date(2020, 12, 31), bv[1], K_FY2020
            ),
            fundamental(
                sid, "TOT_ASSET", "FY2019", date(2019, 12, 31), ta[0], K_FY2019
            ),
            fundamental(
                sid, "TOT_ASSET", "FY2020", date(2020, 12, 31), ta[1], K_FY2020
            ),
            fundamental(sid, "EPS_WAD", "FY2020", date(2020, 12, 31), eps, K_FY2020),
        ]
    return rows


def _base_estimates() -> list[Row]:
    rows: list[Row] = []
    for sid, v0, v1 in (("SEC-A", 4.0, 5.0), ("SEC-B", 2.0, 1.5)):
        rows += [
            estimate(sid, v0, datetime(2021, 8, 1, 12, 0, tzinfo=UTC)),
            estimate(sid, v1, datetime(2021, 11, 15, 12, 0, tzinfo=UTC), vintage_seq=1),
        ]
    return rows


def _future_additions() -> dict[str, list[Row]]:
    """Everything an adversary could append after as_of (LT-010/LT-013
    shapes): future bars, a late-arriving in-period bar, restatements,
    new statements, a new consensus vintage."""
    prices: list[Row] = []
    for sid in UNIVERSE:
        prices += [
            price_bar(
                sid,
                date(2022, 1, 3) + timedelta(days=i),
                close=1e6,
                volume=1e6,
                market_cap=1e9,
            )
            for i in range(5)
        ]
        # late-arriving bar: event BEFORE as_of, knowledge AFTER (must not
        # change the as_of answer; changes the later-as_of answer)
        prices.append(
            price_bar(
                sid,
                date(2021, 12, 21),
                close=999_999.0,
                volume=9e6,
                market_cap=9e9,
                knowledge_time=datetime(2022, 1, 5, 12, 0, tzinfo=UTC),
            )
        )
    k_restate = datetime(2022, 2, 15, 12, 0, tzinfo=UTC)
    k_new = datetime(2022, 3, 31, 12, 0, tzinfo=UTC)
    fundamentals: list[Row] = []
    for sid in UNIVERSE:
        fundamentals += [
            fundamental(
                sid,
                "BOOK_VALUE",
                "FY2020",
                date(2020, 12, 31),
                9_999.0,
                k_restate,
                vintage_seq=1,
            ),
            fundamental(
                sid,
                "TOT_ASSET",
                "FY2020",
                date(2020, 12, 31),
                8_888.0,
                k_restate,
                vintage_seq=1,
            ),
            fundamental(
                sid,
                "EPS_WAD",
                "FY2020",
                date(2020, 12, 31),
                77.0,
                k_restate,
                vintage_seq=1,
            ),
            fundamental(
                sid, "BOOK_VALUE", "FY2021", date(2021, 12, 31), 7_777.0, k_new
            ),
            fundamental(sid, "TOT_ASSET", "FY2021", date(2021, 12, 31), 6_666.0, k_new),
        ]
    estimates = [
        estimate(sid, 9.9, datetime(2022, 1, 20, 12, 0, tzinfo=UTC), vintage_seq=2)
        for sid in UNIVERSE
    ]
    return {
        "prices_daily": prices,
        "fundamentals": fundamentals,
        "estimates_consensus": estimates,
    }


@pytest.fixture
def engines(tmp_path) -> tuple[FeatureEngine, FeatureEngine]:
    return build_engine_pair(
        tmp_path,
        base={
            "prices_daily": _base_prices(),
            "fundamentals": _base_fundamentals(),
            "estimates_consensus": _base_estimates(),
        },
        additions=_future_additions(),
    )


class TestCi004AppendFutureInvariance:
    @pytest.mark.parametrize(("feature_id", "version"), list(library_feature_keys()))
    def test_feature_at_as_of_never_moves(self, engines, feature_id, version):
        """CI-004/CI-002: appending post-as_of knowledge (bars,
        restatements, vintages) leaves every stored row bit-identical —
        values, observation_time AND knowledge_time."""
        engine_a, engine_b = engines
        result_a = engine_a.compute(feature_id, version, AS_OF, UNIVERSE)
        result_b = engine_b.compute(feature_id, version, AS_OF, UNIVERSE)
        assert len(result_a.rows) == len(UNIVERSE)  # probe has teeth
        assert result_a.rows == result_b.rows
        assert result_a.coverage == result_b.coverage
        assert result_a.eligible and result_b.eligible
        assert result_a.max_input_knowledge_time == result_b.max_input_knowledge_time

    def test_added_data_is_real(self, engines):
        """Teeth: at a later as_of the appended rows DO change answers
        (late-arriving 999999 close dominates reversal_1m), so the as_of
        invariance above cannot be passing vacuously."""
        engine_a, engine_b = engines
        rev_a = engine_a.compute("reversal_1m", 1, LATER_AS_OF, UNIVERSE)
        rev_b = engine_b.compute("reversal_1m", 1, LATER_AS_OF, UNIVERSE)
        assert rev_a.values() != rev_b.values()
        assert rev_b.values()["SEC-A"] > 100.0  # the 999999 bar is visible


class TestCi001StoredRowBounds:
    def test_every_stored_row_is_knowable_at_as_of(self, engines):
        """CI-001 on the feature layer's OUTPUT: knowledge_time <= as_of
        and observation_time <= knowledge_time on every row of all 9
        features."""
        engine_b = engines[1]
        for feature_id, version in library_feature_keys():
            result = engine_b.compute(feature_id, version, AS_OF, UNIVERSE)
            assert result.rows, feature_id
            for row in result.rows:
                assert row.knowledge_time <= AS_OF, feature_id
                assert row.observation_time <= row.knowledge_time, feature_id


class TestDeterminism:
    def test_double_run_bit_identical(self, engines):
        """CI-042 shape: the same engine computes the same rows twice."""
        engine_b = engines[1]
        for feature_id, version in library_feature_keys():
            first = engine_b.compute(feature_id, version, AS_OF, UNIVERSE)
            second = engine_b.compute(feature_id, version, AS_OF, UNIVERSE)
            assert first.rows == second.rows, feature_id

    def test_universe_order_invariance(self, engines):
        """CI-043: permuting the requested security order changes no row."""
        engine_b = engines[1]
        for feature_id, version in library_feature_keys():
            fwd = engine_b.compute(feature_id, version, AS_OF, UNIVERSE)
            rev = engine_b.compute(
                feature_id, version, AS_OF, tuple(reversed(UNIVERSE))
            )
            assert fwd.rows == rev.rows, feature_id

    def test_registry_hash_stable_for_lineage(self):
        """The lineage identity of the library registry is deterministic
        across builds (dataset manifests can pin it)."""
        assert (
            build_default_registry().registry_hash()
            == build_default_registry().registry_hash()
        )


class TestFullLibraryRun:
    def test_compute_list_runs_all_nine(self, engines):
        """CR-016 machinery end-to-end: the audited list computes every
        feature, in declared order, fully covered and eligible."""
        engine_b = engines[1]
        results = engine_b.compute_list(AUDITED_LIBRARY_LIST_ID, AS_OF, UNIVERSE)
        assert [r.spec.feature_id for r in results] == [
            fid for fid, _ in library_feature_keys()
        ]
        for result in results:
            assert result.coverage == 1.0, result.spec.feature_id
            assert result.eligible, result.spec.feature_id
            assert {row.security_id for row in result.rows} == set(UNIVERSE)
            for row in result.rows:
                assert row.feature_id == result.spec.feature_id
                assert row.feature_version == result.spec.version
