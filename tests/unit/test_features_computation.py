"""FeatureContext + FeatureEngine enforcement tests (G022).

Structural CI bindings exercised with toy features over a real PitStore:

- CI-001 — the context pins every read to ``knowledge_time <= as_of``;
  a forward-looking per-query ``as_of`` is a typed error;
- CI-004(b) — trailing as-of queries are permitted (window statistics);
- CI-005 — the registry publication lag gates vintaged tables and shows up
  in the stored row's ``knowledge_time`` (= max input knowledge + lag);
- CI-021 — non-finite kernel outputs are dropped (exclude, never impute);
- CI-043 — engine output is invariant to securities/mapping iteration
  order and canonical-sorted by security_id;
- MP §18 — undeclared source table / metric reads are refused at run time,
  matching the registration-time refusal.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from test_features_fixtures import (
    AS_OF,
    bar_knowledge,
    build_engine,
    fundamental,
    price_bar,
)
from test_features_registry import toy_spec

from lasr.core.errors import TimeSemanticsError
from lasr.data.canonical.store import CanonicalStore
from lasr.data.point_in_time import PitStore
from lasr.features.computation import (
    FeatureComputationError,
    RawObservation,
)
from lasr.features.engine import FeatureEngine
from lasr.features.registry import FeatureRegistry, FeatureRegistryError

pytestmark = pytest.mark.unit

D = date(2021, 12, 30)


def _last_close_kernel(ctx, securities):
    """Toy kernel: last knowable close per security."""
    frame = ctx.frame("prices_daily", keys={"security_id": securities})
    out = {}
    for record in frame.to_dict("records"):
        sid = str(record["security_id"])
        if record["close"] is not None:
            out[sid] = RawObservation(
                value=float(record["close"]),
                observation_time=datetime(
                    record["event_date"].year,
                    record["event_date"].month,
                    record["event_date"].day,
                    tzinfo=UTC,
                ),
            )
    return out


def _toy_engine(tmp_path, kernel, spec=None):
    registry = FeatureRegistry()
    registry.register(spec or toy_spec(), kernel)
    return build_engine(
        tmp_path,
        prices=[price_bar("SEC-A", D, close=42.0), price_bar("SEC-B", D, close=7.0)],
        registry=registry,
    )


class TestContextEnforcement:
    def test_undeclared_table_read_refused(self, tmp_path):
        """MP §18 at run time: a close-only feature cannot read
        fundamentals."""

        def sneaky(ctx, securities):
            ctx.frame("fundamentals", keys={"metric": "BOOK_VALUE"})
            return {}

        engine = _toy_engine(tmp_path, sneaky)
        with pytest.raises(FeatureComputationError, match="undeclared source table"):
            engine.compute("toy_close", 1, AS_OF, ["SEC-A"])

    def test_forward_as_of_refused(self, tmp_path):
        """CI-001: a kernel cannot ask for a frame beyond the computation
        as_of — not even by one microsecond."""

        def forward_looking(ctx, securities):
            ctx.frame(
                "prices_daily",
                keys={"security_id": securities},
                as_of=ctx.as_of + timedelta(microseconds=1),
            )
            return {}

        engine = _toy_engine(tmp_path, forward_looking)
        with pytest.raises(FeatureComputationError, match="CI-001"):
            engine.compute("toy_close", 1, AS_OF, ["SEC-A"])

    def test_trailing_as_of_allowed(self, tmp_path):
        """CI-004(b): trailing window queries (earlier as_of) are legal."""

        def trailing(ctx, securities):
            frame = ctx.frame(
                "prices_daily",
                keys={"security_id": securities},
                as_of=ctx.as_of - timedelta(days=7),
            )
            assert len(frame) == 0  # bars knowable only after D - 7d
            return _last_close_kernel(ctx, securities)

        engine = _toy_engine(tmp_path, trailing)
        result = engine.compute("toy_close", 1, AS_OF, ["SEC-A"])
        assert result.values() == {"SEC-A": 42.0}

    def test_undeclared_columns_invisible(self, tmp_path):
        """A close-only feature sees close + plumbing, never volume/mcap."""
        seen: dict[str, object] = {}

        def observer(ctx, securities):
            frame = ctx.frame("prices_daily", keys={"security_id": securities})
            seen["columns"] = list(frame.columns)
            return {}

        engine = _toy_engine(tmp_path, observer)
        engine.compute("toy_close", 1, AS_OF, ["SEC-A"])
        assert seen["columns"] == [
            "security_id",
            "event_date",
            "knowledge_time",
            "close",
        ]

    def test_metric_table_requires_declared_metric_filter(self, tmp_path):
        spec = toy_spec(
            feature_id="toy_book",
            required_fields=("fundamentals.BOOK_VALUE",),
        )

        def no_filter(ctx, securities):
            ctx.frame("fundamentals", keys={"security_id": securities})
            return {}

        registry = FeatureRegistry()
        registry.register(spec, no_filter)
        engine = build_engine(
            tmp_path,
            fundamentals=[
                fundamental(
                    "SEC-A",
                    "BOOK_VALUE",
                    "FY2020",
                    date(2020, 12, 31),
                    500.0,
                    datetime(2021, 3, 31, 12, 0, tzinfo=UTC),
                )
            ],
            registry=registry,
        )
        with pytest.raises(FeatureComputationError, match="must filter 'metric'"):
            engine.compute("toy_book", 1, AS_OF, ["SEC-A"])

    def test_undeclared_metric_read_refused(self, tmp_path):
        spec = toy_spec(
            feature_id="toy_book",
            required_fields=("fundamentals.BOOK_VALUE",),
        )

        def wrong_metric(ctx, securities):
            ctx.frame(
                "fundamentals",
                keys={"security_id": securities, "metric": "TOT_ASSET"},
            )
            return {}

        registry = FeatureRegistry()
        registry.register(spec, wrong_metric)
        engine = build_engine(
            tmp_path,
            fundamentals=[
                fundamental(
                    "SEC-A",
                    "BOOK_VALUE",
                    "FY2020",
                    date(2020, 12, 31),
                    500.0,
                    datetime(2021, 3, 31, 12, 0, tzinfo=UTC),
                )
            ],
            registry=registry,
        )
        with pytest.raises(FeatureComputationError, match="undeclared metric"):
            engine.compute("toy_book", 1, AS_OF, ["SEC-A"])

    def test_naive_as_of_refused(self, tmp_path):
        engine = _toy_engine(tmp_path, _last_close_kernel)
        with pytest.raises(TimeSemanticsError, match="naive"):
            engine.compute("toy_close", 1, datetime(2021, 12, 31), ["SEC-A"])


class TestEngineGuards:
    def test_unknown_feature_typed_error(self, tmp_path):
        engine = _toy_engine(tmp_path, _last_close_kernel)
        with pytest.raises(FeatureRegistryError, match="unknown feature"):
            engine.compute("ghost", 1, AS_OF, ["SEC-A"])

    def test_empty_security_set_refused(self, tmp_path):
        engine = _toy_engine(tmp_path, _last_close_kernel)
        with pytest.raises(FeatureComputationError, match="empty security set"):
            engine.compute("toy_close", 1, AS_OF, [])

    def test_fabricated_security_refused(self, tmp_path):
        def fabricator(ctx, securities):
            out = _last_close_kernel(ctx, securities)
            out["SEC-GHOST"] = RawObservation(
                value=1.0, observation_time=AS_OF - timedelta(days=1)
            )
            return out

        engine = _toy_engine(tmp_path, fabricator)
        with pytest.raises(FeatureComputationError, match="never requested"):
            engine.compute("toy_close", 1, AS_OF, ["SEC-A"])

    def test_value_without_inputs_refused(self, tmp_path):
        """A kernel that emits values without reading any knowledge-stamped
        row is fabricating (no PIT lineage)."""

        def fabricate_from_nothing(ctx, securities):
            return {
                "SEC-A": RawObservation(
                    value=1.0, observation_time=AS_OF - timedelta(days=1)
                )
            }

        engine = _toy_engine(tmp_path, fabricate_from_nothing)
        with pytest.raises(FeatureComputationError, match="without reading"):
            engine.compute("toy_close", 1, AS_OF, ["SEC-A"])

    def test_nonfinite_values_dropped_per_missing_policy(self, tmp_path):
        """CI-021: NaN output -> excluded (absent), the rest survive."""

        def half_nan(ctx, securities):
            out = _last_close_kernel(ctx, securities)
            out["SEC-B"] = RawObservation(
                value=float("nan"),
                observation_time=out["SEC-B"].observation_time,
            )
            return out

        engine = _toy_engine(tmp_path, half_nan)
        result = engine.compute("toy_close", 1, AS_OF, ["SEC-A", "SEC-B"])
        assert result.values() == {"SEC-A": 42.0}
        assert result.coverage == pytest.approx(0.5)

    def test_coverage_gate_boundary(self, tmp_path):
        """Eligibility: coverage == min_coverage passes; below fails."""
        engine = _toy_engine(tmp_path, _last_close_kernel)
        # 2 of 2 covered, min 0.5 -> eligible
        full = engine.compute("toy_close", 1, AS_OF, ["SEC-A", "SEC-B"])
        assert full.coverage == 1.0 and full.eligible
        # 2 of 4 covered = exactly 0.5 -> eligible (>= gate)
        at_gate = engine.compute(
            "toy_close", 1, AS_OF, ["SEC-A", "SEC-B", "SEC-X", "SEC-Y"]
        )
        assert at_gate.coverage == pytest.approx(0.5) and at_gate.eligible
        # 2 of 5 covered = 0.4 -> ineligible, rows still carried
        below = engine.compute(
            "toy_close", 1, AS_OF, ["SEC-A", "SEC-B", "SEC-X", "SEC-Y", "SEC-Z"]
        )
        assert below.coverage == pytest.approx(0.4)
        assert not below.eligible
        assert below.values() == {"SEC-A": 42.0, "SEC-B": 7.0}


class TestKnowledgeStamping:
    def test_row_knowledge_is_max_input_knowledge(self, tmp_path):
        """Unlagged price feature: stored knowledge_time = the latest bar
        knowledge the computation saw (conservative cross-sectional max)."""
        engine = _toy_engine(tmp_path, _last_close_kernel)
        result = engine.compute("toy_close", 1, AS_OF, ["SEC-A", "SEC-B"])
        assert result.max_input_knowledge_time == bar_knowledge(D)
        for row in result.rows:
            assert row.knowledge_time == bar_knowledge(D)
            assert row.knowledge_time <= AS_OF  # CI-001 on the stored row

    def test_ci005_lag_shifts_visibility_and_stamp(self, tmp_path):
        """CI-005 with a 30d registry lag on fundamentals: a statement with
        knowledge inside (as_of-30d, as_of] is invisible; the stored row's
        knowledge_time = input knowledge + 30d."""
        lag = timedelta(days=30)
        spec = toy_spec(
            feature_id="toy_book",
            required_fields=("fundamentals.BOOK_VALUE",),
            publication_lag=lag,
        )

        def latest_book(ctx, securities):
            frame = ctx.frame(
                "fundamentals",
                keys={"security_id": securities, "metric": "BOOK_VALUE"},
            )
            out = {}
            for record in frame.to_dict("records"):
                out[str(record["security_id"])] = RawObservation(
                    value=float(record["value"]),
                    observation_time=datetime(
                        record["period_end"].year,
                        record["period_end"].month,
                        record["period_end"].day,
                        tzinfo=UTC,
                    ),
                )
            return out

        k_old = datetime(2021, 3, 31, 12, 0, tzinfo=UTC)
        k_recent = AS_OF - timedelta(days=10)  # inside the 30d lag window
        registry = FeatureRegistry()
        registry.register(spec, latest_book)
        engine = build_engine(
            tmp_path,
            fundamentals=[
                fundamental(
                    "SEC-A", "BOOK_VALUE", "FY2020", date(2020, 12, 31), 500.0, k_old
                ),
                fundamental(
                    "SEC-A",
                    "BOOK_VALUE",
                    "FY2020",
                    date(2020, 12, 31),
                    999.0,
                    k_recent,
                    vintage_seq=1,
                ),
            ],
            registry=registry,
        )
        result = engine.compute("toy_book", 1, AS_OF, ["SEC-A"])
        # the 999 restatement is NOT knowable through the lag (CI-005)
        assert result.values() == {"SEC-A": 500.0}
        (row,) = result.rows
        assert row.knowledge_time == k_old + lag  # input knowledge + lag
        # once as_of clears k_recent + lag, the restatement takes over
        later = engine.compute(
            "toy_book", 1, k_recent + lag + timedelta(seconds=1), ["SEC-A"]
        )
        assert later.values() == {"SEC-A": 999.0}


class TestDeterminism:
    def test_output_sorted_and_order_invariant(self, tmp_path):
        """CI-043: same result for permuted security order and repeated
        runs; rows canonically sorted by security_id."""
        engine = _toy_engine(tmp_path, _last_close_kernel)
        r1 = engine.compute("toy_close", 1, AS_OF, ["SEC-B", "SEC-A"])
        r2 = engine.compute("toy_close", 1, AS_OF, ["SEC-A", "SEC-B"])
        assert r1.rows == r2.rows
        assert [row.security_id for row in r1.rows] == ["SEC-A", "SEC-B"]

    def test_kernel_mapping_order_irrelevant(self, tmp_path):
        """The engine sorts the kernel's mapping — reversed insertion order
        produces identical rows."""

        def reversed_kernel(ctx, securities):
            out = _last_close_kernel(ctx, securities)
            return dict(reversed(list(out.items())))

        registry = FeatureRegistry()
        registry.register(toy_spec(feature_id="fwd"), _last_close_kernel)
        registry.register(toy_spec(feature_id="rev"), reversed_kernel)
        engine = build_engine(
            tmp_path,
            prices=[
                price_bar("SEC-A", D, close=42.0),
                price_bar("SEC-B", D, close=7.0),
            ],
            registry=registry,
        )
        fwd = engine.compute("fwd", 1, AS_OF, ["SEC-A", "SEC-B"])
        rev = engine.compute("rev", 1, AS_OF, ["SEC-A", "SEC-B"])
        assert [(r.security_id, r.value, r.knowledge_time) for r in fwd.rows] == [
            (r.security_id, r.value, r.knowledge_time) for r in rev.rows
        ]


class TestListComputation:
    def test_compute_list_preserves_list_order(self, tmp_path):
        registry = FeatureRegistry()
        registry.register(toy_spec(feature_id="f_b"), _last_close_kernel)
        registry.register(toy_spec(feature_id="f_a"), _last_close_kernel)
        registry.define_list("toy_list", [("f_b", 1), ("f_a", 1)])
        engine = build_engine(
            tmp_path,
            prices=[price_bar("SEC-A", D, close=42.0)],
            registry=registry,
        )
        results = engine.compute_list("toy_list", AS_OF, ["SEC-A"])
        assert [r.spec.feature_id for r in results] == ["f_b", "f_a"]

    def test_unknown_list_typed_error(self, tmp_path):
        engine = _toy_engine(tmp_path, _last_close_kernel)
        with pytest.raises(FeatureRegistryError, match="unknown feature list"):
            engine.compute_list("p1_fig11_us70", AS_OF, ["SEC-A"])


class TestContextDirectBounds:
    def test_ci001_boundary_exactly_le(self, tmp_path):
        """CI-001 at the context level: a bar with knowledge == as_of is
        knowable; one microsecond later it is not."""
        store = CanonicalStore(tmp_path)
        from test_features_fixtures import write_table

        micro = timedelta(microseconds=1)
        ref = write_table(
            store,
            "prices_daily",
            [
                price_bar("SEC-A", D, close=1.0, knowledge_time=AS_OF),
                price_bar("SEC-B", D, close=2.0, knowledge_time=AS_OF + micro),
            ],
        )
        pit = PitStore(store, dataset_ids={"prices_daily": ref.dataset_id})
        registry = FeatureRegistry()
        registry.register(toy_spec(), _last_close_kernel)
        engine = FeatureEngine(registry, pit)
        at = engine.compute("toy_close", 1, AS_OF, ["SEC-A", "SEC-B"])
        assert at.values() == {"SEC-A": 1.0}  # exclusion non-empty (teeth)
        after = engine.compute("toy_close", 1, AS_OF + micro, ["SEC-A", "SEC-B"])
        assert after.values() == {"SEC-A": 1.0, "SEC-B": 2.0}
