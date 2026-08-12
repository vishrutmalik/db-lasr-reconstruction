"""Provider contract suite CT-01..15 (provider_contract.md §5).

Parameterized over all registered providers; every current and future
provider must pass CT-01..15 unmodified. Capability-conditional tests
skip-with-reason only when the capability is declared false AND the test
verifies the refusal path instead.

Registered today: ``local_file`` (G018). The synthetic provider (G019)
joins by appending a :class:`ProviderCase` to ``PROVIDER_CASES``.
"""

from __future__ import annotations

import hashlib
import logging
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from lasr.core.enums import PitGrade
from lasr.data.providers import (
    FAMILY_RAW_TABLES,
    CapabilityError,
    CorporateActionBasis,
    DataProvider,
    FieldFamily,
    FieldUnavailableError,
    HistoryUnavailableError,
    LocalFileProvider,
    ProviderId,
    SyntheticProvider,
    UnknownProviderIdError,
    grade_dataset,
)
from lasr.data.schemas.base import validate_rows
from lasr.data.schemas.market_data import FM17_FORBIDDEN_PRICE_COLUMNS
from lasr.data.schemas.raw_registry import RAW_SCHEMAS
from lasr.data.synthetic import ScenarioConfig

pytestmark = pytest.mark.integration

FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1] / "fixtures" / "provider" / "template_extracts"
)

#: Evidence citation tokens: CT-01 requires notes to cite a source.
CITATION_TOKENS = ("gap §", "FM-", "A-001", "E-G012", "Data!", "TM ", "W1")

AVAILABLE_FAMILIES_ALL = tuple(sorted(FieldFamily, key=lambda f: f.value))


@dataclass(frozen=True)
class ProviderCase:
    """One registered provider: factory + (optional) immutable input root."""

    name: str
    factory: Callable[[], DataProvider]
    input_root: Path | None


#: G019: the synthetic provider joins the suite on the baseline scenario —
#: small enough for CI, every family populated, TRUE vintages (CT-10/CT-11
#: positive branches). Fixed seed: CT-04 requires instance-identical worlds.
SYNTHETIC_CT_CONFIG = ScenarioConfig(
    scenario_id="baseline", seed=1729, n_securities=40, n_years=6
)

PROVIDER_CASES: tuple[ProviderCase, ...] = (
    ProviderCase(
        name="local_file",
        factory=lambda: LocalFileProvider(FIXTURE_ROOT),
        input_root=FIXTURE_ROOT,
    ),
    ProviderCase(
        name="synthetic",
        factory=lambda: SyntheticProvider(SYNTHETIC_CT_CONFIG),
        input_root=None,
    ),
)


@pytest.fixture(params=PROVIDER_CASES, ids=lambda case: case.name, scope="module")
def case(request: pytest.FixtureRequest) -> ProviderCase:
    return request.param


@pytest.fixture(scope="module")
def provider(case: ProviderCase) -> DataProvider:
    return case.factory()


# ── provider-agnostic helpers ────────────────────────────────────────────────


def master_ids(provider: DataProvider) -> list[ProviderId]:
    frame = provider.fetch_security_master()
    return [
        ProviderId(value=record["ticker"], exchange=record["exchange"])
        for record in frame.to_dict("records")
    ]


def probe_window(provider: DataProvider, family: FieldFamily) -> tuple[date, date]:
    earliest, latest = provider.available_history(family)
    if earliest is None or latest is None:
        return (date(2000, 1, 1), date(2100, 1, 1))
    return (earliest, latest)


