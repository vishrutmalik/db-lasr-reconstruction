"""Synthetic provider unit tests (G019): NB-1 typed refusal (both
adapters), vintage semantics, guards, bundle machinery."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from lasr.core.enums import PitGrade
from lasr.core.errors import TimeSemanticsError
from lasr.data.providers import (
    CorporateActionBasis,
    DuplicateProviderIdError,
    FieldFamily,
    FieldUnavailableError,
    HistoryUnavailableError,
    LocalFileProvider,
    ProviderId,
    SyntheticProvider,
    UnknownProviderIdError,
    require_unique_ids,
)
from lasr.data.providers.synthetic_provider import PROVIDER_NAME
from lasr.data.synthetic import ScenarioConfig

pytestmark = pytest.mark.unit

LOCAL_FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1] / "fixtures" / "provider" / "template_extracts"
)

CONFIG = ScenarioConfig("baseline", seed=424242, n_securities=16, n_years=3)


@pytest.fixture(scope="module")
def provider() -> SyntheticProvider:
    return SyntheticProvider(CONFIG)


@pytest.fixture(scope="module")
def ids(provider: SyntheticProvider) -> list[ProviderId]:
    frame = provider.fetch_security_master()
    return [
        ProviderId(value=r["ticker"], exchange=r["exchange"])
        for r in frame.to_dict("records")
    ]


@pytest.fixture(scope="module")
def window(provider: SyntheticProvider) -> tuple[date, date]:
    earliest, latest = provider.available_history(FieldFamily.MARKET_DAILY)
    assert earliest is not None and latest is not None
    return (earliest, latest)


class TestNb1DuplicateIds:
    """G018 verification NB-1: duplicated ProviderIds must not yield
    PK-violating frames — typed REFUSAL in both adapters."""

    def test_helper_refuses_duplicates(self) -> None:
        pid = ProviderId("SYN0001", "XSYA")
        with pytest.raises(DuplicateProviderIdError, match="SYN0001"):
            require_unique_ids([pid, pid])

    def test_helper_passes_unique_ids_through(self) -> None:
        pids = [ProviderId("SYN0001", "XSYA"), ProviderId("SYN0002", "XSYA")]
        assert require_unique_ids(pids) == tuple(pids)

    def test_synthetic_provider_refuses_duplicates(
        self,
        provider: SyntheticProvider,
        ids: list[ProviderId],
        window: tuple[date, date],
    ) -> None:
        with pytest.raises(DuplicateProviderIdError):
            provider.fetch_prices([ids[0], ids[0]], *window)

    def test_local_file_provider_refuses_duplicates(self) -> None:
        local = LocalFileProvider(LOCAL_FIXTURE_ROOT)
        frame = local.fetch_security_master()
        record = frame.to_dict("records")[0]
        pid = ProviderId(record["ticker"], record["exchange"])
        earliest, latest = local.available_history(FieldFamily.MARKET_DAILY)
        assert earliest is not None and latest is not None
        with pytest.raises(DuplicateProviderIdError):
            local.fetch_prices([pid, pid], earliest, latest)


class TestGuards:
    def test_unknown_id_refused(
        self, provider: SyntheticProvider, window: tuple[date, date]
    ) -> None:
        with pytest.raises(UnknownProviderIdError):
            provider.fetch_prices([ProviderId("NOPE", "XXXX")], *window)

    def test_window_outside_history_refused(
        self, provider: SyntheticProvider, ids: list[ProviderId]
    ) -> None:
        earliest, latest = provider.available_history(FieldFamily.MARKET_DAILY)
        assert earliest is not None and latest is not None
        with pytest.raises(HistoryUnavailableError):
            provider.fetch_prices(ids[:1], earliest - timedelta(days=400), latest)

    def test_inverted_window_refused(
        self, provider: SyntheticProvider, ids: list[ProviderId]
    ) -> None:
        with pytest.raises(TimeSemanticsError):
            provider.fetch_prices(ids[:1], date(2011, 1, 1), date(2010, 1, 1))

    def test_unknown_metric_refused(
        self,
        provider: SyntheticProvider,
        ids: list[ProviderId],
        window: tuple[date, date],
    ) -> None:
        with pytest.raises(FieldUnavailableError):
            provider.fetch_market_metrics(ids[:1], ["NOT_A_METRIC"], *window)
        with pytest.raises(FieldUnavailableError):
            provider.fetch_fundamentals(ids[:1], ["NOT_A_METRIC"], *window)
        with pytest.raises(FieldUnavailableError):
            provider.fetch_classifications(ids[:1], ["not_a_scheme"])
        with pytest.raises(FieldUnavailableError):
            provider.fetch_universe_membership("NOT_A_UNIVERSE", *window)
        with pytest.raises(FieldUnavailableError):
            provider.fetch_trading_calendar("NOT_A_CALENDAR", *window)
        with pytest.raises(FieldUnavailableError):
            provider.fetch_fx_rates([("ZZZ", "YYY")], *window)

    def test_empty_ids_yield_empty_conformant_frame(
        self, provider: SyntheticProvider, window: tuple[date, date]
    ) -> None:
        frame = provider.fetch_prices([], *window)
        assert frame.shape[0] == 0
        assert list(frame.columns)


class TestOhlvService:
    def test_explicit_ohlv_request_is_served_not_refused(
        self,
        provider: SyntheticProvider,
        ids: list[ProviderId],
        window: tuple[date, date],
    ) -> None:
        """Contrast with the local adapter's D-012 refusal: the generator
        genuinely produces OHLV, so coverage includes it (CT-07 branch)."""
        frame = provider.fetch_prices(
            ids[:2], *window, fields=("open", "high", "low", "close", "volume")
        )
        for column in ("open", "high", "low", "close", "volume"):
            assert column in frame.columns
            assert frame[column].notna().all()

    def test_bar_consistency(
        self,
        provider: SyntheticProvider,
        ids: list[ProviderId],
        window: tuple[date, date],
    ) -> None:
        frame = provider.fetch_prices(
            ids[:4], *window, fields=("open", "high", "low", "close", "vwap")
        )
        for record in frame.to_dict("records"):
            assert record["low"] <= min(record["open"], record["close"])
            assert record["high"] >= max(record["open"], record["close"])
            assert record["low"] <= record["vwap"] <= record["high"]


class TestVintageSemantics:
    def find_restated_key(
        self, provider: SyntheticProvider, ids: list[ProviderId]
    ) -> tuple[ProviderId, str, str]:
        earliest, latest = provider.available_history(FieldFamily.FUNDAMENTALS)
        assert earliest is not None and latest is not None
        frame = provider.fetch_fundamentals(
            ids, ["NETINC"], earliest, latest, vintage="all"
        )
        counts: dict[tuple[str, str, str], int] = {}
        for r in frame.to_dict("records"):
            key = (r["ticker"], r["exchange"], r["fiscal_period"])
            counts[key] = counts.get(key, 0) + 1
        ticker, exchange, fiscal = next(k for k, n in counts.items() if n > 1)
        return (ProviderId(ticker, exchange), "NETINC", fiscal)

    def test_all_latest_as_reported_are_consistent(
        self, provider: SyntheticProvider, ids: list[ProviderId]
    ) -> None:
        pid, metric, fiscal = self.find_restated_key(provider, ids)
        earliest, latest = provider.available_history(FieldFamily.FUNDAMENTALS)
        assert earliest is not None and latest is not None

        def rows(vintage: str) -> list[dict]:
            frame = provider.fetch_fundamentals(
                [pid],
                [metric],
                earliest,
                latest,
                vintage=vintage,  # type: ignore[arg-type]
            )
            return [r for r in frame.to_dict("records") if r["fiscal_period"] == fiscal]

        all_rows = rows("all")
        latest_rows = rows("latest")
        first_rows = rows("as_reported")
        assert len(all_rows) == 2
        assert len(latest_rows) == 1 and len(first_rows) == 1
        assert latest_rows[0]["version_type"] == "restated"
        assert first_rows[0]["version_type"] == "as_reported"
        assert latest_rows[0]["knowledge_time"] > first_rows[0]["knowledge_time"]
        assert latest_rows[0]["value"] != first_rows[0]["value"]
        by_stamp = sorted(all_rows, key=lambda r: r["knowledge_time"])
        assert by_stamp[0]["value"] == first_rows[0]["value"]
        assert by_stamp[-1]["value"] == latest_rows[0]["value"]

    def test_estimate_window_end_governs_revision_visibility(
        self, provider: SyntheticProvider, ids: list[ProviderId]
    ) -> None:
        """CI-002 source-side: an earlier window end must never surface a
        LATER revision."""
        earliest, latest = provider.available_history(FieldFamily.ESTIMATES)
        assert earliest is not None and latest is not None
        full = provider.fetch_estimates(ids, ["EPS"], earliest, latest)
        early_end = earliest + (latest - earliest) // 2
        early = provider.fetch_estimates(ids, ["EPS"], earliest, early_end)
        full_stamps = {
            (r["ticker"], r["forecast_period"], r["period_end"]): r["knowledge_time"]
            for r in full.to_dict("records")
        }
        checked = 0
        for r in early.to_dict("records"):
            key = (r["ticker"], r["forecast_period"], r["period_end"])
            if key in full_stamps:
                assert r["knowledge_time"] <= full_stamps[key]
                checked += 1
        assert checked > 0


class TestCapabilitiesAndBundle:
    def test_capability_record_shape(self, provider: SyntheticProvider) -> None:
        caps = provider.capabilities()
        assert caps.provider_name == PROVIDER_NAME
        assert caps.supports_vintages and caps.supports_estimate_history
        assert caps.supports_delistings and caps.supports_index_membership
        for family in FieldFamily:
            record = caps.family(family)
            assert record.available, family
            expected_pit = family is not FieldFamily.CALENDAR
            assert record.supports_pit is expected_pit, family
        market = caps.family(FieldFamily.MARKET_DAILY)
        assert market.corporate_action_basis is CorporateActionBasis.UNADJUSTED

    def test_scenario_catalog_covers_all_lt_scenarios(
        self, provider: SyntheticProvider
    ) -> None:
        catalog = provider.scenario_catalog()
        assert {f"LT-{i:03d}" for i in range(1, 22)} <= catalog
        assert "baseline" in catalog

    def test_generate_bundle_grading_and_manifests(
        self, provider: SyntheticProvider
    ) -> None:
        bundle = provider.generate(CONFIG)
        assert set(bundle.datasets) == set(FieldFamily)
        for family, ref in bundle.datasets.items():
            if family is FieldFamily.CALENDAR:
                assert ref.pit_grade is PitGrade.SNAPSHOT_STAMPED
            else:
                assert ref.pit_grade is PitGrade.SYNTHETIC_TRUTH
            assert ref.manifest is not None
            assert ref.manifest.provider == PROVIDER_NAME
            assert ref.manifest.content_hash == ref.content_hash
            assert ref.tables, family
        assert bundle.sidecar.scenario_id == "baseline"
        assert "A-003" in bundle.sidecar.a003_banner

    def test_generate_bundle_carries_teeth_ablations(self) -> None:
        config = ScenarioConfig("LT-004", seed=7, n_securities=24, n_years=3)
        bundle = SyntheticProvider(config).generate(config)
        assert "control" in bundle.ablations
        control = bundle.ablations["control"]
        metrics = set(control.tables["raw_market_metrics"]["metric"])
        assert "FLEAK" not in metrics
        assert bundle.sidecar.feature("FLEAK").suspected_leak
