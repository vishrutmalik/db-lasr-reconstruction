"""Local-file provider: AlphaSense-template-shaped adapter (G018).

# arch: provider_contract.md §4.2. Reads *template extracts* — a typed
CSV/JSON representation of the AlphaSense company-template workbook
(`docs/data/workbook_schema/w2_nvda_template.md`) — from a caller-supplied
root directory. The xlsx→extract conversion is a thin I/O shim deferred
until openpyxl enters the dependency set (pyproject is frozen; G043 holds
the grant): the adapter *contract* is identical either way.

Template-extract layout (one directory per security,
``<TICKER>__<EXCHANGE>/``):

- ``metadata.json`` — template controls (`Front Page` C3:D5, `Data` sheet):
  ticker, exchange, ``version_type`` (`Data!N2:O3` — ``latest_filing`` is
  the template's only version type, A-001), selected currency, period
  type, TM window.
- ``front_page.csv`` (``excel_code,label,value``) — the FP snapshot fields
  (FM-01/03/04/33/34).
- ``financial_statements.csv`` / ``ratios.csv``
  (``excel_code,label,unit,<FY-5..FY2>``) — the relative fiscal grid
  (E-G012-06): 6 back + 2 forward periods; the
  ``FINANCIAL_PERIOD_END_DATE`` row carries per-column period ends (FS
  row 5). The ``unit`` column makes the W2 unit basis explicit (money in
  millions of the selected currency) — populated by the extract shim from
  the G013 dictionary, never guessed here.
- ``trading_multiples.csv`` — the TM dated panel: adjacent
  ``<CODE>__date,<CODE>__value`` column pairs, ragged lengths per pair
  (each pair carries its own dates because series lengths differ; the
  unadjusted-LTM series show ~3-month holes, E-G012-10).

Capability record is fixed by G012/G013 evidence (provider_contract.md
§4.2 table): everything PIT-false, ``latest_filing`` only, D-011/D-012
semantics. This adapter never fabricates fields (MP §14/§16) and never
writes anywhere (CT-13).
"""

from __future__ import annotations

import csv
import json
import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

from lasr.core.enums import RevisionSupport
from lasr.core.errors import TimeSemanticsError
from lasr.data.providers._frames import DataFrame, build_frame
from lasr.data.providers.base import (
    DEFAULT_PRICE_FIELDS,
    LISTED_ONLY_PRICE_FIELDS,
    CapabilityError,
    CorporateActionBasis,
    FamilyCapability,
    FieldFamily,
    FieldUnavailableError,
    HistoryUnavailableError,
    IntegrityError,
    ProviderCapabilities,
    ProviderId,
    UnknownProviderIdError,
)
from lasr.data.schemas.raw_classifications import RAW_CLASSIFICATIONS
from lasr.data.schemas.raw_estimates import RAW_ESTIMATES
from lasr.data.schemas.raw_fundamentals import RAW_FUNDAMENTALS
from lasr.data.schemas.raw_market_data import RAW_MARKET_DAILY, RAW_MARKET_METRICS
from lasr.data.schemas.raw_security_master import RAW_SECURITY_MASTER
from lasr.data.schemas.raw_trading import RAW_TRADING_CALENDARS

__all__ = [
    "DERIVED_CALENDAR_ID",
    "PROVIDER_NAME",
    "PROVIDER_VERSION",
    "CsvTemplateExtractLoader",
    "ExtractMetadata",
    "LocalFileProvider",
    "PeriodColumn",
    "SecurityExtract",
]

logger = logging.getLogger(__name__)

PROVIDER_NAME = "local_file_alphasense_template"
PROVIDER_VERSION = "1.0.0"

#: The only calendar this adapter serves: the union of observed TM panel
#: dates (FM-08 "derived-with-note"). Absence of a date means *unknown*,
#: never "holiday" — the extract window shows trading days only.
DERIVED_CALENDAR_ID = "local_observed"

#: fetch_prices field -> TM excel_code (FM-11, FM-25; renames documented
#: in field_mapping.md). D-012: nothing beyond this pair is servable.
_PRICE_FIELD_CODES: Mapping[str, str] = {"close": "CLOSE", "market_cap": "MCAP"}

#: Classification scheme -> Front Page excel_code (FM-33/34/35).
_CLASSIFICATION_SCHEME_CODES: Mapping[str, str] = {
    "country_exch": "COUNTRY_EXCH",
    "country_hq": "COUNTRY_HQ",
    "gics_l1": "SECTOR_GICS",
    "gics_l4": "SUB_INDUSTRY_GICS",
}

