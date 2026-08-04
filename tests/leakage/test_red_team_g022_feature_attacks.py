"""Red-team keeper tests for G022 (docs/red_team/G022.md) — feature layer.

Adversarial scenarios with KNOWN correct outcomes, promoted per the
red-team charter. All of these PASS on the audited implementation — they
are regression guards for behaviors the audit confirmed HELD, not
reproductions of open findings (those live in the report only, so CI
stays green).

Covered attacks (report attack-log ids in parentheses):

- context escape via a timezone-disguised forward ``as_of`` — a +09:00
  wall time whose UTC instant is later than the computation as_of must be
  refused; one whose UTC instant is earlier must be served (A1);
- frame-mutation cache poisoning: a kernel that mutates the returned
  frame and re-queries must see pristine store state (A4);
- metric-filter smuggling with a declared+undeclared metric LIST (A5a);
- A-G022-01 stamping direction: the conservative cross-sectional max is
  universe-dependent but NEVER earlier than a row's own inputs (B1/B2);
- momentum_12_1 skip-window teeth: a price jump strictly inside the last
  30 calendar days must not move momentum; the same jump placed exactly
  at as_of-30d must (D1);
- volatility_60d recomputed independently: sample std (ddof=1) of
  pairwise returns, stored DAILY (no sqrt(252) annualization) (D2);
- asset_growth_1y denominator vintage: a restatement of the prior-year
  statement is used iff knowable through the 90d registry lag (CI-002
  restatement trap, both directions) (D3);
- eps_revision_3m prior leg: the trailing as_of-91d query must return the
  vintage knowable THEN, not the latest overall vintage (D4).

These tests build real canonical datasets and query through a real
PitStore (never hand-made frames), self-contained so the file runs under
standalone ``tests/leakage`` collection.
"""

from __future__ import annotations

import itertools
import math
from datetime import UTC, date, datetime, time, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from lasr.core.enums import PitGrade, RevisionSupport
from lasr.data.canonical.builders import BuildContext, BuildResult, write_build
from lasr.data.canonical.stamping import StampingConfig
from lasr.data.canonical.store import CanonicalStore
from lasr.data.point_in_time import PitStore
from lasr.data.providers.base import (
    CorporateActionBasis,
    FamilyCapability,
    FieldFamily,
)
from lasr.data.schemas.base import Row
from lasr.features.computation import FeatureComputationError, RawObservation
from lasr.features.engine import FeatureEngine
from lasr.features.library import build_default_registry
from lasr.features.registry import FeatureRegistry

pytestmark = pytest.mark.leakage

AS_OF = datetime(2021, 12, 31, 12, 0, tzinfo=UTC)
AS_OF_DAY = AS_OF.date()
RETRIEVAL = datetime(2022, 6, 30, 12, 0, tzinfo=UTC)

_CAPABILITY = FamilyCapability(
    available=True,
    supports_pit=True,
    revision_support=RevisionSupport.FULL_VINTAGES,
    fields=frozenset({"CLOSE"}),
    notes="RT-G022 keeper fixture: vintage-capable",
    corporate_action_basis=CorporateActionBasis.UNADJUSTED,
)

_FAMILIES = {
    "prices_daily": FieldFamily.MARKET_DAILY,
    "fundamentals": FieldFamily.FUNDAMENTALS,
    "estimates_consensus": FieldFamily.ESTIMATES,
}


def _bar_kt(day: date) -> datetime:
    """Post-close knowledge stamp for a bar (21:00 UTC of its event day)."""
    return datetime.combine(day, time(21, 0), tzinfo=UTC)


def _price_bar(
    security_id: str,
    day: date,
    *,
    close: float | None = None,
    market_cap: float | None = None,
) -> Row:
    return {
        "security_id": security_id,
        "event_date": day,
        "knowledge_time": _bar_kt(day),
        "open": None,
        "high": None,
        "low": None,
        "close": close,
        "volume": None,
        "vwap": None,
        "bid": None,
        "ask": None,
        "shares_outstanding": None,
        "market_cap": market_cap,
        "currency": "USD",
        "source_snapshot_id": "snap-rt-g022",
    }


def _fundamental(
    security_id: str,
    metric: str,
    fiscal_period: str,
    period_end: date,
    value: float,
    knowledge_time: datetime,
    *,
    vintage_seq: int = 0,
) -> Row:
    return {
        "security_id": security_id,
        "metric": metric,
        "fiscal_period": fiscal_period,
        "period_end": period_end,
        "report_date": None,
        "knowledge_time": knowledge_time,
        "knowledge_basis": "published",
        "ingestion_time": RETRIEVAL,
        "vintage_seq": vintage_seq,
        "value": value,
        "unit": "millions_of_selected_currency",
        "currency": "USD",
        "consolidation_basis": None,
    }


