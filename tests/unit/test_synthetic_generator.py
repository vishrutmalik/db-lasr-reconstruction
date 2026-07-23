"""Generator component unit tests (G019): determinism, churn intervals,
vintage assembly, action mechanics on generated worlds, error seeding.

Uses a small baseline world (kitchen sink: churn, actions, restatements,
estimates) so every emission path executes quickly.
"""

from __future__ import annotations

import itertools
from datetime import date, datetime, timedelta

import pytest

from lasr.data.schemas.base import validate_rows
from lasr.data.schemas.raw_registry import RAW_SCHEMAS
from lasr.data.synthetic import (
    ScenarioConfig,
    SyntheticWorld,
    content_hash_rows,
    generate_world,
    latest_vintage_view,
)
from lasr.data.synthetic.world import Row

pytestmark = pytest.mark.unit

SMALL_BASELINE = ScenarioConfig(
    scenario_id="baseline", seed=424242, n_securities=16, n_years=3
)

#: World tables that hold exactly one row per raw-schema primary key. The
#: vintage-carrying tables intentionally hold the FULL history — multiple
#: knowledge times per event key: fundamentals/estimates (restatements,
#: revisions) and, since RT-G019-1, the interval tables (master,
#: classifications, membership) whose closures are separate later-stamped
#: vintage rows. The provider collapses them on its fetch surface.
PK_UNIQUE_TABLES = (
    "raw_market_daily",
    "raw_market_metrics",
    "raw_corporate_actions",
    "raw_borrow_daily",
    "raw_fx_rates",
    "raw_trading_calendars",
)

#: Interval tables: (raw table, primary key columns).
INTERVAL_VINTAGE_TABLES = (
    ("raw_security_master", ("ticker", "exchange"), "delisting_date"),
    ("raw_classifications", ("ticker", "exchange", "scheme"), "valid_to"),
    (
        "raw_universe_membership",
        ("universe_id", "ticker", "exchange", "valid_from"),
        "valid_to",
    ),
)


@pytest.fixture(scope="module")
def world() -> SyntheticWorld:
    return generate_world(SMALL_BASELINE)


def rows_by_ticker(rows: tuple[Row, ...]) -> dict[str, list[Row]]:
    grouped: dict[str, list[Row]] = {}
    for row in rows:
        grouped.setdefault(str(row["ticker"]), []).append(row)
    return grouped


class TestDeterminism:
    def test_identical_config_and_seed_byte_identical(
        self, world: SyntheticWorld
    ) -> None:
        again = generate_world(SMALL_BASELINE)
        assert again.world_hash() == world.world_hash()
        assert again.content_hashes() == world.content_hashes()

    def test_different_seed_different_world(self, world: SyntheticWorld) -> None:
        other = generate_world(
            ScenarioConfig("baseline", seed=424243, n_securities=16, n_years=3)
        )
        assert other.world_hash() != world.world_hash()

    def test_params_insertion_order_irrelevant(self) -> None:
        a = ScenarioConfig(
            "baseline",
            seed=99,
            n_securities=12,
            n_years=2,
            params={"restatement_fraction": 0.2, "missing_fraction": 0.05},
        )
        b = ScenarioConfig(
            "baseline",
            seed=99,
            n_securities=12,
            n_years=2,
            params={"missing_fraction": 0.05, "restatement_fraction": 0.2},
        )
        assert generate_world(a).world_hash() == generate_world(b).world_hash()

    def test_content_hash_is_row_order_insensitive(self, world: SyntheticWorld) -> None:
        rows = list(world.table("raw_market_daily"))
        assert content_hash_rows(rows) == content_hash_rows(list(reversed(rows)))


