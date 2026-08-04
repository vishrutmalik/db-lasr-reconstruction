"""Remediation tests for the G022 red-team findings (docs/red_team/G022.md).

Each class pins one finding's fix with the audit's own reproduction:

- RT-G022-B1 (BLOCKING) — stored ``knowledge_time`` reflects the EFFECTIVE
  lag the PIT store applied (``max(configured floor, registry lag)``).
  Invariant: querying every input table at the stored stamp under the SAME
  PitQueryConfig serves the rows the computation used (the audit's 0-rows
  reproduction, inverted); one microsecond earlier serves none (the stamp
  is the earliest honest availability instant).
- RT-G022-N1 — metric key objects with divergent ``__str__``/``__eq__``
  cannot smuggle undeclared metric rows (outgoing filter rewritten to
  validated strings).
- RT-G022-N2 — metric-table frames drop undeclared columns (notably the
  post-as_of ``ingestion_time`` wall-clock stamp).
- RT-G022-N3 — the source-field catalog is immutable in place.
- RT-G022-N4 — the registry hash covers kernel identity.
- RT-G022-N6 — a bare ``date`` as ``as_of`` is a typed error.
- RT-G022-N7 — an empty cross-section is never eligible.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import cast

import pytest
from test_features_fixtures import (
    AS_OF,
    bar_knowledge,
    fundamental,
    price_bar,
    write_table,
)
from test_features_registry import toy_spec

from lasr.core.errors import TimeSemanticsError
from lasr.data.canonical.store import CanonicalStore
from lasr.data.point_in_time import PitQueryConfig, PitStore
from lasr.features.computation import (
    RawObservation,
)
from lasr.features.engine import FeatureEngine
from lasr.features.registry import FeatureRegistry

pytestmark = pytest.mark.unit

D_BAR = date(2021, 12, 20)
K_FY2020 = datetime(2021, 3, 31, 12, 0, tzinfo=UTC)
MICRO = timedelta(microseconds=1)


def _last_close_kernel(ctx, securities):
    out = {}
    frame = ctx.frame("prices_daily", keys={"security_id": securities})
    for record in frame.to_dict("records"):
        if record["close"] is not None:
            day = record["event_date"]
            out[str(record["security_id"])] = RawObservation(
                value=float(record["close"]),
                observation_time=datetime(day.year, day.month, day.day, tzinfo=UTC),
            )
    return out


def _latest_book_kernel(ctx, securities):
    out = {}
    frame = ctx.frame(
        "fundamentals", keys={"security_id": securities, "metric": "BOOK_VALUE"}
    )
    for record in frame.to_dict("records"):
        pe = record["period_end"]
        out[str(record["security_id"])] = RawObservation(
            value=float(record["value"]),
            observation_time=datetime(pe.year, pe.month, pe.day, tzinfo=UTC),
        )
    return out


def _price_engine(
    tmp_path, *, floor: timedelta | None, spec=None, kernel=_last_close_kernel
) -> tuple[FeatureEngine, PitStore]:
    store = CanonicalStore(tmp_path)
    ref = write_table(store, "prices_daily", [price_bar("SEC-A", D_BAR, close=100.0)])
    config = (
        PitQueryConfig(publication_lags={"prices_daily": floor})
        if floor is not None
        else PitQueryConfig()
    )
    pit = PitStore(store, dataset_ids={"prices_daily": ref.dataset_id}, config=config)
    registry = FeatureRegistry()
    registry.register(spec or toy_spec(), kernel)
    return FeatureEngine(registry, pit), pit


def _fundamentals_engine(
    tmp_path,
    *,
    floor: timedelta | None,
    spec_lag: timedelta,
    records=None,
    kernel=_latest_book_kernel,
    spec=None,
) -> tuple[FeatureEngine, PitStore]:
    store = CanonicalStore(tmp_path)
    ref = write_table(
        store,
        "fundamentals",
        records
        or [
            fundamental(
                "SEC-A", "BOOK_VALUE", "FY2020", date(2020, 12, 31), 500.0, K_FY2020
            )
        ],
    )
    config = (
        PitQueryConfig(publication_lags={"fundamentals": floor})
        if floor is not None
        else PitQueryConfig()
    )
    pit = PitStore(store, dataset_ids={"fundamentals": ref.dataset_id}, config=config)
    registry = FeatureRegistry()
    registry.register(
        spec
        or toy_spec(
            feature_id="toy_book",
            required_fields=("fundamentals.BOOK_VALUE",),
            publication_lag=spec_lag,
        ),
        kernel,
    )
    return FeatureEngine(registry, pit), pit


class TestRtG022B1EffectiveCutoffStamping:
    """RT-G022-B1 (blocking): the stamp must be the instant the store
    actually makes the inputs knowable, not raw kt + registry lag."""

    def test_price_floor_above_zero_registry_lag(self, tmp_path):
        """Audit repro B3, inverted: 5d configured floor on prices, spec
        lag 0. Stamp must be bar_kt + 5d (= 2021-12-25 21:00), and the
        SAME store must serve the bar at exactly that instant — the audit
        observed a raw-kt stamp at which it served ZERO rows."""
        engine, pit = _price_engine(tmp_path, floor=timedelta(days=5))
        (row,) = engine.compute("toy_close", 1, AS_OF, ["SEC-A"]).rows
        assert row.knowledge_time == bar_knowledge(D_BAR) + timedelta(days=5)
        served = pit.as_of_frame("prices_daily", row.knowledge_time)
        assert len(served) == 1  # the input row IS knowable at the stamp
        assert served.to_dict("records")[0]["close"] == 100.0
        # earliest honest instant: 1µs earlier the store serves nothing
        assert len(pit.as_of_frame("prices_daily", row.knowledge_time - MICRO)) == 0

    def test_vintaged_floor_above_registry_lag(self, tmp_path):
        """Audit repro B4: fundamentals floor 120d > spec lag 90d →
        effective 120d. Stamp = statement kt + 120d, and the same store
        (same config) serves the statement at the stamp, not before."""
        engine, pit = _fundamentals_engine(
            tmp_path, floor=timedelta(days=120), spec_lag=timedelta(days=90)
        )
        result = engine.compute("toy_book", 1, AS_OF, ["SEC-A"])
        assert result.values() == {"SEC-A": 500.0}
        (row,) = result.rows
        assert row.knowledge_time == K_FY2020 + timedelta(days=120)
        assert len(pit.as_of_frame("fundamentals", row.knowledge_time)) == 1
        assert len(pit.as_of_frame("fundamentals", row.knowledge_time - MICRO)) == 0

    def test_registry_lag_above_floor_still_governs(self, tmp_path):
        """The other side of max(): floor 30d < spec lag 90d → effective
        90d — the RT-G020-N1 floor semantics compose, the stamp never
        shortens below the registry lag."""
        engine, pit = _fundamentals_engine(
            tmp_path, floor=timedelta(days=30), spec_lag=timedelta(days=90)
        )
        (row,) = engine.compute("toy_book", 1, AS_OF, ["SEC-A"]).rows
        assert row.knowledge_time == K_FY2020 + timedelta(days=90)
        # knowable at the stamp under the feature's own requested lag too
        assert (
            len(
                pit.as_of_frame(
                    "fundamentals", row.knowledge_time, lag=timedelta(days=90)
                )
            )
            == 1
        )

    def test_no_floor_behavior_unchanged(self, tmp_path):
        """Default config (no floors): stamps are unchanged from the
        pre-remediation behavior (kt + registry lag)."""
        engine, _ = _price_engine(tmp_path, floor=None)
        (row,) = engine.compute("toy_close", 1, AS_OF, ["SEC-A"]).rows
        assert row.knowledge_time == bar_knowledge(D_BAR)

    def test_stamp_still_bounded_by_as_of(self, tmp_path):
        """CI-001 on the output survives the fix: effective-lag stamps
        can never exceed as_of (kt <= as_of - effective ⇒ stamp <= as_of),
        and a bar inside the floor window is simply not knowable."""
        floor = timedelta(days=5)
        engine, _ = _price_engine(tmp_path, floor=floor)
        # bar kt 2021-12-20 21:00 + 5d <= 2021-12-31 12:00 ✔ knowable
        result = engine.compute("toy_close", 1, AS_OF, ["SEC-A"])
        (row,) = result.rows
        assert row.knowledge_time <= AS_OF
        # at an as_of INSIDE the floor window the bar is invisible: no
        # rows, no stamp (the audit confirmed gating was already correct)
        inside = engine.compute(
            "toy_close", 1, bar_knowledge(D_BAR) + floor - MICRO, ["SEC-A"]
        )
        assert inside.rows == ()


class TestRtG022N1MetricKeySmuggling:
    def test_sneaky_metric_key_cannot_read_undeclared_rows(self, tmp_path):
        """Audit repro A5b: a key object with str()='BOOK_VALUE' but
        __eq__ matching 'TOT_ASSET' passes validation; the outgoing filter
        must carry the validated STRING, so only BOOK_VALUE rows are
        served (before the fix the kernel read TOT_ASSET's 1000.0)."""

        class SneakyMetric:
            def __str__(self) -> str:
                return "BOOK_VALUE"

            def __eq__(self, other: object) -> bool:
                return bool(other == "TOT_ASSET")

            def __hash__(self) -> int:
                return hash("TOT_ASSET")

        seen: dict[str, object] = {}

        def sneaky_kernel(ctx, securities):
            frame = ctx.frame(
                "fundamentals",
                keys={"security_id": securities, "metric": SneakyMetric()},
            )
            records = frame.to_dict("records")
            seen["metrics"] = {str(r["metric"]) for r in records}
            return {
                str(r["security_id"]): RawObservation(
                    value=float(cast(float, r["value"])),
                    observation_time=datetime(
                        r["period_end"].year,
                        r["period_end"].month,
                        r["period_end"].day,
                        tzinfo=UTC,
                    ),
                )
                for r in records
            }

        engine, _ = _fundamentals_engine(
            tmp_path,
            floor=None,
            spec_lag=timedelta(0),
            records=[
                fundamental(
                    "SEC-A", "BOOK_VALUE", "FY2020", date(2020, 12, 31), 500.0, K_FY2020
                ),
                fundamental(
                    "SEC-A", "TOT_ASSET", "FY2020", date(2020, 12, 31), 1000.0, K_FY2020
                ),
            ],
            kernel=sneaky_kernel,
            spec=toy_spec(
                feature_id="toy_book",
                required_fields=("fundamentals.BOOK_VALUE",),
                publication_lag=timedelta(0),
            ),
        )
        result = engine.compute("toy_book", 1, AS_OF, ["SEC-A"])
        assert seen["metrics"] == {"BOOK_VALUE"}  # never TOT_ASSET
        assert result.values() == {"SEC-A": 500.0}  # not the smuggled 1000.0


class TestRtG022N2MetricFrameColumns:
    def test_fundamentals_frame_drops_bookkeeping_columns(self, tmp_path):
        """Audit repro A8: ingestion_time (a post-as_of wall-clock stamp),
        report_date, knowledge_basis, unit, currency, consolidation_basis
        must not reach kernels; plumbing + period_end + value remain."""
        seen: dict[str, list[str]] = {}

        def observer(ctx, securities):
            frame = ctx.frame(
                "fundamentals",
                keys={"security_id": securities, "metric": "BOOK_VALUE"},
            )
            seen["columns"] = list(frame.columns)
            return {}

        engine, _ = _fundamentals_engine(
            tmp_path,
            floor=None,
            spec_lag=timedelta(0),
            kernel=observer,
            spec=toy_spec(
                feature_id="toy_book",
                required_fields=("fundamentals.BOOK_VALUE",),
                publication_lag=timedelta(0),
            ),
        )
        engine.compute("toy_book", 1, AS_OF, ["SEC-A"])
        assert seen["columns"] == [
            "security_id",
            "metric",
            "fiscal_period",
            "period_end",
            "knowledge_time",
            "vintage_seq",
            "value",
        ]
        assert "ingestion_time" not in seen["columns"]


class TestRtG022N3CatalogImmutability:
    def test_metric_ids_cannot_be_mutated_in_place(self):
        """Audit repro A6: poisoning catalog.metric_ids in place must
        raise; with_metrics (copy-on-extend) is the only extension path."""
        registry = FeatureRegistry()
        with pytest.raises(TypeError):
            registry.catalog.metric_ids["fundamentals"] = frozenset(  # type: ignore[index]
                {"SECRET_METRIC"}
            )
        # the sanctioned path still works and leaves the original intact
        extended = registry.catalog.with_metrics("fundamentals", {"OCF"})
        assert "OCF" in extended.metric_ids["fundamentals"]
        assert "OCF" not in registry.catalog.metric_ids["fundamentals"]


class TestRtG022N4KernelIdentityInHash:
    def test_swapped_kernels_hash_apart(self):
        """Audit repro F4: identical specs + lists but different kernels
        must not hash identically."""

        def kernel_a(ctx, securities):
            return {}

        def kernel_b(ctx, securities):
            return {}

        r_a, r_b, r_a2 = FeatureRegistry(), FeatureRegistry(), FeatureRegistry()
        r_a.register(toy_spec(), kernel_a)
        r_b.register(toy_spec(), kernel_b)
        r_a2.register(toy_spec(), kernel_a)
        assert r_a.registry_hash() != r_b.registry_hash()
        assert r_a.registry_hash() == r_a2.registry_hash()  # same kernel


class TestRtG022N6TypedDateRefusal:
    def test_bare_date_as_of_is_typed_error(self, tmp_path):
        """Audit repro A3: date(...) must raise TimeSemanticsError, not
        AttributeError — at the engine AND at a kernel's trailing query."""
        engine, _ = _price_engine(tmp_path, floor=None)
        with pytest.raises(TimeSemanticsError, match="tz-aware datetime"):
            engine.compute("toy_close", 1, date(2021, 12, 31), ["SEC-A"])  # type: ignore[arg-type]

        def date_query_kernel(ctx, securities):
            ctx.frame(
                "prices_daily",
                keys={"security_id": securities},
                as_of=date(2021, 12, 1),  # type: ignore[arg-type]
            )
            return {}

        registry = FeatureRegistry()
        registry.register(toy_spec(feature_id="toy_date"), date_query_kernel)
        store = CanonicalStore(tmp_path / "ctx")
        ref = write_table(store, "prices_daily", [price_bar("SEC-A", D_BAR, close=1.0)])
        engine2 = FeatureEngine(
            registry, PitStore(store, dataset_ids={"prices_daily": ref.dataset_id})
        )
        with pytest.raises(TimeSemanticsError, match="tz-aware datetime"):
            engine2.compute("toy_date", 1, AS_OF, ["SEC-A"])


class TestRtG022N7EmptyNeverEligible:
    def test_zero_min_coverage_with_zero_rows_is_ineligible(self, tmp_path):
        """Audit repro E3: min_coverage=0.0 + empty kernel output must not
        yield eligible=True with zero rows (silent-empty discipline)."""

        def empty_kernel(ctx, securities):
            ctx.frame("prices_daily", keys={"security_id": securities})
            return {}

        engine, _ = _price_engine(
            tmp_path,
            floor=None,
            spec=toy_spec(min_coverage=0.0),
            kernel=empty_kernel,
        )
        result = engine.compute("toy_close", 1, AS_OF, ["SEC-A"])
        assert result.rows == ()
        assert not result.eligible

    def test_zero_min_coverage_with_rows_stays_eligible(self, tmp_path):
        engine, _ = _price_engine(tmp_path, floor=None, spec=toy_spec(min_coverage=0.0))
        result = engine.compute("toy_close", 1, AS_OF, ["SEC-A", "SEC-MISSING"])
        assert result.values() == {"SEC-A": 100.0}
        assert result.eligible  # 0.5 >= 0.0 with a non-empty cross-section