def _estimate(
    security_id: str,
    value: float,
    knowledge_time: datetime,
    *,
    vintage_seq: int = 0,
) -> Row:
    return {
        "security_id": security_id,
        "metric": "EPS",
        "forecast_period": "FY+1",
        "stat": "mean",
        "value": value,
        "knowledge_time": knowledge_time,
        "vintage_seq": vintage_seq,
        "n_contributors": None,
    }


def _engine(
    tmp_path: Path,
    *,
    prices: list[Row] | None = None,
    fundamentals: list[Row] | None = None,
    estimates: list[Row] | None = None,
    registry: FeatureRegistry | None = None,
) -> FeatureEngine:
    store = CanonicalStore(tmp_path)
    ctx = BuildContext(
        provider_name="rt_g022_provider",
        provider_version="1.0.0",
        capability=_CAPABILITY,
        source_snapshot_ids=("snap-rt-g022",),
        retrieval_time=RETRIEVAL,
        stamping=StampingConfig(bar_close_time=time(21, 0)),
    )
    dataset_ids: dict[str, str] = {}
    for table, records in (
        ("prices_daily", prices),
        ("fundamentals", fundamentals),
        ("estimates_consensus", estimates),
    ):
        if records:
            build = BuildResult(
                table_name=table,
                family=_FAMILIES[table],
                records=tuple(records),
                pit_grade=PitGrade.FULL_VINTAGES,
                downgrade_events=(),
                context=ctx,
            )
            dataset_ids[table] = write_build(store, build).dataset_id
    pit = PitStore(store, dataset_ids=dataset_ids)
    return FeatureEngine(registry or build_default_registry(), pit)


def _toy_spec(**overrides):
    """Minimal valid close-feature spec (mirrors the unit suite's helper)."""
    from lasr.data.schemas.features import FeatureSpec

    fields = {
        "feature_id": "toy_close",
        "version": 1,
        "category": "technical",
        "direction": "learned",
        "required_fields": ("prices_daily.close",),
        "formula": "last knowable close (red-team toy)",
        "units": "price",
        "frequency": "daily",
        "min_coverage": 0.5,
        "publication_lag": timedelta(0),
        "missing_policy": "exclude",
        "outlier_policy": "none_rank_handles",
        "neutralize": False,
        "monotonicity": "unknown",
        "evidence_source": "red-team toy (docs/red_team/G022.md)",
        "provenance": "ASSUMED",
        "availability": "derived",
    }
    fields.update(overrides)
    return FeatureSpec(**fields)


class TestContextEscape:
    """Attack surface 1: every way a kernel could see past as_of."""

    def test_tz_disguised_forward_as_of_refused(self, tmp_path):
        """A +09:00 wall time later than ctx.as_of IN UTC is a forward look
        no matter how the offset dresses it up; an earlier UTC instant with
        the same trick is a legal trailing query."""
        plus9 = timezone(timedelta(hours=9))
        served: dict[str, int] = {}

        def tz_kernel(ctx, securities):
            # 20:00+09:00 == 11:00Z < 12:00Z -> legal trailing query
            back = ctx.frame(
                "prices_daily",
                keys={"security_id": securities},
                as_of=datetime(2021, 12, 31, 20, 0, tzinfo=plus9),
            )
            served["backward_rows"] = len(back)
            # 22:00+09:00 == 13:00Z > 12:00Z -> forward, must raise
            ctx.frame(
                "prices_daily",
                keys={"security_id": securities},
                as_of=datetime(2021, 12, 31, 22, 0, tzinfo=plus9),
            )
            return {}

        registry = FeatureRegistry()
        registry.register(_toy_spec(), tz_kernel)
        engine = _engine(
            tmp_path,
            prices=[_price_bar("SEC-A", date(2021, 12, 30), close=42.0)],
            registry=registry,
        )
        with pytest.raises(FeatureComputationError, match="CI-001"):
            engine.compute("toy_close", 1, AS_OF, ["SEC-A"])
        # teeth: the backward branch executed and was served
        assert served["backward_rows"] == 1

    def test_frame_mutation_cannot_poison_store(self, tmp_path):
        """The returned frame is not a view into store state: poisoning it
        (and its record dicts) must not change a re-query."""

        def mutator(ctx, securities):
            first = ctx.frame("prices_daily", keys={"security_id": securities})
            first.loc[:, "close"] = 1e9
            records = first.to_dict("records")
            records[0]["close"] = -777.0
            second = ctx.frame("prices_daily", keys={"security_id": securities})
            value = float(second.iloc[0]["close"])
            return {
                "SEC-A": RawObservation(
                    value=value, observation_time=AS_OF - timedelta(days=1)
                )
            }

        registry = FeatureRegistry()
        registry.register(_toy_spec(), mutator)
        engine = _engine(
            tmp_path,
            prices=[_price_bar("SEC-A", date(2021, 12, 30), close=42.0)],
            registry=registry,
        )
        result = engine.compute("toy_close", 1, AS_OF, ["SEC-A"])
        assert result.values() == {"SEC-A": 42.0}

    def test_metric_list_smuggling_refused(self, tmp_path):
        """A metric filter LIST mixing declared and undeclared ids must be
        refused before any row is served."""
        spec = _toy_spec(
            feature_id="toy_book",
            required_fields=("fundamentals.BOOK_VALUE",),
            publication_lag=timedelta(days=90),
        )

        def smuggler(ctx, securities):
            ctx.frame(
                "fundamentals",
                keys={
                    "security_id": securities,
                    "metric": ["BOOK_VALUE", "TOT_ASSET"],
                },
            )
            return {}

        registry = FeatureRegistry()
        registry.register(spec, smuggler)
        engine = _engine(
            tmp_path,
            fundamentals=[
                _fundamental(
                    "SEC-A",
                    "BOOK_VALUE",
                    "FY2020",
                    date(2020, 12, 31),
                    500.0,
                    datetime(2021, 3, 31, 12, 0, tzinfo=UTC),
                ),
                _fundamental(
                    "SEC-A",
                    "TOT_ASSET",
                    "FY2020",
                    date(2020, 12, 31),
                    999.0,
                    datetime(2021, 3, 31, 12, 0, tzinfo=UTC),
                ),
            ],
            registry=registry,
        )
        with pytest.raises(FeatureComputationError, match="undeclared metric"):
            engine.compute("toy_book", 1, AS_OF, ["SEC-A"])