class TestSchemasAndRows:
    @pytest.mark.parametrize("table", PK_UNIQUE_TABLES)
    def test_tables_validate_against_raw_schemas(
        self, world: SyntheticWorld, table: str
    ) -> None:
        validate_rows(RAW_SCHEMAS[table], world.table(table))

    @pytest.mark.parametrize("table", sorted(RAW_SCHEMAS))
    def test_row_models_accept_sampled_rows(
        self, world: SyntheticWorld, table: str
    ) -> None:
        rows = world.table(table)
        for row in rows[:: max(1, len(rows) // 50)]:
            RAW_SCHEMAS[table].row_model(**row)

    @pytest.mark.parametrize(("table", "pk", "closure"), INTERVAL_VINTAGE_TABLES)
    def test_interval_tables_validate_in_their_latest_view(
        self, world: SyntheticWorld, table: str, pk: tuple[str, ...], closure: str
    ) -> None:
        validate_rows(RAW_SCHEMAS[table], latest_vintage_view(world.table(table), pk))

    @pytest.mark.parametrize(("table", "pk", "closure"), INTERVAL_VINTAGE_TABLES)
    def test_interval_closures_are_later_stamped_vintages(
        self, world: SyntheticWorld, table: str, pk: tuple[str, ...], closure: str
    ) -> None:
        """RT-G019-1: the open-stamped row NEVER carries the closure; the
        closure row's knowledge_time is at/after the closure date itself."""
        groups: dict[tuple[object, ...], list[Row]] = {}
        for row in world.table(table):
            groups.setdefault(tuple(row.get(c) for c in pk), []).append(row)
        closures = 0
        for key, rows in groups.items():
            rows.sort(key=lambda r: r["knowledge_time"])  # type: ignore[arg-type,return-value]
            assert rows[0][closure] is None, (table, key)
            assert len(rows) <= 2, (table, key)
            if len(rows) == 2:
                closures += 1
                closed = rows[1][closure]
                stamp = rows[1]["knowledge_time"]
                assert isinstance(closed, date) and isinstance(stamp, datetime)
                assert stamp.date() >= closed, (table, key)
        assert closures > 0, f"{table}: baseline must contain closures"

    def test_every_family_table_is_populated(self, world: SyntheticWorld) -> None:
        for name, rows in world.tables.items():
            assert rows, f"baseline world must populate {name}"


class TestChurnIntervals:
    def test_no_bars_outside_listing_interval(self, world: SyntheticWorld) -> None:
        """Skill invariant: no price after delisting; none before listing."""
        master = {
            str(r["ticker"]): r
            for r in latest_vintage_view(
                world.table("raw_security_master"), ("ticker", "exchange")
            )
        }
        for ticker, bars in rows_by_ticker(world.table("raw_market_daily")).items():
            listing = master[ticker]["listing_date"]
            delisting = master[ticker]["delisting_date"]
            dates = [r["event_date"] for r in bars]
            assert min(dates) == listing  # type: ignore[type-var]
            if delisting is not None:
                assert max(dates) == delisting  # type: ignore[type-var]

    def test_membership_intervals_within_listing_and_non_overlapping(
        self, world: SyntheticWorld
    ) -> None:
        master = {
            str(r["ticker"]): r
            for r in latest_vintage_view(
                world.table("raw_security_master"), ("ticker", "exchange")
            )
        }
        by_ticker = rows_by_ticker(
            list(
                latest_vintage_view(
                    world.table("raw_universe_membership"),
                    ("universe_id", "ticker", "exchange", "valid_from"),
                )
            )
        )
        for ticker, intervals in by_ticker.items():
            listing = master[ticker]["listing_date"]
            assert isinstance(listing, date)
            spans = sorted(
                (r["valid_from"], r["valid_to"])
                for r in intervals  # type: ignore[misc]
            )
            for valid_from, valid_to in spans:
                assert valid_from >= listing
                if valid_to is not None:
                    assert valid_to >= valid_from
            for (_, prev_to), (next_from, _) in itertools.pairwise(spans):
                assert prev_to is not None and next_from > prev_to, (
                    f"{ticker}: overlapping membership intervals"
                )

    def test_terminated_names_carry_delisting_action_and_truth(
        self, world: SyntheticWorld
    ) -> None:
        truths = {(t.ticker, t.exchange): t for t in world.sidecar.delistings}
        actions = {
            (str(r["ticker"]), str(r["exchange"])): r
            for r in world.table("raw_corporate_actions")
            if r["action_type"] in ("delisting", "merger")
        }
        for key, truth in truths.items():
            action = actions[key]
            assert action["terminal_return"] == pytest.approx(truth.terminal_return)
            assert str(action["effective_date"]) == truth.event_date


class TestVintages:
    def test_restated_rows_have_strictly_increasing_knowledge_times(
        self, world: SyntheticWorld
    ) -> None:
        """U2 substrate: per event key, vintages are ordered by knowledge."""
        groups: dict[tuple[object, ...], list[Row]] = {}
        for row in world.table("raw_fundamentals"):
            key = (row["ticker"], row["exchange"], row["metric"], row["fiscal_period"])
            groups.setdefault(key, []).append(row)
        restated = 0
        for key, rows in groups.items():
            if len(rows) == 1:
                continue
            restated += 1
            stamps = [row["knowledge_time"] for row in rows]
            assert stamps == sorted(stamps), key  # type: ignore[type-var]
            assert len(set(stamps)) == len(stamps), key
            versions = [row["version_type"] for row in rows]
            assert versions[0] == "as_reported"
            assert versions[-1] == "restated"
        assert restated > 0, "baseline must contain restatements (MP §17)"

    def test_publication_lag_rule(self, world: SyntheticWorld) -> None:
        """CI-005 structural: knowledge_time >= period_end + configured lag
        for first vintages (A-002 made literal)."""
        lag = timedelta(days=world.sidecar.fundamental_lag_days)
        for row in world.table("raw_fundamentals"):
            if row["version_type"] != "as_reported":
                continue
            knowledge = row["knowledge_time"]
            period_end = row["period_end"]
            assert isinstance(knowledge, datetime) and isinstance(period_end, date)
            assert knowledge.date() >= period_end + lag
            assert row["report_date"] == knowledge.date()

    def test_accounting_identity_holds_within_each_vintage(
        self, world: SyntheticWorld
    ) -> None:
        """EPS * shares == NETINC (millions), for a split-free security."""
        bars = rows_by_ticker(world.table("raw_market_daily"))
        split_tickers = {
            str(r["ticker"])
            for r in world.table("raw_corporate_actions")
            if r["action_type"] == "split"
        }
        by_key: dict[tuple[object, ...], dict[str, float]] = {}
        for row in world.table("raw_fundamentals"):
            ticker = str(row["ticker"])
            if ticker in split_tickers or ticker not in bars:
                continue
            key = (ticker, row["fiscal_period"], row["knowledge_time"])
            by_key.setdefault(key, {})[str(row["metric"])] = float(row["value"])  # type: ignore[arg-type]
        checked = 0
        for (ticker, _, _), values in by_key.items():
            if "EPS" not in values or "NETINC" not in values:
                continue
            shares = float(bars[str(ticker)][0]["shares_outstanding"])  # type: ignore[arg-type]
            assert values["EPS"] * shares == pytest.approx(
                values["NETINC"] * 1e6, rel=1e-9
            )
            checked += 1
        assert checked > 10

    def test_missing_values_exist(self, world: SyntheticWorld) -> None:
        """MP §17 requires real absences, not imputed placeholders."""
        keys = {
            (row["ticker"], row["metric"], row["fiscal_period"])
            for row in world.table("raw_fundamentals")
            if row["metric"] in ("BOOKEQ", "EPS", "NETINC", "REVENUE", "TOTASSET")
        }
        tickers = {k[0] for k in keys}
        periods = {k[2] for k in keys}
        full_grid = len(tickers) * 5 * len(periods)
        assert len(keys) < full_grid, "expected missing fundamental cells"


class TestEstimates:
    def test_revision_histories_ordered_per_key(self, world: SyntheticWorld) -> None:
        groups: dict[tuple[object, ...], list[Row]] = {}
        for row in world.table("raw_estimates"):
            key = (row["ticker"], row["metric"], row["forecast_period"])
            groups.setdefault(key, []).append(row)
        multi = 0
        for key, rows in groups.items():
            stamps = [row["knowledge_time"] for row in rows]
            assert stamps == sorted(stamps), key  # type: ignore[type-var]
            if len(rows) > 1:
                multi += 1
                values = {float(row["value"]) for row in rows}  # type: ignore[arg-type]
                assert len(values) > 1, "revisions must actually revise"
        assert multi > 0, "estimate revision histories required (MP §17)"

    def test_fy1_precedes_fy2(self, world: SyntheticWorld) -> None:
        by_stamp: dict[tuple[object, ...], dict[str, date]] = {}
        for row in world.table("raw_estimates"):
            key = (row["ticker"], row["metric"], row["knowledge_time"])
            end = row["period_end"]
            assert isinstance(end, date)
            by_stamp.setdefault(key, {})[str(row["forecast_period"])] = end
        for ends in by_stamp.values():
            if "FY1" in ends and "FY2" in ends:
                assert ends["FY1"] < ends["FY2"]


class TestActionMechanics:
    def test_split_halves_raw_close_but_not_market_cap(
        self, world: SyntheticWorld
    ) -> None:
        """CI-050 spirit on a generated world: raw close jumps by ~1/2 at a
        2:1 split while market cap moves only by the price return."""
        splits = [
            r
            for r in world.table("raw_corporate_actions")
            if r["action_type"] == "split" and r["ratio_num"] == 2.0
        ]
        assert splits, "baseline schedules 2:1 splits"
        bars = rows_by_ticker(world.table("raw_market_daily"))
        for action in splits:
            series = bars[str(action["ticker"])]
            idx = next(
                i
                for i, row in enumerate(series)
                if row["event_date"] == action["effective_date"]
            )
            prev, curr = series[idx - 1], series[idx]
            close_ratio = float(curr["close"]) / float(prev["close"])  # type: ignore[arg-type]
            cap_ratio = float(curr["market_cap"]) / float(prev["market_cap"])  # type: ignore[arg-type]
            assert close_ratio < 0.75, "raw close must show the split"
            assert 2.0 * close_ratio == pytest.approx(cap_ratio, rel=1e-9)
            assert abs(cap_ratio - 1.0) < 0.5, "market cap must NOT halve"
            shares_ratio = float(curr["shares_outstanding"]) / float(
                prev["shares_outstanding"]  # type: ignore[arg-type]
            )
            assert shares_ratio == pytest.approx(2.0)

    def test_symbol_change_preserves_the_bar_series(
        self, world: SyntheticWorld
    ) -> None:
        changes = [
            r
            for r in world.table("raw_corporate_actions")
            if r["action_type"] == "symbol_change"
        ]
        assert changes, "baseline schedules a symbol change"
        bars = rows_by_ticker(world.table("raw_market_daily"))
        master = {
            str(r["ticker"]): r
            for r in latest_vintage_view(
                world.table("raw_security_master"), ("ticker", "exchange")
            )
        }
        for action in changes:
            old, new = str(action["ticker"]), str(action["successor_ticker"])
            assert master[old]["delisting_date"] is not None
            assert master[new]["listing_date"] == action["effective_date"]
            last_old = max(r["event_date"] for r in bars[old])  # type: ignore[type-var]
            first_new = min(r["event_date"] for r in bars[new])  # type: ignore[type-var]
            assert last_old < first_new  # type: ignore[operator]
            assert first_new == action["effective_date"]

    def test_dividend_amounts_match_the_ledger(self, world: SyntheticWorld) -> None:
        ledger = {
            (row.ticker, row.event_date): row
            for row in world.sidecar.ledger
            if row.dividend_per_share > 0
        }
        assert ledger, "baseline pays dividends"
        for action in world.table("raw_corporate_actions"):
            if action["action_type"] != "cash_dividend":
                continue
            key = (str(action["ticker"]), str(action["effective_date"]))
            assert key in ledger
            assert float(action["amount"]) == pytest.approx(  # type: ignore[arg-type]
                ledger[key].dividend_per_share
            )


class TestSidecarBasics:
    def test_a003_banner_present(self, world: SyntheticWorld) -> None:
        assert world.sidecar.synthetic is True
        assert "A-003" in world.sidecar.a003_banner
        assert "never" in world.sidecar.a003_banner

    def test_config_echo_and_pass_bands(self, world: SyntheticWorld) -> None:
        sc = world.sidecar
        assert sc.scenario_id == "baseline"
        assert sc.seed == SMALL_BASELINE.seed
        assert sc.n_securities == 16
        assert len(sc.period_dates) == SMALL_BASELINE.n_periods
        assert sc.pass_bands["se_period_ic"] == pytest.approx(16**-0.5)
        assert sc.pass_bands["z"] > 0

    def test_feature_truth_paths_cover_all_decision_periods(
        self, world: SyntheticWorld
    ) -> None:
        for truth in world.sidecar.features:
            assert len(truth.rho_path) == SMALL_BASELINE.n_periods - 1