def family_frames(
    provider: DataProvider, family: FieldFamily, ids: Sequence[ProviderId]
) -> dict[str, Any]:
    """Fetch every raw table of an *available* family, provider-agnostically.

    Arguments are derived from the provider's own report methods
    (``field_coverage`` / ``available_history``), so the same call plan
    works for any conformant provider.
    """
    coverage = sorted(provider.field_coverage(family))
    start, end = probe_window(provider, family)
    if family is FieldFamily.SECURITY_MASTER:
        return {"raw_security_master": provider.fetch_security_master(ids)}
    if family is FieldFamily.MARKET_DAILY:
        frames = {"raw_market_daily": provider.fetch_prices(ids, start, end)}
        metrics = [c for c in coverage if c not in ("close", "market_cap")][:4]
        if metrics:
            frames["raw_market_metrics"] = provider.fetch_market_metrics(
                ids, metrics, start, end
            )
        return frames
    if family is FieldFamily.FUNDAMENTALS:
        return {
            "raw_fundamentals": provider.fetch_fundamentals(
                ids, coverage[:4], start, end
            )
        }
    if family is FieldFamily.ESTIMATES:
        return {
            "raw_estimates": provider.fetch_estimates(ids, coverage[:4], start, end)
        }
    if family is FieldFamily.CLASSIFICATIONS:
        return {"raw_classifications": provider.fetch_classifications(ids, coverage)}
    if family is FieldFamily.CORPORATE_ACTIONS:
        return {
            "raw_corporate_actions": provider.fetch_corporate_actions(ids, start, end)
        }
    if family is FieldFamily.UNIVERSE_MEMBERSHIP:
        universe_id = coverage[0] if coverage else "unknown"
        return {
            "raw_universe_membership": provider.fetch_universe_membership(
                universe_id, start, end
            )
        }
    if family is FieldFamily.BORROW:
        return {"raw_borrow_daily": provider.fetch_borrow(ids, start, end)}
    if family is FieldFamily.FX:
        pair = tuple(coverage[0].split("/")) if coverage else ("USD", "EUR")
        return {"raw_fx_rates": provider.fetch_fx_rates([pair], start, end)}
    if family is FieldFamily.CALENDAR:
        calendar_id = coverage[0] if coverage else "unknown"
        return {
            "raw_trading_calendars": provider.fetch_trading_calendar(
                calendar_id, start, end
            )
        }
    raise AssertionError(f"unmapped family {family}")  # pragma: no cover


def refusal_call(
    provider: DataProvider, family: FieldFamily, ids: Sequence[ProviderId]
) -> None:
    """Invoke the fetch for a declared-unavailable family (CT-03)."""
    window = (date(2024, 1, 2), date(2024, 1, 3))
    calls: dict[FieldFamily, Callable[[], Any]] = {
        FieldFamily.SECURITY_MASTER: lambda: provider.fetch_security_master(ids),
        FieldFamily.MARKET_DAILY: lambda: provider.fetch_prices(ids, *window),
        FieldFamily.FUNDAMENTALS: lambda: provider.fetch_fundamentals(
            ids, ["REV"], *window
        ),
        FieldFamily.ESTIMATES: lambda: provider.fetch_estimates(ids, ["REV"], *window),
        FieldFamily.CORPORATE_ACTIONS: lambda: provider.fetch_corporate_actions(
            ids, *window
        ),
        FieldFamily.CLASSIFICATIONS: lambda: provider.fetch_classifications(
            ids, ["gics_l1"]
        ),
        FieldFamily.UNIVERSE_MEMBERSHIP: lambda: provider.fetch_universe_membership(
            "any", *window
        ),
        FieldFamily.BORROW: lambda: provider.fetch_borrow(ids, *window),
        FieldFamily.FX: lambda: provider.fetch_fx_rates([("USD", "EUR")], *window),
        FieldFamily.CALENDAR: lambda: provider.fetch_trading_calendar("any", *window),
    }
    calls[family]()


def normalized_records(frame: Any) -> list[dict[str, Any]]:
    """Frame rows as plain dicts with NaN normalized to None."""
    records: list[dict[str, Any]] = frame.to_dict("records")
    for record in records:
        for key, value in record.items():
            if isinstance(value, float) and math.isnan(value):
                record[key] = None
    return records


