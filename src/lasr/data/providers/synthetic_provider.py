"""Synthetic provider: the FULL_VINTAGES DataProvider over generated worlds.

# arch: provider_contract.md §4.1/§6 (G019). One contract, three
implementations: this adapter serves the ``lasr.data.synthetic`` world
through the SAME ``DataProvider`` protocol and contract-test suite
(CT-01..15) as every other provider. It is the only provider that can
serve the full seven-version reconstruction: true knowledge times,
publication-lagged + restated fundamental vintages, estimate revisions,
interval membership, explicit corporate actions over UNADJUSTED prices.

Scenario interface (§6): ``generate(scenario)`` returns a
:class:`ScenarioBundle` — raw-layer-ready datasets per field family, the
machine-readable :class:`SidecarTruth`, and the teeth-check ablation
datasets — for any catalog scenario (LT-001..021 + baseline).

Capability honesty notes: every family is served with generator-emitted
knowledge times (``supports_pit=true``) EXCEPT the trading calendar — a
derived grid with no knowledge event (the canonical U1 exemption,
G015-verification N-5) whose raw schema carries no knowledge column, so
declaring PIT support there would be dishonest. Corporate actions' raw
knowledge column is ``announcement_time`` (schema-native name).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Literal

import pandas as pd

from lasr.core.enums import PitGrade, RevisionSupport
from lasr.core.errors import TimeSemanticsError
from lasr.data.providers._frames import DataFrame, build_frame
from lasr.data.providers.base import (
    DEFAULT_PRICE_FIELDS,
    FAMILY_RAW_TABLES,
    CapabilityError,
    CorporateActionBasis,
    FamilyCapability,
    FieldFamily,
    FieldUnavailableError,
    HistoryUnavailableError,
    ProviderCapabilities,
    ProviderId,
    UnknownProviderIdError,
    grade_dataset,
    require_unique_ids,
)
from lasr.data.schemas.manifest import DatasetManifest
from lasr.data.schemas.raw_registry import RAW_SCHEMAS
from lasr.data.synthetic import (
    Row,
    ScenarioConfig,
    SidecarTruth,
    content_hash_rows,
    generate_world,
    latest_vintage_view,
)
from lasr.data.synthetic.generator import CALENDAR_ID, UNIVERSE_ID
from lasr.data.synthetic.scenarios import SCENARIO_IDS

__all__ = [
    "PROVIDER_NAME",
    "PROVIDER_VERSION",
    "DatasetRef",
    "ScenarioBundle",
    "SyntheticProvider",
]

logger = logging.getLogger(__name__)

PROVIDER_NAME = "synthetic_generator"
PROVIDER_VERSION = "1.0.0"

_BAR_FIELDS = frozenset(
    {
        "open",
        "high",
        "low",
        "close",
        "volume",
        "vwap",
        "shares_outstanding",
        "market_cap",
    }
)

#: Window-end knowability instant: the END date's bar close (RT-G019-8 —
#: a consumer equating "window end" with "decision at D's close" must not
#: receive data stamped after that close, e.g. 21:30 publications on D).
_BAR_CLOSE = time(21, 0)


# ── scenario bundle machinery (provider_contract.md §6) ──────────────────────


@dataclass(frozen=True)
class DatasetRef:
    """One raw-layer-ready dataset: frames per raw table + U5 manifest.

    ``family`` is ``None`` only for non-raw teeth payloads (the LT-012
    ``fold_spec`` marker); every raw-table dataset carries its family,
    grade and content hash.
    """

    dataset_id: str
    family: FieldFamily | None
    tables: Mapping[str, DataFrame]
    pit_grade: PitGrade | None
    content_hash: str
    manifest: DatasetManifest | None


@dataclass(frozen=True)
class ScenarioBundle:
    """(data, ground-truth sidecar, paired teeth-check ablations) for one
    scenario (# arch: provider_contract.md §6; leakage_tests.md G019 rule)."""

    scenario: ScenarioConfig
    datasets: Mapping[FieldFamily, DatasetRef]
    sidecar: SidecarTruth
    ablations: Mapping[str, DatasetRef]


# ── the provider ─────────────────────────────────────────────────────────────


class SyntheticProvider:
    """DataProvider over one generated world (# arch: provider_contract.md
    §4.1). ``config`` names the scenario served by the fetch methods;
    :meth:`generate` builds bundles for ANY catalog scenario."""

    def __init__(self, config: ScenarioConfig) -> None:
        self._config = config
        self._world = generate_world(config)
        self._known_ids = {
            (str(row["ticker"]), str(row["exchange"]))
            for row in self._world.table("raw_security_master")
        }
        self._capabilities = self._build_capabilities()
        logger.debug(
            "synthetic provider ready: scenario=%s seed=%d ids=%d",
            config.scenario_id,
            config.seed,
            len(self._known_ids),
        )

    # -- scenario interface (§6) ----------------------------------------------

    def scenario_catalog(self) -> frozenset[str]:
        """Named scenarios this generator can construct (LT-001..021)."""
        return SCENARIO_IDS

    def generate(self, scenario: ScenarioConfig) -> ScenarioBundle:
        """Generate the full bundle for ``scenario``: datasets keyed by
        field family, sidecar truth, and teeth-check ablations."""
        world = self._world if scenario == self._config else generate_world(scenario)
        datasets: dict[FieldFamily, DatasetRef] = {}
        for family in FieldFamily:
            tables = {
                name: world.table(name)
                for name in FAMILY_RAW_TABLES[family]
                if name in world.tables
            }
            datasets[family] = self._dataset_ref(
                dataset_id=f"{scenario.scenario_id}/{family.value}",
                family=family,
                tables=tables,
                scenario=scenario,
            )
        ablations = {
            name: self._ablation_ref(name, tables, scenario)
            for name, tables in world.ablations.items()
        }
        return ScenarioBundle(
            scenario=scenario,
            datasets=datasets,
            sidecar=world.sidecar,
            ablations=ablations,
        )

    def _dataset_ref(
        self,
        dataset_id: str,
        family: FieldFamily,
        tables: Mapping[str, tuple[Row, ...]],
        scenario: ScenarioConfig,
    ) -> DatasetRef:
        capability = self._capability_for(family)
        grade = grade_dataset(family, capability, synthetic_truth=True)
        content_hash = content_hash_rows(
            row for rows in tables.values() for row in rows
        )
        frames = {
            name: build_frame(RAW_SCHEMAS[name], list(rows))
            for name, rows in tables.items()
        }
        manifest = DatasetManifest(
            schema_version=PROVIDER_VERSION,
            provider=PROVIDER_NAME,
            pit_grade=grade,
            source_snapshot_ids=(
                f"synthetic:{scenario.scenario_id}:seed={scenario.seed}",
            ),
            content_hash=content_hash,
        )
        return DatasetRef(
            dataset_id=dataset_id,
            family=family,
            tables=frames,
            pit_grade=grade,
            content_hash=content_hash,
            manifest=manifest,
        )

    def _ablation_ref(
        self,
        name: str,
        tables: Mapping[str, tuple[Row, ...]],
        scenario: ScenarioConfig,
    ) -> DatasetRef:
        frames: dict[str, DataFrame] = {}
        for table_name, rows in tables.items():
            if table_name in RAW_SCHEMAS:
                frames[table_name] = build_frame(RAW_SCHEMAS[table_name], list(rows))
            else:  # non-raw teeth payload (LT-012 fold_spec marker)
                frames[table_name] = pd.DataFrame(list(rows), dtype=object)
        return DatasetRef(
            dataset_id=f"{scenario.scenario_id}/ablation/{name}",
            family=None,
            tables=frames,
            pit_grade=None,
            content_hash=content_hash_rows(
                row for rows in tables.values() for row in rows
            ),
            manifest=None,
        )

    # -- capability record (provider_contract.md §4.1) --------------------------

    def _capability_for(self, family: FieldFamily) -> FamilyCapability:
        return self._capabilities.family(family)

    def _metric_codes(self) -> frozenset[str]:
        return frozenset(
            str(row["metric"]) for row in self._world.table("raw_market_metrics")
        )

    def _fundamental_codes(self) -> frozenset[str]:
        return frozenset(
            str(row["metric"]) for row in self._world.table("raw_fundamentals")
        )

    def _estimate_codes(self) -> frozenset[str]:
        return frozenset(
            str(row["metric"]) for row in self._world.table("raw_estimates")
        )

    def _fx_pairs(self) -> frozenset[str]:
        return frozenset(
            f"{row['base_ccy']}/{row['quote_ccy']}"
            for row in self._world.table("raw_fx_rates")
        )

    def _grid_start(self) -> date | None:
        rows = self._world.table("raw_trading_calendars")
        if not rows:
            return None
        first = rows[0]["event_date"]
        return first if isinstance(first, date) else None

    def _build_capabilities(self) -> ProviderCapabilities:
        full = RevisionSupport.FULL_VINTAGES
        families: dict[FieldFamily, FamilyCapability] = {
            FieldFamily.SECURITY_MASTER: FamilyCapability(
                available=True,
                supports_pit=True,
                revision_support=full,
                fields=frozenset(
                    {
                        "ticker",
                        "exchange",
                        "name",
                        "security_type",
                        "mic",
                        "country",
                        "trading_currency",
                        "reporting_currency",
                        "listing_date",
                        "delisting_date",
                    }
                ),
                notes=(
                    "generator-emitted reference data with listings, "
                    "delistings and symbol changes; true knowledge times "
                    "(MP §17) — the counterpoint to the A-001-limited real "
                    "surface (gap §1)"
                ),
                history_start=self._grid_start(),
            ),
            FieldFamily.MARKET_DAILY: FamilyCapability(
                available=True,
                supports_pit=True,
                revision_support=full,
                fields=_BAR_FIELDS | self._metric_codes(),
                notes=(
                    "UNADJUSTED bars + explicit typed actions; the FM-17 "
                    "basis-unknown guard does not bite because the basis is "
                    "declared (provider_contract.md §4.1)"
                ),
                corporate_action_basis=CorporateActionBasis.UNADJUSTED,
            ),
            FieldFamily.FUNDAMENTALS: FamilyCapability(
                available=True,
                supports_pit=True,
                revision_support=full,
                fields=self._fundamental_codes(),
                notes=(
                    "TRUE vintages: publication-lagged as-reported rows plus "
                    "restatements with later knowledge times (A-002 made "
                    "literal; contrast A-001 latest_filing-only)"
                ),
            ),
            FieldFamily.ESTIMATES: FamilyCapability(
                available=True,
                supports_pit=True,
                revision_support=full,
                fields=self._estimate_codes(),
                notes=(
                    "consensus with full revision histories and knowledge "
                    "times (MP §17 analyst-estimate revisions; contrast "
                    "gap §4 snapshot-only surface)"
                ),
            ),
            FieldFamily.CORPORATE_ACTIONS: FamilyCapability(
                available=True,
                supports_pit=True,
                revision_support=full,
                fields=frozenset(
                    {
                        "provider_action_id",
                        "ex_date",
                        "ratio_num",
                        "ratio_den",
                        "amount",
                        "successor_ticker",
                        "terminal_return",
                    }
                ),
                notes=(
                    "typed events (splits, dividends, mergers, symbol "
                    "changes, delistings) with announcement times as the "
                    "knowledge column (CI-049; contrast gap §5 UNAVAILABLE)"
                ),
            ),
            FieldFamily.CLASSIFICATIONS: FamilyCapability(
                available=True,
                supports_pit=True,
                revision_support=full,
                fields=frozenset({"country", "sector"}),
                notes=(
                    "effective-dated country/sector intervals with knowledge "
                    "times (contrast FM-33 SNAPSHOT-only surface)"
                ),
            ),
            FieldFamily.UNIVERSE_MEMBERSHIP: FamilyCapability(
                available=True,
                supports_pit=True,
                revision_support=full,
                fields=frozenset({UNIVERSE_ID}),
                notes=(
                    "point-in-time membership intervals with churn "
                    "(MP §17; contrast gap §8 — the hardest real-data "
                    "blocker)"
                ),
            ),
            FieldFamily.BORROW: FamilyCapability(
                available=True,
                supports_pit=True,
                revision_support=full,
                fields=frozenset(
                    {"borrow_fee_bps_pa", "borrow_available", "hard_to_borrow"}
                ),
                notes=(
                    "per-security borrow fees and availability (MP §17 "
                    "borrow costs; contrast gap §7 UNAVAILABLE)"
                ),
            ),
            FieldFamily.FX: FamilyCapability(
                available=True,
                supports_pit=True,
                revision_support=full,
                fields=self._fx_pairs() | frozenset({"rate"}),
                notes=(
                    "synthetic currency pairs vs the numeraire (contrast "
                    "FM-24 W1-list-only)"
                ),
            ),
            FieldFamily.CALENDAR: FamilyCapability(
                available=True,
                supports_pit=False,
                revision_support=RevisionSupport.NONE,
                fields=frozenset({CALENDAR_ID}),
                notes=(
                    "derived trading-period grid; a calendar has no "
                    "knowledge event (canonical U1 exemption, "
                    "G015-verification N-5; cf. FM-08 derived-with-note), "
                    "so supports_pit=false is the honest declaration"
                ),
            ),
        }
        return ProviderCapabilities(
            provider_name=PROVIDER_NAME,
            provider_version=PROVIDER_VERSION,
            families=families,
            supports_universe_screening=True,
            supports_publication_timestamps=True,
            supports_delistings=True,
            supports_bid_ask=False,  # bars carry no quotes; never fabricated
            supports_borrow=True,
            supports_index_membership=True,
            supports_estimate_history=True,
            supports_vintages=True,
        )

    # -- report methods ---------------------------------------------------------

    def capabilities(self) -> ProviderCapabilities:
        return self._capabilities

    def field_coverage(self, family: FieldFamily) -> frozenset[str]:
        return self._capabilities.family(family).fields

    def available_history(self, family: FieldFamily) -> tuple[date | None, date | None]:
        """Observed (earliest, latest) event window per family; reference
        tables (master, classifications) advertise no window."""

        def bounds(table: str, column: str) -> tuple[date | None, date | None]:
            values: list[date] = []
            for row in self._world.table(table):
                value = row.get(column)
                if isinstance(value, date):
                    values.append(value)
            if not values:
                return (None, None)
            return (min(values), max(values))

        if family in (FieldFamily.SECURITY_MASTER, FieldFamily.CLASSIFICATIONS):
            return (None, None)
        if family is FieldFamily.MARKET_DAILY:
            return bounds("raw_market_daily", "event_date")
        if family is FieldFamily.FUNDAMENTALS:
            return bounds("raw_fundamentals", "period_end")
        if family is FieldFamily.ESTIMATES:
            return bounds("raw_estimates", "period_end")
        if family is FieldFamily.CORPORATE_ACTIONS:
            return bounds("raw_corporate_actions", "effective_date")
        if family is FieldFamily.UNIVERSE_MEMBERSHIP:
            rows = self._world.table("raw_universe_membership")
            grid_end = bounds("raw_trading_calendars", "event_date")[1]
            if not rows or grid_end is None:
                return (None, None)
            froms: list[date] = []
            tos: list[date] = []
            for row in rows:
                valid_from = row["valid_from"]
                if isinstance(valid_from, date):
                    froms.append(valid_from)
                valid_to = row["valid_to"]
                tos.append(valid_to if isinstance(valid_to, date) else grid_end)
            return (min(froms), max(tos))
        if family is FieldFamily.BORROW:
            return bounds("raw_borrow_daily", "event_date")
        if family is FieldFamily.FX:
            return bounds("raw_fx_rates", "event_date")
        if family is FieldFamily.CALENDAR:
            return bounds("raw_trading_calendars", "event_date")
        raise CapabilityError(f"unmapped family {family}")  # pragma: no cover

    # -- shared guards ----------------------------------------------------------

    def _resolve(self, ids: Sequence[ProviderId]) -> set[tuple[str, str]]:
        resolved: set[tuple[str, str]] = set()
        for pid in require_unique_ids(ids):  # NB-1: typed refusal
            key = (pid.value, pid.exchange or "")
            if key not in self._known_ids:
                raise UnknownProviderIdError(
                    f"no synthetic entity {pid.value!r}/{pid.exchange!r} in "
                    f"scenario {self._config.scenario_id!r}"
                )
            resolved.add(key)
        return resolved

    def _check_window(self, family: FieldFamily, start: date, end: date) -> None:
        if start > end:
            raise TimeSemanticsError(f"inverted window: start {start} after end {end}")
        earliest, latest = self.available_history(family)
        if earliest is None or latest is None:
            return
        if start < earliest or end > latest:
            raise HistoryUnavailableError(
                f"window [{start}, {end}] exceeds available history "
                f"[{earliest}, {latest}] for family {family.value!r}; partial "
                "windows are not silently truncated (provider_contract.md §3)"
            )

    @staticmethod
    def _id_match(row: Row, keys: set[tuple[str, str]]) -> bool:
        return (str(row["ticker"]), str(row["exchange"])) in keys

    # -- load methods -----------------------------------------------------------

    def fetch_security_master(
        self, ids: Sequence[ProviderId] | None = None
    ) -> DataFrame:
        # RT-G019-1: the world table carries open + closure VINTAGES per
        # segment; the snapshot surface serves the max-knowledge view
        # (retrieval-time semantics — closures are knowable by then).
        rows = latest_vintage_view(
            self._world.table("raw_security_master"), ("ticker", "exchange")
        )
        if ids is not None:
            keys = self._resolve(ids)
            rows = tuple(row for row in rows if self._id_match(row, keys))
        return build_frame(RAW_SCHEMAS["raw_security_master"], list(rows))

    def fetch_prices(
        self,
        ids: Sequence[ProviderId],
        start: date,
        end: date,
        fields: Sequence[str] = DEFAULT_PRICE_FIELDS,
    ) -> DataFrame:
        requested = list(dict.fromkeys(fields))
        unknown = sorted(set(requested) - _BAR_FIELDS)
        if unknown:
            raise FieldUnavailableError(
                f"price fields {unknown!r} are not servable; bar coverage: "
                f"{sorted(_BAR_FIELDS)}"
            )
        self._check_window(FieldFamily.MARKET_DAILY, start, end)
        keys = self._resolve(ids)
        columns = ["ticker", "exchange", "event_date"]
        columns += [
            c
            for c in RAW_SCHEMAS["raw_market_daily"].column_names
            if c in set(requested)
        ]
        columns += ["currency", "knowledge_time"]
        rows = [
            {name: row[name] for name in columns}
            for row in self._world.table("raw_market_daily")
            if self._id_match(row, keys) and start <= row["event_date"] <= end  # type: ignore[operator]
        ]
        return build_frame(RAW_SCHEMAS["raw_market_daily"], rows, columns=columns)

    def fetch_market_metrics(
        self, ids: Sequence[ProviderId], metrics: Sequence[str], start: date, end: date
    ) -> DataFrame:
        catalog = self._metric_codes()
        unknown = sorted(set(metrics) - catalog)
        if unknown:
            raise FieldUnavailableError(
                f"market metrics {unknown!r} are not in this world; "
                f"coverage: {sorted(catalog)}"
            )
        self._check_window(FieldFamily.MARKET_DAILY, start, end)
        keys = self._resolve(ids)
        wanted = set(metrics)
        rows = [
            row
            for row in self._world.table("raw_market_metrics")
            if row["metric"] in wanted
            and self._id_match(row, keys)
            and start <= row["event_date"] <= end  # type: ignore[operator]
        ]
        return build_frame(RAW_SCHEMAS["raw_market_metrics"], rows)

    def fetch_fundamentals(
        self,
        ids: Sequence[ProviderId],
        metrics: Sequence[str],
        start: date,
        end: date,
        vintage: Literal["latest", "as_reported", "all"] = "latest",
    ) -> DataFrame:
        if vintage not in ("latest", "as_reported", "all"):
            raise CapabilityError(f"unknown vintage mode {vintage!r}")
        catalog = self._fundamental_codes()
        unknown = sorted(set(metrics) - catalog)
        if unknown:
            raise FieldUnavailableError(
                f"fundamental metrics {unknown!r} are not in this world; "
                f"coverage: {sorted(catalog)}"
            )
        self._check_window(FieldFamily.FUNDAMENTALS, start, end)
        keys = self._resolve(ids)
        wanted = set(metrics)
        matched = [
            row
            for row in self._world.table("raw_fundamentals")
            if row["metric"] in wanted
            and self._id_match(row, keys)
            and start <= row["period_end"] <= end  # type: ignore[operator]
        ]
        if vintage != "all":
            by_key: dict[tuple[object, ...], Row] = {}
            for row in matched:
                key = (
                    row["ticker"],
                    row["exchange"],
                    row["metric"],
                    row["fiscal_period"],
                )
                current = by_key.get(key)
                if current is None:
                    by_key[key] = row
                    continue
                newer = row["knowledge_time"] > current["knowledge_time"]  # type: ignore[operator]
                if (vintage == "latest") == bool(newer):
                    by_key[key] = row
            matched = list(by_key.values())
        return build_frame(RAW_SCHEMAS["raw_fundamentals"], matched)

    def fetch_estimates(
        self, ids: Sequence[ProviderId], metrics: Sequence[str], start: date, end: date
    ) -> DataFrame:
        catalog = self._estimate_codes()
        unknown = sorted(set(metrics) - catalog)
        if unknown:
            raise FieldUnavailableError(
                f"estimate metrics {unknown!r} are not in this world; "
                f"coverage: {sorted(catalog)}"
            )
        self._check_window(FieldFamily.ESTIMATES, start, end)
        keys = self._resolve(ids)
        wanted = set(metrics)
        cutoff = datetime.combine(end, _BAR_CLOSE, tzinfo=UTC)
        by_key: dict[tuple[object, ...], Row] = {}
        for row in self._world.table("raw_estimates"):
            if row["metric"] not in wanted or not self._id_match(row, keys):
                continue
            if not start <= row["period_end"] <= end:  # type: ignore[operator]
                continue
            if row["knowledge_time"] > cutoff:  # type: ignore[operator]
                continue  # revision not yet knowable at the window end
            key = (
                row["ticker"],
                row["exchange"],
                row["metric"],
                row["forecast_period"],
            )
            current = by_key.get(key)
            if current is None or row["knowledge_time"] > current["knowledge_time"]:  # type: ignore[operator]
                by_key[key] = row
        return build_frame(RAW_SCHEMAS["raw_estimates"], list(by_key.values()))

    def fetch_corporate_actions(
        self, ids: Sequence[ProviderId], start: date, end: date
    ) -> DataFrame:
        self._check_window(FieldFamily.CORPORATE_ACTIONS, start, end)
        keys = self._resolve(ids)
        rows = [
            row
            for row in self._world.table("raw_corporate_actions")
            if self._id_match(row, keys) and start <= row["effective_date"] <= end  # type: ignore[operator]
        ]
        return build_frame(RAW_SCHEMAS["raw_corporate_actions"], rows)

    def fetch_classifications(
        self, ids: Sequence[ProviderId], schemes: Sequence[str]
    ) -> DataFrame:
        catalog = self.field_coverage(FieldFamily.CLASSIFICATIONS)
        unknown = sorted(set(schemes) - catalog)
        if unknown:
            raise FieldUnavailableError(
                f"classification schemes {unknown!r} are not servable; "
                f"coverage: {sorted(catalog)}"
            )
        keys = self._resolve(ids)
        wanted = set(schemes)
        # RT-G019-1: collapse open/closure vintages (snapshot semantics).
        rows = [
            row
            for row in latest_vintage_view(
                self._world.table("raw_classifications"),
                ("ticker", "exchange", "scheme"),
            )
            if row["scheme"] in wanted and self._id_match(row, keys)
        ]
        return build_frame(RAW_SCHEMAS["raw_classifications"], rows)

    def fetch_universe_membership(
        self, universe_id: str, start: date, end: date
    ) -> DataFrame:
        if universe_id != UNIVERSE_ID:
            raise FieldUnavailableError(
                f"universe {universe_id!r} is not servable; the synthetic "
                f"universe is {UNIVERSE_ID!r}"
            )
        self._check_window(FieldFamily.UNIVERSE_MEMBERSHIP, start, end)
        # RT-G019-1: PIT semantics on the windowed surface — only vintages
        # knowable at the window end's bar close are considered, THEN the
        # max-knowledge row per interval key is taken, so a closure dated
        # beyond the window can never appear (the open row serves instead).
        cutoff = datetime.combine(end, _BAR_CLOSE, tzinfo=UTC)
        knowable = [
            row
            for row in self._world.table("raw_universe_membership")
            if row["knowledge_time"] <= cutoff  # type: ignore[operator]
        ]
        rows = [
            row
            for row in latest_vintage_view(
                knowable, ("universe_id", "ticker", "exchange", "valid_from")
            )
            if row["valid_from"] <= end  # type: ignore[operator]
            and (row["valid_to"] is None or row["valid_to"] >= start)  # type: ignore[operator]
        ]
        return build_frame(RAW_SCHEMAS["raw_universe_membership"], rows)

    def fetch_borrow(
        self, ids: Sequence[ProviderId], start: date, end: date
    ) -> DataFrame:
        self._check_window(FieldFamily.BORROW, start, end)
        keys = self._resolve(ids)
        rows = [
            row
            for row in self._world.table("raw_borrow_daily")
            if self._id_match(row, keys) and start <= row["event_date"] <= end  # type: ignore[operator]
        ]
        return build_frame(RAW_SCHEMAS["raw_borrow_daily"], rows)

    def fetch_fx_rates(
        self, pairs: Sequence[tuple[str, str]], start: date, end: date
    ) -> DataFrame:
        served = self._fx_pairs()
        unknown = sorted(
            f"{base}/{quote}"
            for base, quote in pairs
            if f"{base}/{quote}" not in served
        )
        if unknown:
            raise FieldUnavailableError(
                f"FX pairs {unknown!r} are not servable; coverage: {sorted(served)}"
            )
        self._check_window(FieldFamily.FX, start, end)
        wanted = {(base, quote) for base, quote in pairs}
        rows = [
            row
            for row in self._world.table("raw_fx_rates")
            if (row["base_ccy"], row["quote_ccy"]) in wanted
            and start <= row["event_date"] <= end  # type: ignore[operator]
        ]
        return build_frame(RAW_SCHEMAS["raw_fx_rates"], rows)

    def fetch_trading_calendar(
        self, calendar_id: str, start: date, end: date
    ) -> DataFrame:
        if calendar_id != CALENDAR_ID:
            raise FieldUnavailableError(
                f"calendar {calendar_id!r} is not servable; the synthetic "
                f"calendar is {CALENDAR_ID!r}"
            )
        self._check_window(FieldFamily.CALENDAR, start, end)
        rows = [
            row
            for row in self._world.table("raw_trading_calendars")
            if start <= row["event_date"] <= end  # type: ignore[operator]
        ]
        return build_frame(RAW_SCHEMAS["raw_trading_calendars"], rows)