_SECURITY_MASTER_FIELDS = frozenset(
    {"ticker", "exchange", "name", "country", "trading_currency", "reporting_currency"}
)

_PERIOD_END_CODE = "FINANCIAL_PERIOD_END_DATE"
_GRID_FIXED_HEADER = ("excel_code", "label", "unit")
_FRONT_PAGE_HEADER = ("excel_code", "label", "value")
_METADATA_REQUIRED_KEYS = (
    "ticker",
    "exchange",
    "version_type",
    "selected_currency",
    "period_type",
)


# ── typed template-extract representation ────────────────────────────────────


@dataclass(frozen=True)
class ExtractMetadata:
    """Template controls of one extract (`Front Page` C3:D5 + `Data`)."""

    ticker: str
    exchange: str
    version_type: str  # Data!N2:O3 — `latest_filing` for AlphaSense
    selected_currency: str  # Data!A1:B1 selected currency code
    period_type: str  # Data!D1:E1, e.g. FY
    window_start: date | None = None  # TM B4/C4
    window_end: date | None = None  # TM B5/C5


@dataclass(frozen=True)
class PeriodColumn:
    """One relative fiscal-grid column (FS/RA row 4 label + row 5 end)."""

    label: str  # e.g. FY-3
    offset: int  # -5..2
    period_end: date


@dataclass(frozen=True)
class SecurityExtract:
    """One security's template extract, fully parsed and immutable."""

    metadata: ExtractMetadata
    front_page: Mapping[str, str]  # excel_code -> non-empty value
    period_columns: tuple[PeriodColumn, ...]
    fundamentals: Mapping[str, Mapping[str, float]]  # metric -> {label: value}
    fundamental_units: Mapping[str, str]  # metric -> unit
    multiples: Mapping[str, tuple[tuple[date, float], ...]]  # code -> series

    @property
    def provider_id(self) -> ProviderId:
        return ProviderId(value=self.metadata.ticker, exchange=self.metadata.exchange)


# ── CSV template-extract loader ──────────────────────────────────────────────


def _read_rows(path: Path) -> list[list[str]]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.reader(handle))
    except FileNotFoundError as exc:
        raise IntegrityError(f"missing extract file: {path}") from exc


def _parse_date(text: str, context: str) -> date:
    try:
        return date.fromisoformat(text.strip())
    except ValueError as exc:
        raise IntegrityError(f"{context}: invalid ISO date {text!r}") from exc


def _parse_float(text: str, context: str) -> float:
    try:
        return float(text)
    except ValueError as exc:
        raise IntegrityError(f"{context}: invalid numeric value {text!r}") from exc