def frame_hash(frame: Any) -> str:
    """Canonical content hash (CT-04: hash equality after canonical sort)."""
    payload = repr(
        [sorted(record.items()) for record in normalized_records(frame)]
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def assert_conforms(table_name: str, frame: Any) -> None:
    """CT-05 core: columns declared+ordered, batch rules, typed rows."""
    schema = RAW_SCHEMAS[table_name]
    columns = list(frame.columns)
    declared = [c for c in schema.column_names if c in set(columns)]
    assert columns == declared, (
        f"{table_name}: columns {columns} not in schema order/vocabulary"
    )
    records = normalized_records(frame)
    validate_rows(schema, records)  # nullability, PK, sort, forbidden columns
    for record in records:
        schema.row_model(**record)  # dtypes, closed enums, UTC timestamps


def available_families(provider: DataProvider) -> list[FieldFamily]:
    capabilities = provider.capabilities()
    return [
        family
        for family in AVAILABLE_FAMILIES_ALL
        if capabilities.family(family).available
    ]


def unavailable_families(provider: DataProvider) -> list[FieldFamily]:
    capabilities = provider.capabilities()
    return [
        family
        for family in AVAILABLE_FAMILIES_ALL
        if not capabilities.family(family).available
    ]


# ── CT-01: capability record completeness ────────────────────────────────────


def test_ct01_capability_record_completeness(provider: DataProvider) -> None:
    capabilities = provider.capabilities()
    assert capabilities.provider_name
    assert capabilities.provider_version
    for family in FieldFamily:
        assert family in capabilities.families, family.value
        record = capabilities.family(family)
        assert isinstance(record.available, bool)
        assert isinstance(record.supports_pit, bool)
        assert record.notes.strip(), f"{family.value}: notes must cite a source"
        assert any(token in record.notes for token in CITATION_TOKENS), (
            f"{family.value}: notes carry no recognizable citation: {record.notes!r}"
        )
    for flag in (
        "supports_universe_screening",
        "supports_publication_timestamps",
        "supports_delistings",
        "supports_bid_ask",
        "supports_borrow",
        "supports_index_membership",
        "supports_estimate_history",
        "supports_vintages",
    ):
        assert isinstance(getattr(capabilities, flag), bool), flag


# ── CT-02: capability honesty (positive) ─────────────────────────────────────


def test_ct02_available_families_serve_conformant_frames(
    provider: DataProvider,
) -> None:
    ids = master_ids(provider)
    assert ids, "provider serves no securities"
    for family in available_families(provider):
        frames = family_frames(provider, family, ids)
        assert frames, family.value
        for table_name, frame in frames.items():
            assert_conforms(table_name, frame)


# ── CT-03: capability honesty (negative) ─────────────────────────────────────


def test_ct03_unavailable_families_refuse_with_capability_error(
    provider: DataProvider,
) -> None:
    ids = master_ids(provider)
    families = unavailable_families(provider)
    if not families:
        pytest.skip("provider declares every family available (synthetic)")
    for family in families:
        with pytest.raises(CapabilityError):
            refusal_call(provider, family, ids)


def test_ct03_vintage_requests_respect_supports_vintages(
    provider: DataProvider,
) -> None:
    capabilities = provider.capabilities()
    if not capabilities.family(FieldFamily.FUNDAMENTALS).available:
        pytest.skip("fundamentals unavailable; vintage guard untestable")
    ids = master_ids(provider)[:1]
    coverage = sorted(provider.field_coverage(FieldFamily.FUNDAMENTALS))[:1]
    window = probe_window(provider, FieldFamily.FUNDAMENTALS)
    if capabilities.supports_vintages:
        pytest.skip("supports_vintages=true: positive path is CT-11")
    for vintage in ("as_reported", "all"):
        with pytest.raises(CapabilityError):
            provider.fetch_fundamentals(ids, coverage, *window, vintage=vintage)  # type: ignore[arg-type]


# ── CT-04: determinism / idempotence ─────────────────────────────────────────


def test_ct04_identical_calls_return_identical_frames(
    case: ProviderCase,
) -> None:
    first = case.factory()
    second = case.factory()
    for provider_instance in (first, second):
        assert provider_instance.capabilities() == first.capabilities()
    ids = master_ids(first)
    for family in available_families(first):
        hashes = []
        for provider_instance in (first, first, second):  # repeat + fresh instance
            frames = family_frames(provider_instance, family, ids)
            hashes.append({name: frame_hash(frame) for name, frame in frames.items()})
        assert hashes[0] == hashes[1] == hashes[2], family.value


# ── CT-05: raw schema conformance ────────────────────────────────────────────


def test_ct05_frames_conform_to_registered_raw_schemas(
    provider: DataProvider,
) -> None:
    ids = master_ids(provider)
    for family in available_families(provider):
        for table_name, frame in family_frames(provider, family, ids).items():
            assert table_name in FAMILY_RAW_TABLES[family]
            assert_conforms(table_name, frame)
            records = normalized_records(frame)
            for record in records:
                for key, value in record.items():
                    if isinstance(value, datetime):
                        assert value.tzinfo is not None, (
                            f"{table_name}.{key}: naive timestamp"
                        )


# ── CT-06: history bounds ────────────────────────────────────────────────────


def test_ct06_windows_outside_history_raise(provider: DataProvider) -> None:
    ids = master_ids(provider)[:1]
    checked = 0
    for family in available_families(provider):
        earliest, latest = provider.available_history(family)
        if earliest is None or latest is None:
            continue  # snapshot families advertise no window
        checked += 1
        # the advertised window itself must serve (no error)
        family_frames(provider, family, ids)
        with pytest.raises(HistoryUnavailableError):
            fetch_with_window(
                provider, family, ids, earliest, latest.replace(year=latest.year + 1)
            )
        with pytest.raises(HistoryUnavailableError):
            fetch_with_window(
                provider, family, ids, earliest.replace(year=earliest.year - 1), latest
            )
    assert checked, "no windowed family with established history was exercised"


def fetch_with_window(
    provider: DataProvider,
    family: FieldFamily,
    ids: Sequence[ProviderId],
    start: date,
    end: date,
) -> Any:
    coverage = sorted(provider.field_coverage(family))
    if family is FieldFamily.MARKET_DAILY:
        return provider.fetch_prices(ids, start, end)
    if family is FieldFamily.FUNDAMENTALS:
        return provider.fetch_fundamentals(ids, coverage[:1], start, end)
    if family is FieldFamily.ESTIMATES:
        return provider.fetch_estimates(ids, coverage[:1], start, end)
    if family is FieldFamily.CALENDAR:
        return provider.fetch_trading_calendar(coverage[0], start, end)
    if family is FieldFamily.BORROW:
        return provider.fetch_borrow(ids, start, end)
    if family is FieldFamily.FX:
        pair = tuple(coverage[0].split("/")) if coverage else ("USD", "EUR")
        return provider.fetch_fx_rates([pair], start, end)
    if family is FieldFamily.CORPORATE_ACTIONS:
        return provider.fetch_corporate_actions(ids, start, end)
    if family is FieldFamily.UNIVERSE_MEMBERSHIP:
        universe_id = coverage[0] if coverage else "unknown"
        return provider.fetch_universe_membership(universe_id, start, end)
    raise AssertionError(f"family {family} has no windowed fetch")


# ── CT-07: field coverage honesty ────────────────────────────────────────────


def test_ct07_uncovered_fields_raise_field_unavailable(
    provider: DataProvider,
) -> None:
    ids = master_ids(provider)[:1]
    window = probe_window(provider, FieldFamily.MARKET_DAILY)
    market = provider.capabilities().family(FieldFamily.MARKET_DAILY)
    if market.available:
        coverage = provider.field_coverage(FieldFamily.MARKET_DAILY)
        # D-012: explicit OHLV requests refused until VP-01 passes.
        for field in ("open", "high", "low", "volume"):
            if field in coverage:
                continue  # a probed provider may legitimately serve OHLV
            with pytest.raises(FieldUnavailableError):
                provider.fetch_prices(ids, *window, fields=(field,))
        with pytest.raises(FieldUnavailableError):
            provider.fetch_market_metrics(ids, ["DEFINITELY_NOT_A_METRIC"], *window)
    fundamentals = provider.capabilities().family(FieldFamily.FUNDAMENTALS)
    if fundamentals.available:
        with pytest.raises(FieldUnavailableError):
            provider.fetch_fundamentals(
                ids,
                ["DEFINITELY_NOT_A_METRIC"],
                *probe_window(provider, FieldFamily.FUNDAMENTALS),
            )


def test_ct07_field_coverage_matches_returned_fields(
    provider: DataProvider,
) -> None:
    ids = master_ids(provider)
    for family in available_families(provider):
        coverage = provider.field_coverage(family)
        assert coverage == provider.capabilities().family(family).fields
        for table_name, frame in family_frames(provider, family, ids).items():
            schema = RAW_SCHEMAS[table_name]
            key_columns = set(schema.primary_key) | {
                "currency",
                "unit",
                "value",
                "version_type",
                "period_end",
                "is_trading_day",
                "name",
                # G019 amendment: structural PIT/interval columns are not
                # field coverage — CT-10 MANDATES knowledge stamps on
                # PIT-true providers' frames, and interval bounds are
                # structure like period_end (previously unexercised: the
                # local adapter emits none of these).
                "knowledge_time",
                "announcement_time",
                "valid_from",
                "valid_to",
            }
            if "metric" in frame.columns:
                served = set(frame["metric"])
                assert served <= coverage, (
                    f"{table_name}: served metrics {served - coverage} "
                    "outside declared coverage"
                )
            else:
                extra = set(frame.columns) - key_columns - coverage
                assert not extra, (
                    f"{table_name}: columns {extra} outside declared coverage"
                )


# ── CT-08: no fabrication ────────────────────────────────────────────────────


def test_ct08_uncovered_fields_absent_or_null_never_synthesized(
    provider: DataProvider,
) -> None:
    ids = master_ids(provider)
    for family in available_families(provider):
        coverage = provider.field_coverage(family)
        for table_name, frame in family_frames(provider, family, ids).items():
            schema = RAW_SCHEMAS[table_name]
            for column in schema.column_names:
                if column in frame.columns:
                    continue
                # absent column == not fabricated; nothing more to check
            if table_name == "raw_market_daily":
                for column in ("open", "high", "low", "volume", "bid", "ask"):
                    if column in coverage:
                        continue
                    if column in frame.columns:
                        values = [
                            v
                            for v in frame[column]
                            if v is not None
                            and not (isinstance(v, float) and math.isnan(v))
                        ]
                        assert not values, (
                            f"{table_name}.{column} fabricated despite coverage=false"
                        )


# ── CT-09: id stability ──────────────────────────────────────────────────────


def test_ct09_same_entity_same_provider_id_across_calls(
    provider: DataProvider,
) -> None:
    first = master_ids(provider)
    second = master_ids(provider)
    assert first == second
    assert len(set(first)) == len(first), "duplicate provider ids in master"
    window = probe_window(provider, FieldFamily.MARKET_DAILY)
    if provider.capabilities().family(FieldFamily.MARKET_DAILY).available:
        frame = provider.fetch_prices(first, *window)
        served = {
            ProviderId(value=r["ticker"], exchange=r["exchange"])
            for r in normalized_records(frame)
        }
        assert served <= set(first)


# ── CT-10: knowledge-time discipline ─────────────────────────────────────────


# G019 amendments to CT-10 (first PIT-true provider; branches previously
# unexercised): (a) the raw corporate-actions schema names its knowledge
# column ``announcement_time`` (G017 schema; no knowledge_time column
# exists there, so the literal column check was unsatisfiable); (b) on
# ``raw_estimates`` the ``period_end`` is a FORECAST horizon — estimates
# are published before the period they predict, so U3's knowledge>=event
# comparison applies to event tables only.
KNOWLEDGE_COLUMN_BY_TABLE = {"raw_corporate_actions": "announcement_time"}
FORECAST_PERIOD_TABLES = frozenset({"raw_estimates"})


def test_ct10_knowledge_time_stamping_is_ingestions_job(
    provider: DataProvider,
) -> None:
    """supports_pit=false => frames carry NO knowledge column;
    supports_pit=true => knowledge column non-null and >= event time (U3)."""
    ids = master_ids(provider)
    capabilities = provider.capabilities()
    for family in available_families(provider):
        supports_pit = capabilities.family(family).supports_pit
        for table_name, frame in family_frames(provider, family, ids).items():
            column = KNOWLEDGE_COLUMN_BY_TABLE.get(table_name, "knowledge_time")
            if not supports_pit:
                assert column not in frame.columns, (
                    f"{table_name}: non-PIT provider emitted {column} "
                    "(stamping is ingestion's job, A-001)"
                )
                continue
            assert column in frame.columns, table_name
            for record in normalized_records(frame):
                knowledge_time = record[column]
                assert knowledge_time is not None
                if table_name in FORECAST_PERIOD_TABLES:
                    continue  # period_end is a forecast horizon, not an event
                event = record.get("event_date") or record.get("period_end")
                if isinstance(event, date):
                    assert knowledge_time.date() >= event, (
                        f"{table_name}: knowledge time precedes event (U3)"
                    )


# ── CT-11: vintage semantics ─────────────────────────────────────────────────


def test_ct11_vintage_semantics(provider: DataProvider) -> None:
    capabilities = provider.capabilities()
    if not capabilities.supports_vintages:
        # Refusal path is contracted by CT-03; skip-with-reason per §5.
        pytest.skip(
            "supports_vintages=false: refusal verified in CT-03 "
            "(vintage='as_reported'/'all' raise CapabilityError)"
        )
    ids = master_ids(provider)[:1]
    coverage = sorted(provider.field_coverage(FieldFamily.FUNDAMENTALS))[:1]
    window = probe_window(provider, FieldFamily.FUNDAMENTALS)
    frame_all = provider.fetch_fundamentals(ids, coverage, *window, vintage="all")
    frame_latest = provider.fetch_fundamentals(ids, coverage, *window, vintage="latest")
    all_records = normalized_records(frame_all)
    latest_records = normalized_records(frame_latest)
    assert len(all_records) >= len(latest_records)
    # latest == max-knowledge row per event key (CI-002 source-side)
    by_key: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for record in all_records:
        key = (
            record["ticker"],
            record["exchange"],
            record["metric"],
            record["fiscal_period"],
        )
        by_key.setdefault(key, []).append(record)
    for record in latest_records:
        key = (
            record["ticker"],
            record["exchange"],
            record["metric"],
            record["fiscal_period"],
        )
        newest = max(by_key[key], key=lambda r: r["knowledge_time"])
        assert record["value"] == newest["value"]


# ── CT-12: empty-vs-error distinction ────────────────────────────────────────


def test_ct12_valid_but_empty_returns_conformant_frame(
    provider: DataProvider,
) -> None:
    if not provider.capabilities().family(FieldFamily.MARKET_DAILY).available:
        pytest.skip("market family unavailable")
    window = probe_window(provider, FieldFamily.MARKET_DAILY)
    frame = provider.fetch_prices([], *window)  # genuinely empty, valid query
    assert frame.shape[0] == 0
    assert list(frame.columns), "empty frame must keep its schema columns"
    assert_conforms("raw_market_daily", frame)


def test_ct12_absence_conditions_raise(provider: DataProvider) -> None:
    if not provider.capabilities().family(FieldFamily.MARKET_DAILY).available:
        pytest.skip("market family unavailable")
    window = probe_window(provider, FieldFamily.MARKET_DAILY)
    with pytest.raises(UnknownProviderIdError):
        provider.fetch_prices([ProviderId("NO_SUCH_ENTITY", "NOWHERE")], *window)


# ── CT-13: immutability of inputs ────────────────────────────────────────────


def tree_hashes(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_ct13_provider_never_mutates_its_inputs(case: ProviderCase) -> None:
    if case.input_root is None:
        pytest.skip("provider has no file inputs")
    before = tree_hashes(case.input_root)
    provider = case.factory()
    ids = master_ids(provider)
    for family in available_families(provider):
        family_frames(provider, family, ids)
    after = tree_hashes(case.input_root)
    assert before == after, "provider mutated its input files"


# ── CT-14: credential hygiene ────────────────────────────────────────────────


def test_ct14_no_credential_values_leak(
    case: ProviderCase,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    canary = "CANARY-SECRET-2f4e9d"
    monkeypatch.setenv("LASR_API_KEY", canary)
    monkeypatch.setenv("LASR_API_SECRET", canary)
    with caplog.at_level(logging.DEBUG):
        provider = case.factory()
        ids = master_ids(provider)
        capabilities = provider.capabilities()
        for family in available_families(provider):
            for frame in family_frames(provider, family, ids).values():
                assert canary not in repr(normalized_records(frame))
    assert canary not in repr(capabilities)
    assert canary not in caplog.text


# ── CT-15: corporate-action basis declared + D-011 grading ───────────────────


def test_ct15_market_basis_declared_and_frames_unadulterated(
    provider: DataProvider,
) -> None:
    capabilities = provider.capabilities()
    market = capabilities.family(FieldFamily.MARKET_DAILY)
    assert isinstance(market.corporate_action_basis, CorporateActionBasis)
    if not market.available:
        pytest.skip("market family unavailable")
    ids = master_ids(provider)
    frame = provider.fetch_prices(
        ids, *probe_window(provider, FieldFamily.MARKET_DAILY)
    )
    smuggled = set(frame.columns) & set(FM17_FORBIDDEN_PRICE_COLUMNS)
    assert not smuggled, (
        f"adjusted-price columns {smuggled} present; basis declaration "
        f"({market.corporate_action_basis.value}) would be dishonest (FM-17)"
    )


def test_ct15_d011_grading_from_the_declared_capabilities(
    provider: DataProvider,
) -> None:
    """D-011 split, driven by each provider's own record: revision-prone
    non-PIT families grade SNAPSHOT_STAMPED; the market retro window
    grades RETRO_WINDOW only once the adjustment-basis check passes."""
    capabilities = provider.capabilities()
    fundamentals = capabilities.family(FieldFamily.FUNDAMENTALS)
    if fundamentals.available and not fundamentals.supports_pit:
        assert (
            grade_dataset(FieldFamily.FUNDAMENTALS, fundamentals)
            is PitGrade.SNAPSHOT_STAMPED
        )
    market = capabilities.family(FieldFamily.MARKET_DAILY)
    if market.available and not market.supports_pit:
        if market.corporate_action_basis is CorporateActionBasis.UNKNOWN:
            assert (
                grade_dataset(FieldFamily.MARKET_DAILY, market)
                is PitGrade.SNAPSHOT_STAMPED
            ), "UNKNOWN basis without acknowledgment must not grade RETRO_WINDOW"
            assert (
                grade_dataset(
                    FieldFamily.MARKET_DAILY,
                    market,
                    adjustment_basis_acknowledged=True,
                )
                is PitGrade.RETRO_WINDOW
            ), "TM panel grades RETRO_WINDOW once the FM-17 guard is satisfied"
        else:
            assert (
                grade_dataset(FieldFamily.MARKET_DAILY, market) is PitGrade.RETRO_WINDOW
            )


# ── CT-16: interval-table PIT policing (G029; integration_queue RT-9) ────────
#
# The LT-016 leak shape at the CONTRACT level: a provider serving interval
# tables (universe membership; security-master listing intervals) must not
# expose CLOSURES knowable only later — every row carrying a closure fact
# must be stamped no earlier than the closure event itself, and every
# interval must ALSO be served as an open vintage stamped at (or before)
# its entry, so knowledge-truncating the rows at any as_of yields an
# honest membership view (no early exits, no backfilled entries).


def _interval_rows(
    family: FieldFamily, provider: DataProvider, table: str
) -> list[dict[str, Any]] | None:
    capabilities = provider.capabilities()
    capability = capabilities.family(family)
    if not capability.available:
        return None
    if not capability.supports_pit:
        return None
    frames = family_frames(provider, family, master_ids(provider))
    frame = frames.get(table)
    if frame is None:
        return None
    return normalized_records(frame)


@pytest.mark.parametrize(
    ("family", "table", "closure_field"),
    [
        (
            FieldFamily.UNIVERSE_MEMBERSHIP,
            "raw_universe_membership",
            "valid_to",
        ),
        (
            FieldFamily.SECURITY_MASTER,
            "raw_security_master",
            "delisting_date",
        ),
    ],
    ids=["universe_membership", "listing_intervals"],
)
def test_ct16_interval_closures_are_never_knowable_early(
    provider: DataProvider,
    family: FieldFamily,
    table: str,
    closure_field: str,
) -> None:
    """CT-16(a): a row carrying a closure fact must be stamped AT or
    AFTER the closure event — an early-stamped closure is a survivorship
    oracle (LT-016) for any knowledge-truncating consumer."""
    records = _interval_rows(family, provider, table)
    if records is None:
        pytest.skip(
            f"{family.value}: unavailable or supports_pit=false — interval "
            "PIT policing needs served knowledge stamps (refusal/stamping "
            "paths are CT-03/CT-10)"
        )
    checked = 0
    for record in records:
        closure = record.get(closure_field)
        if closure is None:
            continue
        knowledge = record.get("knowledge_time")
        assert isinstance(knowledge, datetime), (
            f"{table}: closure row without a knowledge stamp: {record!r}"
        )
        assert knowledge.date() >= closure, (
            f"{table}: closure {closure_field}={closure} stamped "
            f"{knowledge.isoformat()} — knowable BEFORE the exit "
            "(LT-016 leak shape; CT-16)"
        )
        checked += 1
    if not checked:
        pytest.skip(f"{table}: no closed intervals in this world/window")


def test_ct16_membership_closure_is_invisible_before_its_publication(
    provider: DataProvider,
) -> None:
    """CT-16(b): fetching the SAME membership window with an end BEFORE a
    closure's publication must serve the interval OPEN — the closure must
    neither appear early (survivorship oracle) nor take the membership
    with it (backfill shape). The security master has no windowed fetch
    (snapshot semantics; its truncation honesty is CT-10 + the canonical
    vintages), so this arm polices the membership surface."""
    family = FieldFamily.UNIVERSE_MEMBERSHIP
    records = _interval_rows(family, provider, "raw_universe_membership")
    if records is None:
        pytest.skip(
            "universe membership: unavailable or supports_pit=false — "
            "interval PIT policing needs served knowledge stamps"
        )
    coverage = sorted(provider.field_coverage(family))
    universe_id = coverage[0] if coverage else "unknown"
    start, _end = probe_window(provider, family)
    closed = [r for r in records if r.get("valid_to") is not None][:5]
    if not closed:
        pytest.skip("no closed membership intervals in this world/window")
    for record in closed:
        valid_to = record["valid_to"]
        early_end = valid_to - timedelta(days=1)
        if early_end <= record["valid_from"] or early_end < start:
            continue
        early = normalized_records(
            provider.fetch_universe_membership(universe_id, start, early_end)
        )
        key = (record["universe_id"], record["ticker"], record["exchange"])
        matches = [
            row
            for row in early
            if (row["universe_id"], row["ticker"], row["exchange"]) == key
            and row["valid_from"] == record["valid_from"]
        ]
        assert matches, (
            f"membership {key!r} vanished from a pre-closure window — "
            "backfilled membership (LT-016; CT-16)"
        )
        for row in matches:
            assert row.get("valid_to") is None or row["valid_to"] <= early_end, (
                f"membership {key!r}: closure {row['valid_to']} served in a "
                f"window ending {early_end} — knowable only later "
                "(LT-016 leak shape; CT-16)"
            )