class TestStampingDirection:
    """Attack surface 2 (A-G022-01): the conservative-max stamp may be
    LATER than a row's own inputs (universe-dependent), never earlier."""

    def test_stale_security_stamped_with_fresh_knowledge_never_earlier(self, tmp_path):
        old_day = AS_OF_DAY - timedelta(days=10)
        fresh_day = AS_OF_DAY - timedelta(days=1)
        engine = _engine(
            tmp_path,
            prices=[
                _price_bar("SEC-OLD", old_day, market_cap=1e9),
                _price_bar("SEC-FRESH", fresh_day, market_cap=2e9),
            ],
        )
        joint = engine.compute("size_neg_log_mcap", 1, AS_OF, ["SEC-OLD", "SEC-FRESH"])
        rows = {r.security_id: r for r in joint.rows}
        # OLD is stamped with FRESH's knowledge: over-conservative, honest.
        assert rows["SEC-OLD"].knowledge_time == _bar_kt(fresh_day)
        # Direction invariant: never earlier than the row's OWN input.
        assert rows["SEC-OLD"].knowledge_time >= _bar_kt(old_day)
        assert rows["SEC-FRESH"].knowledge_time >= _bar_kt(fresh_day)
        # Alone, OLD's stamp collapses to its own input's knowledge — the
        # stamp is universe-dependent (report finding RT-G022-N8 documents
        # the persistence implications); the VALUE must not be.
        solo = engine.compute("size_neg_log_mcap", 1, AS_OF, ["SEC-OLD"])
        (solo_row,) = solo.rows
        assert solo_row.knowledge_time == _bar_kt(old_day)
        assert solo_row.value == rows["SEC-OLD"].value


