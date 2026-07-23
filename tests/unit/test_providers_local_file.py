"""Unit tests: local-file (AlphaSense-template-shaped) adapter (G018).

Two halves:

- loader integrity: every malformed-extract condition raises
  ``IntegrityError`` (quarantine, never repair — provider_contract.md §3);
- adapter behavior against the committed SYNTHETIC fixture: the §4.2
  evidence-fixed capability record, the D-012 price-field guard, the
  A-001 vintage guard, family routing (actuals vs FY+1/FY+2 consensus),
  the workbook gap/empty patterns, and window/id error paths.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from lasr.core.enums import RevisionSupport
from lasr.core.errors import TimeSemanticsError
from lasr.data.providers import (
    DERIVED_CALENDAR_ID,
    CapabilityError,
    CorporateActionBasis,
    CsvTemplateExtractLoader,
    FieldFamily,
    FieldUnavailableError,
    HistoryUnavailableError,
    IntegrityError,
    LocalFileProvider,
    ProviderId,
    UnknownProviderIdError,
)
from lasr.data.providers.local_file import PROVIDER_NAME

pytestmark = pytest.mark.unit

FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1] / "fixtures" / "provider" / "template_extracts"
)

SYNA = ProviderId("SYNA", "XNAS")
SYNC = ProviderId("SYNC", "XNAS")
SYND = ProviderId("SYND", "XTSE")
ALL_IDS = [
    SYNA,
    ProviderId("SYNB", "XNYS"),
    SYNC,
    SYND,
    ProviderId("SYNE", "XLON"),
    ProviderId("SYNF", "XNAS"),
]

MARKET_WINDOW = (date(2024, 1, 2), date(2025, 6, 27))
FUND_WINDOW = (date(2019, 12, 31), date(2025, 3, 31))
EST_WINDOW = (date(2025, 12, 31), date(2027, 3, 31))


@pytest.fixture(scope="module")
def provider() -> LocalFileProvider:
    return LocalFileProvider(FIXTURE_ROOT)


# ── loader integrity paths ───────────────────────────────────────────────────


def write_minimal_extract(root: Path) -> Path:
    extract = root / "FAKE__XTST"
    extract.mkdir(parents=True)
    (extract / "metadata.json").write_text(
        json.dumps(
            {
                "ticker": "FAKE",
                "exchange": "XTST",
                "version_type": "latest_filing",
                "selected_currency": "USD",
                "period_type": "FY",
            }
        ),
        encoding="utf-8",
    )
    (extract / "front_page.csv").write_text(
        "excel_code,label,value\n"
        "NAME,Company Name,Fake Test Corp\n"
        "TRADING_CURR,Trading Currency,USD\n",
        encoding="utf-8",
    )
    (extract / "financial_statements.csv").write_text(
        "excel_code,label,unit,FY-1,FY0,FY1\n"
        "FINANCIAL_PERIOD_END_DATE,Period End,,2023-12-31,2024-12-31,2025-12-31\n"
        "REV,Revenue,millions_of_selected_currency,10.0,11.0,12.5\n",
        encoding="utf-8",
    )
    (extract / "trading_multiples.csv").write_text(
        "CLOSE__date,CLOSE__value,MCAP__date,MCAP__value\n"
        "2024-01-02,10.0,2024-01-02,1000.0\n"
        "2024-01-03,10.5,2024-01-03,1050.0\n",
        encoding="utf-8",
    )
    return extract


class TestLoaderIntegrity:
    def test_minimal_extract_loads(self, tmp_path: Path) -> None:
        write_minimal_extract(tmp_path)
        provider = LocalFileProvider(tmp_path)
        assert provider.fetch_security_master().shape[0] == 1

    def test_missing_root_raises(self, tmp_path: Path) -> None:
        with pytest.raises(IntegrityError, match="not a directory"):
            LocalFileProvider(tmp_path / "nowhere")

    def test_empty_root_raises(self, tmp_path: Path) -> None:
        with pytest.raises(IntegrityError, match="no template extracts"):
            LocalFileProvider(tmp_path)

    def test_metadata_missing_key_raises(self, tmp_path: Path) -> None:
        extract = write_minimal_extract(tmp_path)
        payload = json.loads((extract / "metadata.json").read_text())
        del payload["version_type"]
        (extract / "metadata.json").write_text(json.dumps(payload))
        with pytest.raises(IntegrityError, match="version_type"):
            LocalFileProvider(tmp_path)

    def test_front_page_bad_header_raises(self, tmp_path: Path) -> None:
        extract = write_minimal_extract(tmp_path)
        (extract / "front_page.csv").write_text("code,name,val\nNAME,x,y\n")
        with pytest.raises(IntegrityError, match="header"):
            LocalFileProvider(tmp_path)

    def test_missing_trading_curr_raises(self, tmp_path: Path) -> None:
        extract = write_minimal_extract(tmp_path)
        (extract / "front_page.csv").write_text(
            "excel_code,label,value\nNAME,Company Name,Fake Test Corp\n"
        )
        with pytest.raises(IntegrityError, match="TRADING_CURR"):
            LocalFileProvider(tmp_path)

    def test_grid_without_period_end_row_raises(self, tmp_path: Path) -> None:
        extract = write_minimal_extract(tmp_path)
        (extract / "financial_statements.csv").write_text(
            "excel_code,label,unit,FY-1,FY0,FY1\n"
            "REV,Revenue,millions_of_selected_currency,10.0,11.0,12.5\n"
        )
        with pytest.raises(IntegrityError, match="FINANCIAL_PERIOD_END_DATE"):
            LocalFileProvider(tmp_path)

    def test_grid_bad_period_label_raises(self, tmp_path: Path) -> None:
        extract = write_minimal_extract(tmp_path)
        (extract / "financial_statements.csv").write_text(
            "excel_code,label,unit,Q-1,Q0,Q1\n"
            "FINANCIAL_PERIOD_END_DATE,Period End,,2023-12-31,2024-12-31,2025-12-31\n"
        )
        with pytest.raises(IntegrityError, match="relative grid"):
            LocalFileProvider(tmp_path)

    def test_grid_non_numeric_value_raises(self, tmp_path: Path) -> None:
        extract = write_minimal_extract(tmp_path)
        (extract / "financial_statements.csv").write_text(
            "excel_code,label,unit,FY-1,FY0\n"
            "FINANCIAL_PERIOD_END_DATE,Period End,,2023-12-31,2024-12-31\n"
            "REV,Revenue,millions_of_selected_currency,ten,11.0\n"
        )
        with pytest.raises(IntegrityError, match="invalid numeric"):
            LocalFileProvider(tmp_path)

    def test_ratios_grid_mismatch_raises(self, tmp_path: Path) -> None:
        extract = write_minimal_extract(tmp_path)
        (extract / "ratios.csv").write_text(
            "excel_code,label,unit,FY-1,FY0,FY1\n"
            "FINANCIAL_PERIOD_END_DATE,Period End,,2023-06-30,2024-06-30,2025-06-30\n"
            "ROE,Return on Equity,percent,0.1,0.2,\n"
        )
        with pytest.raises(IntegrityError, match="disagrees"):
            LocalFileProvider(tmp_path)

    def test_duplicate_metric_across_grids_raises(self, tmp_path: Path) -> None:
        extract = write_minimal_extract(tmp_path)
        (extract / "ratios.csv").write_text(
            "excel_code,label,unit,FY-1,FY0,FY1\n"
            "FINANCIAL_PERIOD_END_DATE,Period End,,2023-12-31,2024-12-31,2025-12-31\n"
            "REV,Revenue,millions_of_selected_currency,10.0,11.0,\n"
        )
        with pytest.raises(IntegrityError, match="duplicated across"):
            LocalFileProvider(tmp_path)

    def test_one_sided_tm_pair_raises(self, tmp_path: Path) -> None:
        extract = write_minimal_extract(tmp_path)
        (extract / "trading_multiples.csv").write_text(
            "CLOSE__date,CLOSE__value\n2024-01-02,\n"
        )
        with pytest.raises(IntegrityError, match="one-sided"):
            LocalFileProvider(tmp_path)

    def test_unpaired_tm_header_raises(self, tmp_path: Path) -> None:
        extract = write_minimal_extract(tmp_path)
        (extract / "trading_multiples.csv").write_text(
            "CLOSE__date,MCAP__value\n2024-01-02,1.0\n"
        )
        with pytest.raises(IntegrityError, match="pair"):
            LocalFileProvider(tmp_path)

    def test_descending_tm_dates_raise(self, tmp_path: Path) -> None:
        extract = write_minimal_extract(tmp_path)
        (extract / "trading_multiples.csv").write_text(
            "CLOSE__date,CLOSE__value\n2024-01-03,10.0\n2024-01-02,10.5\n"
        )
        with pytest.raises(IntegrityError, match="ascending"):
            LocalFileProvider(tmp_path)

    def test_duplicate_extract_identity_raises(self, tmp_path: Path) -> None:
        write_minimal_extract(tmp_path)
        duplicate = tmp_path / "FAKE__XTST_COPY"
        duplicate.mkdir()
        source = tmp_path / "FAKE__XTST"
        for name in (
            "metadata.json",
            "front_page.csv",
            "financial_statements.csv",
            "trading_multiples.csv",
        ):
            (duplicate / name).write_text((source / name).read_text())
        with pytest.raises(IntegrityError, match="duplicate template extract"):
            LocalFileProvider(tmp_path)

    def test_loader_discovery_is_sorted(self) -> None:
        loader = CsvTemplateExtractLoader()
        names = [p.name for p in loader.discover(FIXTURE_ROOT)]
        assert names == sorted(names)
        assert len(names) == 6


# ── §4.2 evidence-fixed capability record ────────────────────────────────────


class TestCapabilityRecord:
    def test_every_cross_family_flag_is_false(
        self, provider: LocalFileProvider
    ) -> None:
        caps = provider.capabilities()
        assert caps.provider_name == PROVIDER_NAME
        assert not caps.supports_universe_screening  # gap §1
        assert not caps.supports_publication_timestamps  # gap §3
        assert not caps.supports_delistings  # gap §1
        assert not caps.supports_bid_ask  # gap §2
        assert not caps.supports_borrow  # gap §7
        assert not caps.supports_index_membership  # gap §8
        assert not caps.supports_estimate_history  # gap §4
        assert not caps.supports_vintages  # Data!N2:O3 (A-001)

    def test_supports_pit_false_for_every_family(
        self, provider: LocalFileProvider
    ) -> None:
        for family, capability in provider.capabilities().families.items():
            assert not capability.supports_pit, family.value

    def test_family_rows_match_the_fixed_table(
        self, provider: LocalFileProvider
    ) -> None:
        families = provider.capabilities().families
        market = families[FieldFamily.MARKET_DAILY]
        assert market.available
        assert market.revision_support is RevisionSupport.LATEST_ONLY
        assert market.history_start is None  # depth NOT_ESTABLISHED
        assert market.corporate_action_basis is CorporateActionBasis.UNKNOWN
        fundamentals = families[FieldFamily.FUNDAMENTALS]
        assert fundamentals.available
        assert fundamentals.revision_support is RevisionSupport.LATEST_ONLY
        assert "FY-5..FY+2" in fundamentals.notes  # E-G012-06 window note
        estimates = families[FieldFamily.ESTIMATES]
        assert estimates.available
        assert estimates.revision_support is RevisionSupport.NONE
        for family in (FieldFamily.SECURITY_MASTER, FieldFamily.CLASSIFICATIONS):
            assert families[family].available
            assert families[family].revision_support is RevisionSupport.NONE
        for family in (
            FieldFamily.CORPORATE_ACTIONS,
            FieldFamily.UNIVERSE_MEMBERSHIP,
            FieldFamily.BORROW,
            FieldFamily.FX,
        ):
            assert not families[family].available, family.value
        calendar = families[FieldFamily.CALENDAR]
        assert calendar.available
        assert "derived" in calendar.notes  # FM-08 derived-with-note

    def test_market_coverage_is_the_d012_pair_plus_tm_codes(
        self, provider: LocalFileProvider
    ) -> None:
        coverage = provider.field_coverage(FieldFamily.MARKET_DAILY)
        assert {"close", "market_cap"} <= coverage
        assert {"EV", "PE", "PE_ADJ", "EV_TO_EBITDA", "P_TO_BV"} <= coverage
        assert not {"open", "high", "low", "volume"} & coverage


# ── error paths and routing against the fixture ─────────────────────────────


class TestAdapterBehavior:
    @pytest.mark.parametrize("field", ["open", "high", "low", "volume"])
    def test_d012_ohlv_requests_refused(
        self, provider: LocalFileProvider, field: str
    ) -> None:
        with pytest.raises(FieldUnavailableError, match="VP-01"):
            provider.fetch_prices([SYNA], *MARKET_WINDOW, fields=(field,))

    def test_unknown_price_field_refused(self, provider: LocalFileProvider) -> None:
        with pytest.raises(FieldUnavailableError, match="not servable"):
            provider.fetch_prices([SYNA], *MARKET_WINDOW, fields=("total_return",))

    @pytest.mark.parametrize("vintage", ["as_reported", "all"])
    def test_a001_vintage_guard(
        self, provider: LocalFileProvider, vintage: str
    ) -> None:
        with pytest.raises(CapabilityError, match="latest_filing"):
            provider.fetch_fundamentals(
                [SYNA],
                ["REV"],
                *FUND_WINDOW,
                vintage=vintage,  # type: ignore[arg-type]
            )

    def test_unknown_metric_refused(self, provider: LocalFileProvider) -> None:
        with pytest.raises(FieldUnavailableError, match="NOT_A_METRIC"):
            provider.fetch_fundamentals([SYNA], ["NOT_A_METRIC"], *FUND_WINDOW)

    def test_unknown_id_raises(self, provider: LocalFileProvider) -> None:
        with pytest.raises(UnknownProviderIdError, match="ZZZZ"):
            provider.fetch_prices([ProviderId("ZZZZ", "XNAS")], *MARKET_WINDOW)

    def test_window_overflow_raises_not_truncates(
        self, provider: LocalFileProvider
    ) -> None:
        start, end = MARKET_WINDOW
        with pytest.raises(HistoryUnavailableError, match="not silently truncated"):
            provider.fetch_prices([SYNA], start, end.replace(year=end.year + 1))

    def test_inverted_window_raises(self, provider: LocalFileProvider) -> None:
        with pytest.raises(TimeSemanticsError, match="inverted"):
            provider.fetch_prices([SYNA], date(2024, 6, 1), date(2024, 1, 1))

    def test_unavailable_families_refuse_with_gap_citation(
        self, provider: LocalFileProvider
    ) -> None:
        window = MARKET_WINDOW
        with pytest.raises(CapabilityError, match="gap §5"):
            provider.fetch_corporate_actions([SYNA], *window)
        with pytest.raises(CapabilityError, match="gap §7"):
            provider.fetch_borrow([SYNA], *window)
        with pytest.raises(CapabilityError, match="gap §8"):
            provider.fetch_universe_membership("russell3000", *window)
        with pytest.raises(CapabilityError, match="FM-24"):
            provider.fetch_fx_rates([("USD", "CAD")], *window)

    def test_unknown_calendar_refused(self, provider: LocalFileProvider) -> None:
        with pytest.raises(FieldUnavailableError, match="XNYS"):
            provider.fetch_trading_calendar("XNYS", *MARKET_WINDOW)

    def test_fundamentals_serve_actuals_only(self, provider: LocalFileProvider) -> None:
        """FY+1/FY+2 grid columns are consensus, routed to estimates —
        fetch_fundamentals never returns them. Structurally double-locked:
        the fundamentals available_history itself ends at the latest
        *actual* period end, so a window reaching into forecast periods is
        refused rather than truncated."""
        frame = provider.fetch_fundamentals([SYNA], ["REV"], *FUND_WINDOW)
        assert set(frame["fiscal_period"]) == {
            "FY-5",
            "FY-4",
            "FY-3",
            "FY-2",
            "FY-1",
            "FY0",
        }
        assert set(frame["version_type"]) == {"latest_filing"}
        assert set(frame["unit"]) == {"millions_of_selected_currency"}

    def test_estimates_serve_forward_columns_only(
        self, provider: LocalFileProvider
    ) -> None:
        frame = provider.fetch_estimates([SYNA], ["REV"], *EST_WINDOW)
        assert set(frame["forecast_period"]) == {"FY1", "FY2"}
        # gap §4: statistic type NOT_ESTABLISHED — never fabricated.
        assert "stat" not in frame.columns

    def test_metric_without_consensus_yields_empty_estimates(
        self, provider: LocalFileProvider
    ) -> None:
        frame = provider.fetch_estimates([SYNA], ["EBIT"], *EST_WINDOW)
        assert frame.shape[0] == 0
        assert list(frame.columns)  # conformant empty frame, not None

    def test_all_empty_metric_row_yields_empty_frame(
        self, provider: LocalFileProvider
    ) -> None:
        """BOOK_VALUE mirrors NVDA's 0-of-8 rows: covered, but empty
        (CT-12 valid-but-empty)."""
        assert "BOOK_VALUE" in provider.field_coverage(FieldFamily.FUNDAMENTALS)
        frame = provider.fetch_fundamentals([SYNA], ["BOOK_VALUE"], *FUND_WINDOW)
        assert frame.shape[0] == 0

    def test_non_payer_dps_is_empty_not_fabricated(
        self, provider: LocalFileProvider
    ) -> None:
        frame = provider.fetch_fundamentals([SYNC], ["DPS"], *FUND_WINDOW)
        assert frame.shape[0] == 0

    def test_unadjusted_ltm_gaps_surface_in_metrics(
        self, provider: LocalFileProvider
    ) -> None:
        """The two ~3-month holes (E-G012-10) are visible in PE but not in
        the full-series PE_ADJ."""
        gapped = provider.fetch_market_metrics(
            [SYNA], ["PE"], date(2024, 8, 1), date(2024, 10, 25)
        )
        full = provider.fetch_market_metrics(
            [SYNA], ["PE_ADJ"], date(2024, 8, 1), date(2024, 10, 25)
        )
        assert gapped.shape[0] == 0
        assert full.shape[0] > 50

    def test_empty_tm_pair_is_covered_but_empty(
        self, provider: LocalFileProvider
    ) -> None:
        frame = provider.fetch_market_metrics([SYNA], ["P_TO_BV"], *MARKET_WINDOW)
        assert frame.shape[0] == 0

    def test_prices_carry_trading_currency(self, provider: LocalFileProvider) -> None:
        frame = provider.fetch_prices([SYND], date(2024, 1, 2), date(2024, 1, 5))
        assert set(frame["currency"]) == {"CAD"}

    def test_classification_empty_cell_skipped_not_fabricated(
        self, provider: LocalFileProvider
    ) -> None:
        frame = provider.fetch_classifications(
            [ProviderId("SYNF", "XNAS")], ["gics_l1", "gics_l4"]
        )
        assert set(frame["scheme"]) == {"gics_l1"}  # SYNF has no L4 value

    def test_calendar_is_union_of_observed_dates(
        self, provider: LocalFileProvider
    ) -> None:
        frame = provider.fetch_trading_calendar(
            DERIVED_CALENDAR_ID, date(2024, 1, 2), date(2024, 1, 12)
        )
        days = list(frame["event_date"])
        assert days == sorted(set(days))
        assert all(d.weekday() < 5 for d in days)
        assert set(frame["calendar_id"]) == {DERIVED_CALENDAR_ID}

    def test_offset_fiscal_year_periods_served(
        self, provider: LocalFileProvider
    ) -> None:
        frame = provider.fetch_fundamentals(
            [ProviderId("SYNE", "XLON")], ["REV"], *FUND_WINDOW
        )
        assert date(2025, 3, 31) in set(frame["period_end"])

    def test_available_history_matches_fixture_construction(
        self, provider: LocalFileProvider
    ) -> None:
        assert provider.available_history(FieldFamily.MARKET_DAILY) == MARKET_WINDOW
        assert provider.available_history(FieldFamily.FUNDAMENTALS) == FUND_WINDOW
        assert provider.available_history(FieldFamily.ESTIMATES) == EST_WINDOW
        assert provider.available_history(FieldFamily.SECURITY_MASTER) == (None, None)
        assert provider.available_history(FieldFamily.BORROW) == (None, None)
