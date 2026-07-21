"""Regenerates the SYNTHETIC template-extract fixture (G018).

Every value under ``template_extracts/`` is INVENTED — six fake securities
with seeded random-walk prices and made-up fundamentals. No real market or
issuer data of any kind (in particular: no NVDA data). The layout mimics
the workbook facts documented in
``docs/data/workbook_schema/w2_nvda_template.md``:

- FY-5..FY+2 relative fiscal grid; actuals in FY-5..FY0, consensus-style
  non-integer values in FY1/FY2 for a subset of metrics; one all-empty
  metric row (``BOOK_VALUE``, mirroring the 0-of-8 rows);
- ``latest_filing`` as the only version type (`Data!N2:O3`);
- TM daily panel as per-metric (date, value) column pairs with ragged
  lengths: full daily series for CLOSE/MCAP/EV/`_ADJ` multiples, two
  ~3-month holes in the unadjusted-LTM multiples (E-G012-10), and one
  header-only empty pair (``P_TO_BV``);
- a W1-style metric-catalog subset with per-row units.

Deterministic: fixed seed, fixed calendar arithmetic. Run from the repo
root with ``uv run python tests/fixtures/provider/generate_template_extracts.py``.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np

SEED = 20180
OUT_ROOT = Path(__file__).resolve().parent / "template_extracts"

WINDOW_START = date(2024, 1, 1)  # TM B4/C4 user-set window start
WINDOW_END = date(2025, 6, 30)  # TM B5/C5 user-set window end
FIRST_TRADING_DAY = date(2024, 1, 2)

#: The two ~3-month holes in the unadjusted-LTM series (values disappear
#: until the next quarter's LTM fundamentals arrive — E-G012-10 pattern).
LTM_GAPS = (
    (date(2024, 7, 30), date(2024, 10, 27)),
    (date(2025, 1, 30), date(2025, 4, 27)),
)

FULL_PAIRS = ("CLOSE", "MCAP", "EV", "PE_ADJ")
GAPPED_PAIRS = ("PE", "EV_TO_EBITDA")
EMPTY_PAIRS = ("P_TO_BV",)  # header-only, no data returned (TM AS/AT pattern)

GRID_LABELS = ("FY-5", "FY-4", "FY-3", "FY-2", "FY-1", "FY0", "FY1", "FY2")

#: (code, label, unit) for the statement grid — W1-catalog subset.
FS_METRICS = (
    ("REV", "Revenue", "millions_of_selected_currency"),
    ("EBITDA", "EBITDA", "millions_of_selected_currency"),
    ("EBIT", "EBIT", "millions_of_selected_currency"),
    ("NI_BASIC", "Net Income to Common Shareholders", "millions_of_selected_currency"),
    ("EPS_WAD", "Earnings Per Share - WAD", "selected_currency_per_share"),
    ("DPS", "Dividends Per Share", "selected_currency_per_share"),
    ("TOT_ASSET", "Total Assets", "millions_of_selected_currency"),
    ("DEBT_TOTAL", "Total Debt", "millions_of_selected_currency"),
    ("OCF", "Operating Cash Flow", "millions_of_selected_currency"),
    ("CAPEX", "Capex", "millions_of_selected_currency"),
    ("BOOK_VALUE", "Book Value", "millions_of_selected_currency"),  # all-empty
)

#: Metrics whose FY1/FY2 cells carry consensus-style values.
CONSENSUS_METRICS = frozenset({"REV", "EBITDA", "EPS_WAD"})

RATIO_METRICS = (
    ("ROE", "Return on Equity", "percent"),
    ("ROA", "Return on Assets", "percent"),
    ("CURRENT_RATIO", "Current Ratio", "ratio"),
)


@dataclass(frozen=True)
class FakeSecurity:
    ticker: str
    exchange: str
    exchange_display: str
    name: str
    currency: str
    country_exch: str
    country_hq: str
    sector: str
    sub_industry: str | None
    fy0_end: date  # fiscal-year-0 period end
    base_price: float
    skip_metrics: frozenset[str] = frozenset()


SECURITIES = (
    FakeSecurity(
        ticker="SYNA",
        exchange="XNAS",
        exchange_display="Synthetic Nasdaq",
        name="Synthetic Aurora Corp",
        currency="USD",
        country_exch="US",
        country_hq="United States",
        sector="Information Technology",
        sub_industry="Synthetic Semiconductors",
        fy0_end=date(2024, 12, 31),
        base_price=140.0,
    ),
    FakeSecurity(
        ticker="SYNB",
        exchange="XNYS",
        exchange_display="Synthetic NYSE",
        name="Synthetic Borealis Inc",
        currency="USD",
        country_exch="US",
        country_hq="United States",
        sector="Industrials",
        sub_industry="Synthetic Machinery",
        fy0_end=date(2024, 12, 31),
        base_price=55.0,
    ),
    FakeSecurity(
        ticker="SYNC",
        exchange="XNAS",
        exchange_display="Synthetic Nasdaq",
        name="Synthetic Cascade PLC",
        currency="USD",
        country_exch="US",
        country_hq="Ireland",
        sector="Health Care",
        sub_industry="Synthetic Biotech",
        fy0_end=date(2024, 12, 31),
        base_price=18.0,
        skip_metrics=frozenset({"DPS"}),  # non-payer: empty DPS row
    ),
    FakeSecurity(
        ticker="SYND",
        exchange="XTSE",
        exchange_display="Synthetic Toronto",
        name="Synthetic Dominion Ltd",
        currency="CAD",
        country_exch="CA",
        country_hq="Canada",
        sector="Materials",
        sub_industry="Synthetic Mining",
        fy0_end=date(2024, 12, 31),
        base_price=32.0,
    ),
    FakeSecurity(
        ticker="SYNE",
        exchange="XLON",
        exchange_display="Synthetic London",
        name="Synthetic Ember Group",
        currency="GBP",
        country_exch="GB",
        country_hq="United Kingdom",
        sector="Consumer Staples",
        sub_industry="Synthetic Beverages",
        fy0_end=date(2025, 3, 31),  # offset fiscal year (March-ending)
        base_price=8.5,
    ),
    FakeSecurity(
        ticker="SYNF",
        exchange="XNAS",
        exchange_display="Synthetic Nasdaq",
        name="Synthetic Flux Holdings",
        currency="USD",
        country_exch="US",
        country_hq="United States",
        sector="Financials",
        sub_industry=None,  # empty FP cell: classification valid-but-empty
        fy0_end=date(2024, 12, 31),
        base_price=210.0,
    ),
)


def weekdays(start: date, end: date) -> list[date]:
    days = []
    day = start
    while day <= end:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def in_gap(day: date) -> bool:
    return any(lo <= day <= hi for lo, hi in LTM_GAPS)


def fiscal_period_ends(fy0_end: date) -> dict[str, date]:
    return {
        label: fy0_end.replace(year=fy0_end.year + offset)
        for label, offset in zip(GRID_LABELS, range(-5, 3), strict=True)
    }


def write_csv(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)


def build_security(security: FakeSecurity, rng: np.random.Generator) -> None:
    out_dir = OUT_ROOT / f"{security.ticker}__{security.exchange}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # -- metadata.json (template controls) ------------------------------------
    metadata = {
        "synthetic": True,
        "note": (
            "SYNTHETIC FIXTURE - every value invented; generated by "
            "generate_template_extracts.py, seed 20180"
        ),
        "ticker": security.ticker,
        "exchange": security.exchange,
        "version_type": "latest_filing",
        "selected_currency": security.currency,
        "period_type": "FY",
        "window_start": WINDOW_START.isoformat(),
        "window_end": WINDOW_END.isoformat(),
    }
    (out_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )

    # -- front_page.csv --------------------------------------------------------
    front_rows: list[list[str]] = [["excel_code", "label", "value"]]
    front_rows += [
        ["NAME", "Company Name", security.name],
        ["COUNTRY_HQ", "Country of Headquaters", security.country_hq],
        ["TRADING_CURR", "Trading Currency", security.currency],
        ["SECTOR_GICS", "Sector (GICS L1)", security.sector],
        [
            "SUB_INDUSTRY_GICS",
            "Sub-Sector (GICS L4)",
            security.sub_industry or "",
        ],
        ["REPORTING_CURR", "Reporting Currency", security.currency],
        ["COUNTRY_EXCH", "Country of Stock Exchange", security.country_exch],
        ["EXCH", "Stock Exchange", security.exchange_display],
        [
            "FINANCIAL_PERIOD_END_DATE",
            "Financial Period End Date",
            security.fy0_end.isoformat(),
        ],
    ]
    write_csv(out_dir / "front_page.csv", front_rows)

    # -- fiscal grids -----------------------------------------------------------
    ends = fiscal_period_ends(security.fy0_end)
    header = ["excel_code", "label", "unit", *GRID_LABELS]
    period_row = [
        "FINANCIAL_PERIOD_END_DATE",
        "Financial Period End Date",
        "",
        *[ends[label].isoformat() for label in GRID_LABELS],
    ]

    def grid_rows(
        metrics: tuple[tuple[str, str, str], ...], base_scale: float
    ) -> list[list[str]]:
        rows = [header, period_row]
        for code, label, unit in metrics:
            if code == "BOOK_VALUE" or code in security.skip_metrics:
                rows.append([code, label, unit, *[""] * len(GRID_LABELS)])
                continue
            level = base_scale * float(rng.uniform(0.5, 5.0))
            growth = float(rng.uniform(1.02, 1.25))
            cells: list[str] = []
            for i, grid_label in enumerate(GRID_LABELS):
                is_forward = grid_label in ("FY1", "FY2")
                if is_forward and code not in CONSENSUS_METRICS:
                    cells.append("")
                    continue
                noise = float(rng.uniform(0.9, 1.1))
                value = level * (growth**i) * noise
                cells.append(f"{value:.4f}" if is_forward else f"{value:.2f}")
            rows.append([code, label, unit, *cells])
        return rows

    write_csv(out_dir / "financial_statements.csv", grid_rows(FS_METRICS, 1000.0))
    write_csv(out_dir / "ratios.csv", grid_rows(RATIO_METRICS, 0.05))

    # -- trading_multiples.csv ---------------------------------------------------
    days = weekdays(FIRST_TRADING_DAY, date(2025, 6, 27))  # last weekday <= window
    n = len(days)
    log_returns = rng.normal(loc=0.0003, scale=0.02, size=n - 1)
    closes = security.base_price * np.exp(np.concatenate(([0.0], np.cumsum(log_returns))))
    shares_mn = float(rng.uniform(200.0, 2000.0))
    net_debt_mn = float(rng.uniform(-500.0, 4000.0))
    pe_level = float(rng.uniform(12.0, 45.0))
    ev_ebitda_level = float(rng.uniform(6.0, 30.0))

    series: dict[str, list[tuple[date, float]]] = {code: [] for code in FULL_PAIRS}
    series |= {code: [] for code in GAPPED_PAIRS}
    series |= {code: [] for code in EMPTY_PAIRS}
    for i, day in enumerate(days):
        close = float(closes[i])
        mcap = close * shares_mn
        series["CLOSE"].append((day, round(close, 4)))
        series["MCAP"].append((day, round(mcap, 1)))
        series["EV"].append((day, round(mcap + net_debt_mn, 1)))
        series["PE_ADJ"].append(
            (day, round(pe_level * float(rng.uniform(0.93, 1.07)), 6))
        )
        if not in_gap(day):
            series["PE"].append(
                (day, round(pe_level * float(rng.uniform(0.9, 1.1)), 6))
            )
            series["EV_TO_EBITDA"].append(
                (day, round(ev_ebitda_level * float(rng.uniform(0.9, 1.1)), 6))
            )

    codes = [*FULL_PAIRS, *GAPPED_PAIRS, *EMPTY_PAIRS]
    tm_header: list[str] = []
    for code in codes:
        tm_header += [f"{code}__date", f"{code}__value"]
    max_len = max(len(series[code]) for code in codes)
    tm_rows: list[list[str]] = [tm_header]
    for row_index in range(max_len):
        row: list[str] = []
        for code in codes:
            observations = series[code]
            if row_index < len(observations):
                day, value = observations[row_index]
                row += [day.isoformat(), repr(value)]
            else:
                row += ["", ""]
        tm_rows.append(row)
    write_csv(out_dir / "trading_multiples.csv", tm_rows)


def main() -> None:
    rng = np.random.Generator(np.random.PCG64(SEED))
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    for security in SECURITIES:  # fixed order: deterministic child streams
        build_security(security, rng)
    print(f"wrote {len(SECURITIES)} synthetic template extracts under {OUT_ROOT}")


if __name__ == "__main__":
    main()