class TestLibraryFormulaHonesty:
    """Attack surface 4: recompute library features independently and
    spring the known traps (skip window, restatement, trailing vintage)."""

    @staticmethod
    def _weekday_range(days_back: int) -> list[date]:
        start = AS_OF_DAY - timedelta(days=days_back)
        return [
            start + timedelta(days=i)
            for i in range(days_back + 1)
            if (start + timedelta(days=i)).weekday() < 5
            and (start + timedelta(days=i)) <= AS_OF_DAY
        ]

    def test_momentum_skip_window_has_teeth(self, tmp_path):
        """An 80% jump strictly inside the last 30 calendar days must NOT
        move 12-1 momentum; the same jump at exactly as_of-30d must."""
        days = self._weekday_range(400)
        inside = [
            _price_bar(
                "SEC-J",
                d,
                close=100.0 if d <= AS_OF_DAY - timedelta(days=30) else 180.0,
            )
            for d in days
        ]
        at_boundary = [
            _price_bar(
                "SEC-K",
                d,
                close=100.0 if d < AS_OF_DAY - timedelta(days=30) else 180.0,
            )
            for d in days
        ]
        engine = _engine(tmp_path, prices=inside + at_boundary)
        values = engine.compute("momentum_12_1", 1, AS_OF, ["SEC-J", "SEC-K"]).values()
        assert values["SEC-J"] == pytest.approx(0.0, abs=1e-12)  # skip honored
        assert values["SEC-K"] == pytest.approx(0.8, abs=1e-12)  # boundary in

    def test_volatility_60d_daily_ddof1_not_annualized(self, tmp_path):
        """Independent recompute: sample std (ddof=1) over pairwise returns
        of knowable bars in [as_of-60d, as_of]; stored value is DAILY."""
        rng = np.random.default_rng(20260730)
        days = self._weekday_range(90)
        closes: dict[date, float] = {}
        level = 100.0
        for d in days:
            level *= float(np.exp(rng.normal(0.0, 0.01)))
            closes[d] = level
        engine = _engine(
            tmp_path, prices=[_price_bar("SEC-A", d, close=closes[d]) for d in days]
        )
        got = engine.compute("volatility_60d", 1, AS_OF, ["SEC-A"]).values()["SEC-A"]
        window_start = AS_OF_DAY - timedelta(days=60)
        knowable = [
            closes[d]
            for d in days
            if window_start <= d <= AS_OF_DAY and _bar_kt(d) <= AS_OF
        ]
        returns = [b / a - 1.0 for a, b in itertools.pairwise(knowable)]
        expected = float(np.std(np.array(returns), ddof=1))
        assert got == pytest.approx(expected, abs=1e-15)
        assert not math.isclose(got, expected * math.sqrt(252), rel_tol=1e-6)

    def test_asset_growth_denominator_is_knowable_vintage(self, tmp_path):
        """CI-002 restatement trap, both directions: the FY2020 restatement
        feeds the denominator iff knowable through the 90d registry lag."""
        as_of_late = datetime(2022, 8, 1, 12, 0, tzinfo=UTC)

        def growth(sub_path: Path, restate_kt: datetime) -> float:
            engine = _engine(
                sub_path,
                fundamentals=[
                    _fundamental(
                        "SEC-A",
                        "TOT_ASSET",
                        "FY2020",
                        date(2020, 12, 31),
                        1000.0,
                        datetime(2021, 3, 31, 12, 0, tzinfo=UTC),
                    ),
                    _fundamental(
                        "SEC-A",
                        "TOT_ASSET",
                        "FY2020",
                        date(2020, 12, 31),
                        1200.0,
                        restate_kt,
                        vintage_seq=1,
                    ),
                    _fundamental(
                        "SEC-A",
                        "TOT_ASSET",
                        "FY2021",
                        date(2021, 12, 31),
                        1500.0,
                        datetime(2022, 3, 31, 12, 0, tzinfo=UTC),
                    ),
                ],
            )
            return engine.compute("asset_growth_1y", 1, as_of_late, ["SEC-A"]).values()[
                "SEC-A"
            ]

        # knowable: kt 2022-02-15 + 90d = 2022-05-16 <= as_of -> restated 1200
        knowable = growth(
            tmp_path / "knowable", datetime(2022, 2, 15, 12, 0, tzinfo=UTC)
        )
        assert knowable == pytest.approx(1500.0 / 1200.0 - 1.0)
        # embargoed: kt 2022-06-15 + 90d = 2022-09-13 > as_of -> original 1000
        embargoed = growth(
            tmp_path / "embargoed", datetime(2022, 6, 15, 12, 0, tzinfo=UTC)
        )
        assert embargoed == pytest.approx(1500.0 / 1000.0 - 1.0)

    def test_eps_revision_prior_leg_uses_trailing_vintage(self, tmp_path):
        """The as_of-91d leg must be the consensus knowable THEN (v0), not
        the latest overall vintage (which would fake a 0.0 revision)."""
        engine = _engine(
            tmp_path,
            estimates=[
                _estimate("SEC-A", 3.0, datetime(2021, 8, 15, 12, 0, tzinfo=UTC)),
                _estimate(
                    "SEC-A",
                    4.0,
                    datetime(2021, 11, 20, 12, 0, tzinfo=UTC),
                    vintage_seq=1,
                ),
            ],
        )
        result = engine.compute("eps_revision_3m", 1, AS_OF, ["SEC-A"])
        assert result.values()["SEC-A"] == pytest.approx((4.0 - 3.0) / 3.0)
        (row,) = result.rows
        # stamp = the fresh vintage's knowledge (max input seen)
        assert row.knowledge_time == datetime(2021, 11, 20, 12, 0, tzinfo=UTC)