class CsvTemplateExtractLoader:
    """Loads the CSV/JSON template-extract layout (module docstring).

    Every malformed-payload condition raises :class:`IntegrityError` —
    ingestion quarantines, never repairs (provider_contract.md §3).
    """

    def discover(self, root: Path) -> tuple[Path, ...]:
        """Extract directories under ``root`` (sorted — determinism)."""
        if not root.is_dir():
            raise IntegrityError(f"template-extract root is not a directory: {root}")
        return tuple(
            sorted(
                (p for p in root.iterdir() if (p / "metadata.json").is_file()),
                key=lambda p: p.name,
            )
        )

    def load(self, extract_dir: Path) -> SecurityExtract:
        """Parse one extract directory into a :class:`SecurityExtract`."""
        metadata = self._load_metadata(extract_dir / "metadata.json")
        front_page = self._load_front_page(extract_dir / "front_page.csv")
        fs_periods, fs_metrics, fs_units = self._load_grid(
            extract_dir / "financial_statements.csv", metadata.period_type
        )
        ratios_path = extract_dir / "ratios.csv"
        if ratios_path.is_file():
            ra_periods, ra_metrics, ra_units = self._load_grid(
                ratios_path, metadata.period_type
            )
            if ra_periods != fs_periods:
                raise IntegrityError(
                    f"{extract_dir.name}: ratios.csv period grid disagrees with "
                    "financial_statements.csv (FS/RA share row-5 period ends)"
                )
            overlap = sorted(set(fs_metrics) & set(ra_metrics))
            if overlap:
                raise IntegrityError(
                    f"{extract_dir.name}: metric codes duplicated across "
                    f"statement and ratio grids: {overlap!r}"
                )
            fs_metrics = {**fs_metrics, **ra_metrics}
            fs_units = {**fs_units, **ra_units}
        multiples = self._load_multiples(extract_dir / "trading_multiples.csv")
        if "TRADING_CURR" not in front_page:
            raise IntegrityError(
                f"{extract_dir.name}: front_page.csv lacks TRADING_CURR "
                "(required to emit price bars, FM-04)"
            )
        return SecurityExtract(
            metadata=metadata,
            front_page=front_page,
            period_columns=fs_periods,
            fundamentals={k: fs_metrics[k] for k in sorted(fs_metrics)},
            fundamental_units={k: fs_units[k] for k in sorted(fs_units)},
            multiples={k: multiples[k] for k in sorted(multiples)},
        )

    def _load_metadata(self, path: Path) -> ExtractMetadata:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise IntegrityError(f"unreadable metadata.json: {path} ({exc})") from exc
        if not isinstance(payload, dict):
            raise IntegrityError(f"{path}: metadata.json must hold an object")
        missing = [k for k in _METADATA_REQUIRED_KEYS if not payload.get(k)]
        if missing:
            raise IntegrityError(f"{path}: metadata.json missing keys {missing!r}")
        window_start = payload.get("window_start")
        window_end = payload.get("window_end")
        return ExtractMetadata(
            ticker=str(payload["ticker"]).strip(),
            exchange=str(payload["exchange"]).strip(),
            version_type=str(payload["version_type"]).strip(),
            selected_currency=str(payload["selected_currency"]).strip(),
            period_type=str(payload["period_type"]).strip(),
            window_start=(
                _parse_date(str(window_start), str(path)) if window_start else None
            ),
            window_end=_parse_date(str(window_end), str(path)) if window_end else None,
        )

    def _load_front_page(self, path: Path) -> dict[str, str]:
        rows = _read_rows(path)
        if not rows or tuple(rows[0]) != _FRONT_PAGE_HEADER:
            raise IntegrityError(
                f"{path}: expected header {_FRONT_PAGE_HEADER!r}, got "
                f"{rows[0] if rows else None!r}"
            )
        values: dict[str, str] = {}
        for row in rows[1:]:
            if len(row) != 3:
                raise IntegrityError(f"{path}: malformed row {row!r}")
            code, _label, value = (cell.strip() for cell in row)
            if not code:
                raise IntegrityError(f"{path}: row with empty excel_code: {row!r}")
            if code in values:
                raise IntegrityError(f"{path}: duplicate excel_code {code!r}")
            if value:
                values[code] = value
        return values

    def _load_grid(
        self, path: Path, period_type: str
    ) -> tuple[tuple[PeriodColumn, ...], dict[str, dict[str, float]], dict[str, str]]:
        rows = _read_rows(path)
        if not rows or tuple(rows[0][:3]) != _GRID_FIXED_HEADER:
            raise IntegrityError(
                f"{path}: expected header starting {_GRID_FIXED_HEADER!r}"
            )
        labels = [cell.strip() for cell in rows[0][3:]]
        if not labels:
            raise IntegrityError(f"{path}: grid declares no period columns")
        pattern = re.compile(rf"^{re.escape(period_type)}(-?\d+)$")
        offsets: list[int] = []
        for label in labels:
            match = pattern.match(label)
            if match is None:
                raise IntegrityError(
                    f"{path}: period label {label!r} does not match the "
                    f"{period_type}-relative grid (FS row 4 convention)"
                )
            offsets.append(int(match.group(1)))
        period_ends: dict[str, date] | None = None
        metrics: dict[str, dict[str, float]] = {}
        units: dict[str, str] = {}
        for row in rows[1:]:
            if len(row) != 3 + len(labels):
                raise IntegrityError(f"{path}: ragged grid row {row!r}")
            code = row[0].strip()
            if not code:
                raise IntegrityError(f"{path}: row with empty excel_code: {row!r}")
            cells = [cell.strip() for cell in row[3:]]
            if code == _PERIOD_END_CODE:
                period_ends = {
                    label: _parse_date(cell, f"{path} [{code}]")
                    for label, cell in zip(labels, cells, strict=True)
                }
                continue
            if code in metrics:
                raise IntegrityError(f"{path}: duplicate metric code {code!r}")
            metrics[code] = {
                label: _parse_float(cell, f"{path} [{code} {label}]")
                for label, cell in zip(labels, cells, strict=True)
                if cell
            }
            units[code] = row[2].strip() or "not_established"
        if period_ends is None:
            raise IntegrityError(
                f"{path}: missing {_PERIOD_END_CODE} row (FS row 5 period ends)"
            )
        columns = tuple(
            PeriodColumn(label=label, offset=offset, period_end=period_ends[label])
            for label, offset in zip(labels, offsets, strict=True)
        )
        ordered = sorted(columns, key=lambda c: c.offset)
        if [c.period_end for c in ordered] != sorted(c.period_end for c in ordered):
            raise IntegrityError(
                f"{path}: period ends are not increasing with the relative offset"
            )
        return columns, metrics, units

    def _load_multiples(self, path: Path) -> dict[str, tuple[tuple[date, float], ...]]:
        rows = _read_rows(path)
        if not rows:
            raise IntegrityError(f"{path}: empty trading_multiples.csv")
        header = [cell.strip() for cell in rows[0]]
        if len(header) % 2 != 0:
            raise IntegrityError(
                f"{path}: TM header must hold (date,value) column pairs"
            )
        codes: list[str] = []
        for i in range(0, len(header), 2):
            date_col, value_col = header[i], header[i + 1]
            if not (date_col.endswith("__date") and value_col.endswith("__value")):
                raise IntegrityError(
                    f"{path}: columns {date_col!r}/{value_col!r} are not a "
                    "<CODE>__date/<CODE>__value pair"
                )
            code = date_col[: -len("__date")]
            if code != value_col[: -len("__value")] or not code:
                raise IntegrityError(
                    f"{path}: pair code mismatch {date_col!r} vs {value_col!r}"
                )
            if code in codes:
                raise IntegrityError(f"{path}: duplicate TM pair code {code!r}")
            codes.append(code)
        series: dict[str, list[tuple[date, float]]] = {code: [] for code in codes}
        for row in rows[1:]:
            padded = list(row) + [""] * (len(header) - len(row))
            for pair_index, code in enumerate(codes):
                date_cell = padded[2 * pair_index].strip()
                value_cell = padded[2 * pair_index + 1].strip()
                if bool(date_cell) != bool(value_cell):
                    raise IntegrityError(
                        f"{path}: one-sided (date,value) cell for {code!r}: "
                        f"({date_cell!r}, {value_cell!r})"
                    )
                if date_cell:
                    series[code].append(
                        (
                            _parse_date(date_cell, f"{path} [{code}]"),
                            _parse_float(value_cell, f"{path} [{code}]"),
                        )
                    )
        for code, observations in series.items():
            dates = [d for d, _ in observations]
            if dates != sorted(dates) or len(set(dates)) != len(dates):
                raise IntegrityError(
                    f"{path}: {code!r} dates must be strictly ascending "
                    "(TM panel convention)"
                )
        return {code: tuple(observations) for code, observations in series.items()}


