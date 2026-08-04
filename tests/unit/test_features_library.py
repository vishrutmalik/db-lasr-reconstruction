"""Audited-library formula fixtures (G022): one hand-worked micro-fixture
plus a coverage/missing-policy case per feature.

Every expected value is derived BY HAND in the test docstring (never by
running the code under test — skills/quantitative-test-design step 6);
each feature cites its field_mapping.md evidence row. All computations run
through the real PitStore + engine (as_of = 2021-12-31 12:00 UTC; bar
knowledge = 21:00 UTC of the bar's day).

CI-024 window discipline is bound here: a trailing-window statistic
(volatility_60d, adv_dollar_20d) ignores data outside its declared window
(perturbation outside → bit-identical; inside → changed, teeth).
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta

import pytest
from test_features_fixtures import (
    AS_OF,
    build_engine,
    build_engine_pair,
    estimate,
    fundamental,
    price_bar,
)

pytestmark = pytest.mark.unit

K_FY2019 = datetime(2020, 3, 31, 12, 0, tzinfo=UTC)
K_FY2020 = datetime(2021, 3, 31, 12, 0, tzinfo=UTC)


class TestMomentum121:
    """momentum_12_1 = close(<= d-30d) / close(<= d-365d) - 1
    (field_mapping §5.3, FM-18(c))."""

    def test_hand_fixture(self, tmp_path):
        """d = 2021-12-31. recent day = 12-01 -> last bar 2021-11-30
        (close 130, 1d stale); base day = 2020-12-31 -> last bar
        2020-12-28 (close 100, 3d stale). 130/100 - 1 = 0.30 exactly.
        The 2021-12-30 bar (close 143) must NOT enter (it is after the
        skip cutoff)."""
        engine = build_engine(
            tmp_path,
            prices=[
                price_bar("SEC-A", date(2020, 12, 28), close=100.0),
                price_bar("SEC-A", date(2021, 11, 30), close=130.0),
                price_bar("SEC-A", date(2021, 12, 30), close=143.0),
            ],
        )
        result = engine.compute("momentum_12_1", 1, AS_OF, ["SEC-A"])
        assert result.values() == {"SEC-A": pytest.approx(0.30, abs=1e-12)}
        (row,) = result.rows
        assert row.observation_time == datetime(2021, 11, 30, tzinfo=UTC)

    def test_missing_base_and_stale_base_excluded(self, tmp_path):
        """SEC-B has no bar near the base day -> missing; SEC-C's base bar
        is 31 days stale (> 20d guard) -> missing (CI-021 exclude)."""
        engine = build_engine(
            tmp_path,
            prices=[
                price_bar("SEC-A", date(2020, 12, 28), close=100.0),
                price_bar("SEC-A", date(2021, 11, 30), close=130.0),
                price_bar("SEC-B", date(2021, 11, 30), close=50.0),
                price_bar("SEC-C", date(2020, 11, 30), close=80.0),
                price_bar("SEC-C", date(2021, 11, 30), close=90.0),
            ],
        )
        result = engine.compute("momentum_12_1", 1, AS_OF, ["SEC-A", "SEC-B", "SEC-C"])
        assert set(result.values()) == {"SEC-A"}
        assert result.coverage == pytest.approx(1 / 3)
        assert not result.eligible  # 1/3 < min_coverage 0.5


class TestReversal1m:
    """reversal_1m = close(<= d) / close(<= d-30d) - 1 (field_mapping
    §5.3 'Total return, 21D (1M)'); direction lower_is_better."""

    def test_hand_fixture(self, tmp_path):
        """now bar 2021-12-30 close 143; prev day = 12-01 -> bar
        2021-11-30 close 130. 143/130 - 1 = 0.1 exactly."""
        engine = build_engine(
            tmp_path,
            prices=[
                price_bar("SEC-A", date(2021, 11, 30), close=130.0),
                price_bar("SEC-A", date(2021, 12, 30), close=143.0),
            ],
        )
        result = engine.compute("reversal_1m", 1, AS_OF, ["SEC-A"])
        assert result.values() == {"SEC-A": pytest.approx(0.1, abs=1e-12)}

    def test_null_close_excluded(self, tmp_path):
        """A bar with close=None cannot cover the lookup (CI-021)."""
        engine = build_engine(
            tmp_path,
            prices=[
                price_bar("SEC-A", date(2021, 11, 30), close=None, volume=1.0),
                price_bar("SEC-A", date(2021, 12, 30), close=143.0),
            ],
        )
        result = engine.compute("reversal_1m", 1, AS_OF, ["SEC-A"])
        assert result.values() == {}
        assert result.coverage == 0.0


class TestSizeNegLogMcap:
    """size_neg_log_mcap = -ln(market_cap at last bar <= d)
    (field_mapping §5.6 '-Market Cap', FM-25)."""

    def test_hand_fixture(self, tmp_path):
        """mcap 2000 -> -ln(2000) = -7.6009024595420815..."""
        engine = build_engine(
            tmp_path,
            prices=[price_bar("SEC-A", date(2021, 12, 30), market_cap=2000.0)],
        )
        result = engine.compute("size_neg_log_mcap", 1, AS_OF, ["SEC-A"])
        assert result.values() == {"SEC-A": pytest.approx(-math.log(2000.0), rel=1e-12)}

    def test_nonpositive_and_missing_mcap_excluded(self, tmp_path):
        engine = build_engine(
            tmp_path,
            prices=[
                price_bar("SEC-A", date(2021, 12, 30), market_cap=2000.0),
                price_bar("SEC-B", date(2021, 12, 30), close=5.0),  # no mcap
            ],
        )
        result = engine.compute("size_neg_log_mcap", 1, AS_OF, ["SEC-A", "SEC-B"])
        assert set(result.values()) == {"SEC-A"}


class TestBookToPrice:
    """book_to_price = BOOK_VALUE(latest statement) / market_cap
    (field_mapping §5.1: B/P = BOOK_VALUE dict r202 / MCAP dict r418)."""

    def test_hand_fixture(self, tmp_path):
        """BOOK_VALUE FY2020 = 500 (knowledge 2021-03-31, clears the 90d
        lag: 2021-03-31 + 90d = 2021-06-29 <= as_of); mcap 2000 ->
        500/2000 = 0.25."""
        engine = build_engine(
            tmp_path,
            prices=[price_bar("SEC-A", date(2021, 12, 30), market_cap=2000.0)],
            fundamentals=[
                fundamental(
                    "SEC-A", "BOOK_VALUE", "FY2020", date(2020, 12, 31), 500.0, K_FY2020
                )
            ],
        )
        result = engine.compute("book_to_price", 1, AS_OF, ["SEC-A"])
        assert result.values() == {"SEC-A": pytest.approx(0.25, abs=1e-12)}

    def test_stale_statement_excluded(self, tmp_path):
        """A statement with period_end 560d before as_of (> 540d guard)
        is missing, not stale-filled."""
        engine = build_engine(
            tmp_path,
            prices=[price_bar("SEC-A", date(2021, 12, 30), market_cap=2000.0)],
            fundamentals=[
                fundamental(
                    "SEC-A",
                    "BOOK_VALUE",
                    "FY2019",
                    AS_OF.date() - timedelta(days=560),  # 2020-06-19
                    500.0,
                    datetime(2020, 8, 15, 12, 0, tzinfo=UTC),  # after period_end (U3)
                )
            ],
        )
        result = engine.compute("book_to_price", 1, AS_OF, ["SEC-A"])
        assert result.values() == {}


class TestEarningsYield:
    """earnings_yield = EPS_WAD(latest statement) / close
    (field_mapping §5.1 multiples inverted; EPS_WAD dict r38)."""

    def test_hand_fixture(self, tmp_path):
        """EPS 5.0 / close 100 = 0.05."""
        engine = build_engine(
            tmp_path,
            prices=[price_bar("SEC-A", date(2021, 12, 30), close=100.0)],
            fundamentals=[
                fundamental(
                    "SEC-A", "EPS_WAD", "FY2020", date(2020, 12, 31), 5.0, K_FY2020
                )
            ],
        )
        result = engine.compute("earnings_yield", 1, AS_OF, ["SEC-A"])
        assert result.values() == {"SEC-A": pytest.approx(0.05, abs=1e-12)}

    def test_negative_eps_is_a_legal_value(self, tmp_path):
        """Losses produce negative yield — a raw value, not a missing one
        (rank handles outliers, P1-09)."""
        engine = build_engine(
            tmp_path,
            prices=[price_bar("SEC-A", date(2021, 12, 30), close=100.0)],
            fundamentals=[
                fundamental(
                    "SEC-A", "EPS_WAD", "FY2020", date(2020, 12, 31), -2.0, K_FY2020
                )
            ],
        )
        result = engine.compute("earnings_yield", 1, AS_OF, ["SEC-A"])
        assert result.values() == {"SEC-A": pytest.approx(-0.02, abs=1e-12)}


class TestEpsRevision3m:
    """eps_revision_3m = (consensus now - consensus at as_of-91d) /
    |consensus at as_of-91d| (field_mapping §5.4; SYNTHETIC-ONLY)."""

    def test_hand_fixture(self, tmp_path):
        """Vintage 0 = 4.0 (k 2021-08-01, knowable at as_of-91d =
        2021-10-01); vintage 1 = 5.0 (k 2021-11-15, the latest now).
        (5-4)/|4| = 0.25."""
        engine = build_engine(
            tmp_path,
            estimates=[
                estimate("SEC-A", 4.0, datetime(2021, 8, 1, 12, 0, tzinfo=UTC)),
                estimate(
                    "SEC-A",
                    5.0,
                    datetime(2021, 11, 15, 12, 0, tzinfo=UTC),
                    vintage_seq=1,
                ),
            ],
        )
        result = engine.compute("eps_revision_3m", 1, AS_OF, ["SEC-A"])
        assert result.values() == {"SEC-A": pytest.approx(0.25, abs=1e-12)}

    def test_no_prior_vintage_and_zero_prior_excluded(self, tmp_path):
        """SEC-B's only vintage arrives after as_of-91d -> no prior ->
        missing. SEC-C's prior is exactly 0 -> relative change undefined
        -> missing (documented)."""
        engine = build_engine(
            tmp_path,
            estimates=[
                estimate("SEC-B", 5.0, datetime(2021, 11, 15, 12, 0, tzinfo=UTC)),
                estimate("SEC-C", 0.0, datetime(2021, 8, 1, 12, 0, tzinfo=UTC)),
                estimate(
                    "SEC-C",
                    1.0,
                    datetime(2021, 11, 15, 12, 0, tzinfo=UTC),
                    vintage_seq=1,
                ),
            ],
        )
        result = engine.compute("eps_revision_3m", 1, AS_OF, ["SEC-B", "SEC-C"])
        assert result.values() == {}


class TestVolatility60d:
    """volatility_60d = sample std (ddof=1) of successive daily close
    returns over [d-60d, d] (field_mapping FM-21)."""

    @staticmethod
    def _alternating_bars(security_id: str, start: date, n_bars: int):
        """Closes multiply by 1.1 / 0.9 alternately -> returns alternate
        +0.10 / -0.10 exactly (up to float rounding)."""
        bars = []
        close = 100.0
        for i in range(n_bars):
            bars.append(price_bar(security_id, start + timedelta(days=i), close=close))
            close *= 1.1 if i % 2 == 0 else 0.9
        return bars

    def test_hand_fixture(self, tmp_path):
        """11 bars -> 10 returns alternating +0.1/-0.1: mean 0, sample
        var = 10*(0.1)^2/9 -> std = sqrt(0.1)/3 = 0.105409255338946
        (analytic, not computed by the kernel)."""
        engine = build_engine(
            tmp_path,
            prices=self._alternating_bars("SEC-A", date(2021, 12, 1), 11),
        )
        result = engine.compute("volatility_60d", 1, AS_OF, ["SEC-A"])
        assert result.values() == {
            "SEC-A": pytest.approx(math.sqrt(0.1) / 3.0, rel=1e-9)
        }

    def test_too_few_returns_excluded(self, tmp_path):
        """10 bars -> 9 returns < 10 required -> missing."""
        engine = build_engine(
            tmp_path,
            prices=self._alternating_bars("SEC-A", date(2021, 12, 1), 10),
        )
        result = engine.compute("volatility_60d", 1, AS_OF, ["SEC-A"])
        assert result.values() == {}

    def test_ci024_window_discipline(self, tmp_path):
        """CI-024 analog: a bar OUTSIDE [d-60d, d] (2021-10-30, absurd
        close 5.0) cannot move the statistic; the same bar INSIDE the
        window does (teeth)."""
        base = self._alternating_bars("SEC-A", date(2021, 12, 1), 11)
        engine_a, engine_b = build_engine_pair(
            tmp_path,
            base={"prices_daily": base},
            additions={
                "prices_daily": [price_bar("SEC-A", date(2021, 10, 30), close=5.0)]
            },
        )
        rows_a = engine_a.compute("volatility_60d", 1, AS_OF, ["SEC-A"]).rows
        rows_b = engine_b.compute("volatility_60d", 1, AS_OF, ["SEC-A"]).rows
        assert rows_a == rows_b  # outside the window: bit-identical
        # teeth: the same absurd close INSIDE the window changes the value
        engine_c, engine_d = build_engine_pair(
            tmp_path / "teeth",
            base={"prices_daily": base},
            additions={
                "prices_daily": [price_bar("SEC-A", date(2021, 11, 20), close=5.0)]
            },
        )
        value_c = engine_c.compute("volatility_60d", 1, AS_OF, ["SEC-A"]).values()
        value_d = engine_d.compute("volatility_60d", 1, AS_OF, ["SEC-A"]).values()
        assert value_c["SEC-A"] != value_d["SEC-A"]


class TestAdvDollar20d:
    """adv_dollar_20d = mean(close * volume) over [d-20d, d]
    (field_mapping FM-29 / FM-30(b))."""

    def test_hand_fixture(self, tmp_path):
        """5 bars, (close, volume) pairs (10,100),(20,50),(10,100),
        (20,50),(10,100) -> every dollar volume = 1000 -> mean 1000."""
        pairs = [
            (10.0, 100.0),
            (20.0, 50.0),
            (10.0, 100.0),
            (20.0, 50.0),
            (10.0, 100.0),
        ]
        engine = build_engine(
            tmp_path,
            prices=[
                price_bar(
                    "SEC-A",
                    date(2021, 12, 24) + timedelta(days=i),
                    close=c,
                    volume=v,
                )
                for i, (c, v) in enumerate(pairs)
            ],
        )
        result = engine.compute("adv_dollar_20d", 1, AS_OF, ["SEC-A"])
        assert result.values() == {"SEC-A": pytest.approx(1000.0, abs=1e-9)}

    def test_null_volume_rows_dont_count(self, tmp_path):
        """4 complete bars + 1 with volume=None -> 4 < 5 minimum ->
        missing (a null leg never fabricates a dollar volume)."""
        engine = build_engine(
            tmp_path,
            prices=[
                price_bar("SEC-A", date(2021, 12, 24), close=10.0, volume=None),
                *[
                    price_bar(
                        "SEC-A",
                        date(2021, 12, 25) + timedelta(days=i),
                        close=10.0,
                        volume=100.0,
                    )
                    for i in range(4)
                ],
            ],
        )
        result = engine.compute("adv_dollar_20d", 1, AS_OF, ["SEC-A"])
        assert result.values() == {}

    def test_ci024_window_discipline(self, tmp_path):
        """A huge dollar-volume bar just OUTSIDE [d-20d, d] (2021-12-10)
        cannot move the mean; inside (2021-12-30) it does (teeth)."""
        base = [
            price_bar(
                "SEC-A",
                date(2021, 12, 24) + timedelta(days=i),
                close=10.0,
                volume=100.0,
            )
            for i in range(5)
        ]
        engine_a, engine_b = build_engine_pair(
            tmp_path,
            base={"prices_daily": base},
            additions={
                "prices_daily": [
                    price_bar("SEC-A", date(2021, 12, 10), close=1e6, volume=1e6)
                ]
            },
        )
        assert (
            engine_a.compute("adv_dollar_20d", 1, AS_OF, ["SEC-A"]).rows
            == engine_b.compute("adv_dollar_20d", 1, AS_OF, ["SEC-A"]).rows
        )
        engine_c, engine_d = build_engine_pair(
            tmp_path / "teeth",
            base={"prices_daily": base},
            additions={
                "prices_daily": [
                    price_bar("SEC-A", date(2021, 12, 30), close=1e6, volume=1e6)
                ]
            },
        )
        assert (
            engine_c.compute("adv_dollar_20d", 1, AS_OF, ["SEC-A"]).values()
            != engine_d.compute("adv_dollar_20d", 1, AS_OF, ["SEC-A"]).values()
        )


class TestAssetGrowth1y:
    """asset_growth_1y = TOT_ASSET(FY0)/TOT_ASSET(FY-1) - 1
    (field_mapping §5.2 'Asset growth', TOT_ASSET dict r117)."""

    def test_hand_fixture(self, tmp_path):
        """FY2020 = 1000 (pe 2020-12-31), FY2019 = 800 (pe 2019-12-31,
        gap 366d in [330, 400]): 1000/800 - 1 = 0.25."""
        engine = build_engine(
            tmp_path,
            fundamentals=[
                fundamental(
                    "SEC-A", "TOT_ASSET", "FY2019", date(2019, 12, 31), 800.0, K_FY2019
                ),
                fundamental(
                    "SEC-A", "TOT_ASSET", "FY2020", date(2020, 12, 31), 1000.0, K_FY2020
                ),
            ],
        )
        result = engine.compute("asset_growth_1y", 1, AS_OF, ["SEC-A"])
        assert result.values() == {"SEC-A": pytest.approx(0.25, abs=1e-12)}
        (row,) = result.rows
        # pure-fundamental feature: stored knowledge = statement knowledge
        # + the 90d registry lag (CI-005 arithmetic, exact)
        assert row.knowledge_time == K_FY2020 + timedelta(days=90)
        assert row.observation_time == datetime(2020, 12, 31, tzinfo=UTC)

    def test_single_statement_and_bad_gap_excluded(self, tmp_path):
        """SEC-B has one statement -> missing; SEC-C's statements are two
        years apart (gap 731d > 400d) -> missing; SEC-D's prior is
        non-positive -> missing."""
        engine = build_engine(
            tmp_path,
            fundamentals=[
                fundamental(
                    "SEC-B", "TOT_ASSET", "FY2020", date(2020, 12, 31), 1000.0, K_FY2020
                ),
                fundamental(
                    "SEC-C", "TOT_ASSET", "FY2018", date(2018, 12, 31), 700.0, K_FY2019
                ),
                fundamental(
                    "SEC-C", "TOT_ASSET", "FY2020", date(2020, 12, 31), 1000.0, K_FY2020
                ),
                fundamental(
                    "SEC-D", "TOT_ASSET", "FY2019", date(2019, 12, 31), -5.0, K_FY2019
                ),
                fundamental(
                    "SEC-D", "TOT_ASSET", "FY2020", date(2020, 12, 31), 1000.0, K_FY2020
                ),
            ],
        )
        result = engine.compute(
            "asset_growth_1y", 1, AS_OF, ["SEC-B", "SEC-C", "SEC-D"]
        )
        assert result.values() == {}