# ── the provider ─────────────────────────────────────────────────────────────


class LocalFileProvider:
    """AlphaSense-template-shaped local-file provider
    (# arch: provider_contract.md §4.2).

    ``root`` is caller-supplied (the runbook wires it from
    ``LASR_LOCAL_TEMPLATE_ROOT`` via ``config`` — this class never reads
    environment variables, system_design.md §4 rule table).
    """

    def __init__(
        self, root: Path, loader: CsvTemplateExtractLoader | None = None
    ) -> None:
        self._root = root
        self._loader = loader if loader is not None else CsvTemplateExtractLoader()
        extracts = [self._loader.load(d) for d in self._loader.discover(root)]
        if not extracts:
            raise IntegrityError(f"no template extracts found under {root}")
        self._extracts: dict[ProviderId, SecurityExtract] = {}
        for extract in extracts:
            pid = extract.provider_id
            if pid in self._extracts:
                raise IntegrityError(
                    f"duplicate template extract for {pid.value}/{pid.exchange}"
                )
            self._extracts[pid] = extract
        self._capabilities = self._build_capabilities()
        logger.debug("loaded %d template extracts from local drop", len(self._extracts))

    # -- capability record (fixed by G012/G013 evidence, §4.2 table) ---------

    def _build_capabilities(self) -> ProviderCapabilities:
        fundamental_codes = self._fundamental_codes()
        metric_codes = self._market_metric_codes()
        families: dict[FieldFamily, FamilyCapability] = {
            FieldFamily.SECURITY_MASTER: FamilyCapability(
                available=True,
                supports_pit=False,
                revision_support=RevisionSupport.NONE,
                fields=_SECURITY_MASTER_FIELDS,
                notes=(
                    "current snapshot only (FM-01/03/04 SNAPSHOT); no security "
                    "ids beyond ticker+exchange (FM-02, gap §1)"
                ),
            ),
            FieldFamily.MARKET_DAILY: FamilyCapability(
                available=True,
                supports_pit=False,
                revision_support=RevisionSupport.LATEST_ONLY,
                fields=frozenset(DEFAULT_PRICE_FIELDS) | metric_codes,
                notes=(
                    "TM panel RETRO_DAILY (FM-11/25); OHLV LISTED_ONLY "
                    "(FM-12/13/14, D-012 pending VP-01); adjustment basis "
                    "NOT_ESTABLISHED (FM-17); depth NOT_ESTABLISHED (gap §2)"
                ),
                history_start=None,  # depth NOT_ESTABLISHED (global caveat)
                corporate_action_basis=CorporateActionBasis.UNKNOWN,
            ),
            FieldFamily.FUNDAMENTALS: FamilyCapability(
                available=True,
                supports_pit=False,
                revision_support=RevisionSupport.LATEST_ONLY,
                fields=fundamental_codes,
                notes=(
                    "FY-5..FY+2 relative window per pull (E-G012-06); "
                    "latest_filing is the only version type "
                    "(Data!N2:O3, A-001); period ends only, no report dates "
                    "(FM-09/FM-10)"
                ),
            ),
            FieldFamily.ESTIMATES: FamilyCapability(
                available=True,
                supports_pit=False,
                revision_support=RevisionSupport.NONE,
                fields=fundamental_codes,
                notes=(
                    "current consensus snapshot only, FY+1/FY+2 grid columns "
                    "(FM-46); no revision history (gap §4); statistic type "
                    "NOT_ESTABLISHED"
                ),
            ),
            FieldFamily.CORPORATE_ACTIONS: FamilyCapability(
                available=False,
                supports_pit=False,
                revision_support=RevisionSupport.NONE,
                fields=frozenset(),
                notes="UNAVAILABLE: no action events in the surface (gap §5)",
            ),
            FieldFamily.CLASSIFICATIONS: FamilyCapability(
                available=True,
                supports_pit=False,
                revision_support=RevisionSupport.NONE,
                fields=frozenset(_CLASSIFICATION_SCHEME_CODES),
                notes=(
                    "current values only (FM-33/34/35 SNAPSHOT); no "
                    "effective-dated history (gap §6)"
                ),
            ),
            FieldFamily.UNIVERSE_MEMBERSHIP: FamilyCapability(
                available=False,
                supports_pit=False,
                revision_support=RevisionSupport.NONE,
                fields=frozenset(),
                notes="UNAVAILABLE: nothing index-related (gap §8, FM-27)",
            ),
            FieldFamily.BORROW: FamilyCapability(
                available=False,
                supports_pit=False,
                revision_support=RevisionSupport.NONE,
                fields=frozenset(),
                notes="UNAVAILABLE: nothing short-lending related (gap §7, FM-40)",
            ),
            FieldFamily.FX: FamilyCapability(
                available=False,
                supports_pit=False,
                revision_support=RevisionSupport.NONE,
                fields=frozenset(),
                notes="UNAVAILABLE: FX Rate is W1-list-only (FM-24, gap §6)",
            ),
            FieldFamily.CALENDAR: FamilyCapability(
                available=True,
                supports_pit=False,
                revision_support=RevisionSupport.NONE,
                fields=frozenset({DERIVED_CALENDAR_ID}),
                notes=(
                    "derived-with-note: union of observed TM panel dates "
                    "(FM-08); absence of a date is unknown, not a holiday"
                ),
            ),
        }
        return ProviderCapabilities(
            provider_name=PROVIDER_NAME,
            provider_version=PROVIDER_VERSION,
            families=families,
            supports_universe_screening=False,  # gap §1: single-ticker templates
            supports_publication_timestamps=False,  # gap §3 (FM-10)
            supports_delistings=False,  # gap §1
            supports_bid_ask=False,  # gap §2
            supports_borrow=False,  # gap §7
            supports_index_membership=False,  # gap §8
            supports_estimate_history=False,  # gap §4
            supports_vintages=False,  # Data!N2:O3 = latest_filing only (A-001)
        )

    def _fundamental_codes(self) -> frozenset[str]:
        return frozenset(
            code for extract in self._extracts.values() for code in extract.fundamentals
        )

    def _market_metric_codes(self) -> frozenset[str]:
        price_codes = set(_PRICE_FIELD_CODES.values())
        return frozenset(
            code
            for extract in self._extracts.values()
            for code in extract.multiples
            if code not in price_codes
        )

    # -- report methods -------------------------------------------------------

    def capabilities(self) -> ProviderCapabilities:
        return self._capabilities

    def field_coverage(self, family: FieldFamily) -> frozenset[str]:
        return self._capabilities.family(family).fields

    def available_history(self, family: FieldFamily) -> tuple[date | None, date | None]:
        """Observed (earliest, latest) served by *this drop*; (None, None)
        for snapshot families and unavailable families. Provider-level
        depth stays NOT_ESTABLISHED (``FamilyCapability.history_start``)."""
        if family in (FieldFamily.MARKET_DAILY, FieldFamily.CALENDAR):
            dates = [
                observation_date
                for extract in self._extracts.values()
                for series in extract.multiples.values()
                for observation_date, _ in series
            ]
            return (min(dates), max(dates)) if dates else (None, None)
        if family is FieldFamily.FUNDAMENTALS:
            ends = [
                column.period_end
                for extract in self._extracts.values()
                for column in extract.period_columns
                if column.offset <= 0
            ]
            return (min(ends), max(ends)) if ends else (None, None)
        if family is FieldFamily.ESTIMATES:
            ends = [
                column.period_end
                for extract in self._extracts.values()
                for column in extract.period_columns
                if column.offset > 0
            ]
            return (min(ends), max(ends)) if ends else (None, None)
        return (None, None)

    # -- shared guards ---------------------------------------------------------

    def _require_available(self, family: FieldFamily) -> None:
        capability = self._capabilities.family(family)
        if not capability.available:
            raise CapabilityError(
                f"family {family.value!r} is unavailable from provider "
                f"{PROVIDER_NAME!r}: {capability.notes}"
            )

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

    def _resolve(self, ids: Sequence[ProviderId]) -> list[SecurityExtract]:
        resolved: list[SecurityExtract] = []
        for pid in ids:
            extract = self._extracts.get(pid)
            if extract is None:
                known = ", ".join(
                    f"{p.value}/{p.exchange}"
                    for p in sorted(
                        self._extracts, key=lambda p: (p.value, p.exchange or "")
                    )
                )
                raise UnknownProviderIdError(
                    f"no template extract for {pid.value!r}/{pid.exchange!r}; "
                    f"known ids: {known}"
                )
            resolved.append(extract)
        return resolved

    # -- load methods ----------------------------------------------------------

    def fetch_security_master(
        self, ids: Sequence[ProviderId] | None = None
    ) -> DataFrame:
        self._require_available(FieldFamily.SECURITY_MASTER)
        extracts = (
            sorted(
                self._extracts.values(),
                key=lambda e: (e.metadata.ticker, e.metadata.exchange),
            )
            if ids is None
            else self._resolve(ids)
        )
        logger.debug("fetch_security_master: %d ids", len(extracts))
        rows: list[dict[str, object]] = [
            {
                "ticker": extract.metadata.ticker,
                "exchange": extract.metadata.exchange,
                "name": extract.front_page.get("NAME"),
                "country": extract.front_page.get("COUNTRY_EXCH"),
                "trading_currency": extract.front_page.get("TRADING_CURR"),
                "reporting_currency": extract.front_page.get("REPORTING_CURR"),
            }
            for extract in extracts
        ]
        columns = [
            c for c in RAW_SECURITY_MASTER.column_names if c in _SECURITY_MASTER_FIELDS
        ]
        return build_frame(RAW_SECURITY_MASTER, rows, columns=columns)

    def fetch_prices(
        self,
        ids: Sequence[ProviderId],
        start: date,
        end: date,
        fields: Sequence[str] = DEFAULT_PRICE_FIELDS,
    ) -> DataFrame:
        self._require_available(FieldFamily.MARKET_DAILY)
        requested = list(dict.fromkeys(fields))
        for field_name in requested:
            if field_name in LISTED_ONLY_PRICE_FIELDS:
                raise FieldUnavailableError(
                    f"price field {field_name!r} is LISTED_ONLY (FM-12/13/14): "
                    "no daily series is demonstrated; refused until probe "
                    "VP-01 passes (D-012)"
                )
            if field_name not in _PRICE_FIELD_CODES:
                raise FieldUnavailableError(
                    f"price field {field_name!r} is not servable; coverage: "
                    f"{sorted(_PRICE_FIELD_CODES)}"
                )
        self._check_window(FieldFamily.MARKET_DAILY, start, end)
        logger.debug(
            "fetch_prices: %d ids, %d fields, window [%s, %s]",
            len(ids),
            len(requested),
            start,
            end,
        )
        rows: list[dict[str, object]] = []
        for extract in self._resolve(ids):
            currency = extract.front_page["TRADING_CURR"]
            per_date: dict[date, dict[str, object]] = {}
            for field_name in requested:
                code = _PRICE_FIELD_CODES[field_name]
                for observation_date, value in extract.multiples.get(code, ()):
                    if start <= observation_date <= end:
                        per_date.setdefault(observation_date, {})[field_name] = value
            for observation_date in sorted(per_date):
                rows.append(
                    {
                        "ticker": extract.metadata.ticker,
                        "exchange": extract.metadata.exchange,
                        "event_date": observation_date,
                        **per_date[observation_date],
                        "currency": currency,
                    }
                )
        columns = ["ticker", "exchange", "event_date", *requested, "currency"]
        ordered = [c for c in RAW_MARKET_DAILY.column_names if c in set(columns)]
        return build_frame(RAW_MARKET_DAILY, rows, columns=ordered)

    def fetch_market_metrics(
        self, ids: Sequence[ProviderId], metrics: Sequence[str], start: date, end: date
    ) -> DataFrame:
        self._require_available(FieldFamily.MARKET_DAILY)
        catalog = self._market_metric_codes()
        unknown = sorted(set(metrics) - catalog)
        if unknown:
            raise FieldUnavailableError(
                f"market metrics {unknown!r} are not in this drop's TM panel; "
                f"coverage: {sorted(catalog)}"
            )
        self._check_window(FieldFamily.MARKET_DAILY, start, end)
        logger.debug(
            "fetch_market_metrics: %d ids, %d metrics, window [%s, %s]",
            len(ids),
            len(metrics),
            start,
            end,
        )
        rows: list[dict[str, object]] = []
        for extract in self._resolve(ids):
            for metric in dict.fromkeys(metrics):
                for observation_date, value in extract.multiples.get(metric, ()):
                    if start <= observation_date <= end:
                        rows.append(
                            {
                                "ticker": extract.metadata.ticker,
                                "exchange": extract.metadata.exchange,
                                "metric": metric,
                                "event_date": observation_date,
                                "value": value,
                            }
                        )
        columns = ["ticker", "exchange", "metric", "event_date", "value"]
        return build_frame(RAW_MARKET_METRICS, rows, columns=columns)

    def fetch_fundamentals(
        self,
        ids: Sequence[ProviderId],
        metrics: Sequence[str],
        start: date,
        end: date,
        vintage: Literal["latest", "as_reported", "all"] = "latest",
    ) -> DataFrame:
        self._require_available(FieldFamily.FUNDAMENTALS)
        if vintage != "latest":
            raise CapabilityError(
                f"vintage={vintage!r} requires supports_vintages, which this "
                "provider declares false: the template's only version type is "
                "latest_filing (Data!N2:O3, A-001)"
            )
        catalog = self._fundamental_codes()
        unknown = sorted(set(metrics) - catalog)
        if unknown:
            raise FieldUnavailableError(
                f"fundamental metrics {unknown!r} are not in this drop's grid; "
                f"coverage: {sorted(catalog)}"
            )
        self._check_window(FieldFamily.FUNDAMENTALS, start, end)
        logger.debug(
            "fetch_fundamentals: %d ids, %d metrics, window [%s, %s]",
            len(ids),
            len(metrics),
            start,
            end,
        )
        rows: list[dict[str, object]] = []
        for extract in self._resolve(ids):
            for metric in dict.fromkeys(metrics):
                values = extract.fundamentals.get(metric, {})
                unit = extract.fundamental_units.get(metric, "not_established")
                for column in extract.period_columns:
                    if column.offset > 0:  # FY+1/FY+2 are consensus -> estimates
                        continue
                    if column.label not in values:
                        continue
                    if not start <= column.period_end <= end:
                        continue
                    rows.append(
                        {
                            "ticker": extract.metadata.ticker,
                            "exchange": extract.metadata.exchange,
                            "metric": metric,
                            "fiscal_period": column.label,
                            "period_end": column.period_end,
                            "value": values[column.label],
                            "unit": unit,
                            "currency": extract.metadata.selected_currency,
                            "version_type": extract.metadata.version_type,
                        }
                    )
        columns = [
            "ticker",
            "exchange",
            "metric",
            "fiscal_period",
            "period_end",
            "value",
            "unit",
            "currency",
            "version_type",
        ]
        return build_frame(RAW_FUNDAMENTALS, rows, columns=columns)

    def fetch_estimates(
        self, ids: Sequence[ProviderId], metrics: Sequence[str], start: date, end: date
    ) -> DataFrame:
        self._require_available(FieldFamily.ESTIMATES)
        catalog = self._fundamental_codes()
        unknown = sorted(set(metrics) - catalog)
        if unknown:
            raise FieldUnavailableError(
                f"estimate metrics {unknown!r} are not in this drop's grid; "
                f"coverage: {sorted(catalog)}"
            )
        self._check_window(FieldFamily.ESTIMATES, start, end)
        logger.debug(
            "fetch_estimates: %d ids, %d metrics, window [%s, %s]",
            len(ids),
            len(metrics),
            start,
            end,
        )
        rows: list[dict[str, object]] = []
        for extract in self._resolve(ids):
            for metric in dict.fromkeys(metrics):
                values = extract.fundamentals.get(metric, {})
                for column in extract.period_columns:
                    if column.offset <= 0:
                        continue
                    if column.label not in values:
                        continue
                    if not start <= column.period_end <= end:
                        continue
                    rows.append(
                        {
                            "ticker": extract.metadata.ticker,
                            "exchange": extract.metadata.exchange,
                            "metric": metric,
                            "forecast_period": column.label,
                            "value": values[column.label],
                            "period_end": column.period_end,
                            # stat stays absent: mean-vs-median is
                            # NOT_ESTABLISHED (gap §4) — never fabricated.
                            "currency": extract.metadata.selected_currency,
                        }
                    )
        columns = [
            "ticker",
            "exchange",
            "metric",
            "forecast_period",
            "value",
            "period_end",
            "currency",
        ]
        return build_frame(RAW_ESTIMATES, rows, columns=columns)

    def fetch_classifications(
        self, ids: Sequence[ProviderId], schemes: Sequence[str]
    ) -> DataFrame:
        self._require_available(FieldFamily.CLASSIFICATIONS)
        unknown = sorted(set(schemes) - set(_CLASSIFICATION_SCHEME_CODES))
        if unknown:
            raise FieldUnavailableError(
                f"classification schemes {unknown!r} are not servable; "
                f"coverage: {sorted(_CLASSIFICATION_SCHEME_CODES)}"
            )
        logger.debug(
            "fetch_classifications: %d ids, %d schemes", len(ids), len(schemes)
        )
        rows: list[dict[str, object]] = []
        for extract in self._resolve(ids):
            for scheme in dict.fromkeys(schemes):
                value = extract.front_page.get(_CLASSIFICATION_SCHEME_CODES[scheme])
                if value is None:  # empty FP cell: valid-but-empty (CT-12)
                    continue
                rows.append(
                    {
                        "ticker": extract.metadata.ticker,
                        "exchange": extract.metadata.exchange,
                        "scheme": scheme,
                        "value": value,
                    }
                )
        columns = ["ticker", "exchange", "scheme", "value"]
        return build_frame(RAW_CLASSIFICATIONS, rows, columns=columns)

    def fetch_trading_calendar(
        self, calendar_id: str, start: date, end: date
    ) -> DataFrame:
        self._require_available(FieldFamily.CALENDAR)
        if calendar_id != DERIVED_CALENDAR_ID:
            raise FieldUnavailableError(
                f"calendar {calendar_id!r} is not servable; the only derived "
                f"calendar is {DERIVED_CALENDAR_ID!r} (FM-08 derived-with-note)"
            )
        self._check_window(FieldFamily.CALENDAR, start, end)
        observed = sorted(
            {
                observation_date
                for extract in self._extracts.values()
                for series in extract.multiples.values()
                for observation_date, _ in series
                if start <= observation_date <= end
            }
        )
        logger.debug(
            "fetch_trading_calendar: %d observed days in [%s, %s]",
            len(observed),
            start,
            end,
        )
        rows: list[dict[str, object]] = [
            {
                "calendar_id": DERIVED_CALENDAR_ID,
                "event_date": observation_date,
                "is_trading_day": True,
            }
            for observation_date in observed
        ]
        return build_frame(RAW_TRADING_CALENDARS, rows)

    # -- unavailable families: typed refusals (never silent) ------------------

    def fetch_corporate_actions(
        self, ids: Sequence[ProviderId], start: date, end: date
    ) -> DataFrame:
        self._require_available(FieldFamily.CORPORATE_ACTIONS)
        raise AssertionError("unreachable")  # pragma: no cover

    def fetch_borrow(
        self, ids: Sequence[ProviderId], start: date, end: date
    ) -> DataFrame:
        self._require_available(FieldFamily.BORROW)
        raise AssertionError("unreachable")  # pragma: no cover

    def fetch_universe_membership(
        self, universe_id: str, start: date, end: date
    ) -> DataFrame:
        self._require_available(FieldFamily.UNIVERSE_MEMBERSHIP)
        raise AssertionError("unreachable")  # pragma: no cover

    def fetch_fx_rates(
        self, pairs: Sequence[tuple[str, str]], start: date, end: date
    ) -> DataFrame:
        self._require_available(FieldFamily.FX)
        raise AssertionError("unreachable")  # pragma: no cover
