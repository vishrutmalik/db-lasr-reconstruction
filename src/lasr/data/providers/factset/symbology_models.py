"""Symbology v3 request/response models (FS010 — first concrete family).

# arch: docs/factset/capability/symbology.{md,json} (FS003, complete
manifest) — the only family whose models FS010 may implement; all other
family models are gated on FS009 reconciliation.

Facts encoded from the manifest:

- POST preferred over GET for id lists (8 KB URL cap on GET; FS003
  fs010_guidance);
- ids ceiling = 100, the SAFE ceiling from discrepancy D-1 (prose max 100
  vs schema max 3000): documented bounds conflict → take the MINIMUM until
  a live measurement resolves U-3 (FS002 §6.2 rule);
- output symbol types: 1..20 per request (schema bound);
- current-resolution POST body is FLAT; historical POST body is
  WRAPPED-IN-DATA (D-9: separate request builders, never one shape);
- ``inputSymbolType`` has a server default (``tickerRegion``) AND is
  required (D-4): the builders MATERIALIZE it explicitly so one logical
  request can never hash two ways;
- historical output types are limited to SEDOL/CUSIP/ISIN/tickerRegion;
  fsym ids are historical INPUTS only (pit_asymmetry);
- response dynamic keys may be lowercased vs the enum casing (D-6/U-5):
  parsing matches output-type keys case-insensitively;
- spec example payloads are internally inconsistent (D-7): fixtures are
  hand-synthesized, never copied from the spec.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from lasr.data.providers.factset.errors import (
    FactSetConfigError,
    FactSetIntegrityError,
)
from lasr.data.providers.factset.request_norm import (
    NormalizedRequest,
    normalize_id_list,
)

__all__ = [
    "API_FAMILY",
    "API_VERSION",
    "HISTORICAL_INPUT_SYMBOL_TYPES",
    "HISTORICAL_OUTPUT_SYMBOL_TYPES",
    "INPUT_SYMBOL_TYPES",
    "MAX_IDS_PER_REQUEST",
    "MAX_OUTPUT_TYPES",
    "OUTPUT_SYMBOL_TYPES",
    "PATH_PREFIX",
    "HistoricalResolutionRow",
    "ResolutionRow",
    "build_historical_resolution_request",
    "build_identifier_resolution_request",
    "parse_historical_resolution_response",
    "parse_identifier_resolution_response",
]

API_FAMILY = "symbology"
API_VERSION = "v3"
PATH_PREFIX = "/symbology/v3"

#: FS003 D-1 safe ceiling (prose 100 vs schema 3000 → minimum until U-3).
MAX_IDS_PER_REQUEST = 100
#: Body-schema bound 1..20 output symbol types per request.
MAX_OUTPUT_TYPES = 20

#: input_symbol_types_current (FS003 enum, 31 values).
INPUT_SYMBOL_TYPES = frozenset(
    {
        "BIC",
        "CIK",
        "CRD",
        "EIN",
        "FITCH",
        "LEI",
        "MD",
        "SPR",
        "VALOREN",
        "WKN",
        "UKCH",
        "RSSD",
        "SEDOL",
        "CUSIP",
        "fsymEntityId",
        "fsymSecurityId",
        "fsymRegionalId",
        "fsymListingId",
        "ISIN",
        "tickerExchange",
        "tickerRegion",
        "bloombergFigi",
        "bloombergTicker",
        "GVKEY",
        "GVKEY & IID",
        "JCN",
        "LoanX",
        "MarkitRed",
        "VAT",
        "crunchBaseId",
        "creditSafeId",
    }
)

#: input_symbol_types_historical (FS003 enum, 28 values — current minus
#: VAT/crunchBaseId/creditSafeId).
HISTORICAL_INPUT_SYMBOL_TYPES = frozenset(
    INPUT_SYMBOL_TYPES - {"VAT", "crunchBaseId", "creditSafeId"}
)

#: output_symbol_types_current (FS003 enum, 30 values).
OUTPUT_SYMBOL_TYPES = frozenset(
    {
        "BIC",
        "CIK",
        "CRD",
        "EIN",
        "FITCH",
        "LEI",
        "MD",
        "SPR",
        "WKN",
        "UKCH",
        "RSSD",
        "SEDOL",
        "CUSIP",
        "fsymEntityId",
        "fsymSecurityId",
        "fsymRegionalId",
        "fsymListingId",
        "ISIN",
        "tickerExchange",
        "tickerRegion",
        "JCN",
        "bloombergListingTicker",
        "bloombergRegionalTicker",
        "bloombergSecurityTicker",
        "bloombergFigiListing",
        "bloombergFigiRegional",
        "bloombergFigiSecurity",
        "VAT",
        "crunchBaseId",
        "creditSafeId",
    }
)

#: output_symbol_types_historical (FS003 enum, exactly 4 values).
HISTORICAL_OUTPUT_SYMBOL_TYPES = frozenset({"SEDOL", "CUSIP", "ISIN", "tickerRegion"})

_RESOLUTION_ENDPOINT = "/identifier-resolution"
_HISTORICAL_ENDPOINT = "/historical-identifier-resolution"

#: Fixed data-row fields (everything else is a dynamic output-type key).
_FIXED_ROW_FIELDS = frozenset(
    {"requestId", "inputSymbolType", "name", "frefListingExchange", "currency"}
)


def _validate_symbol_types(
    values: Sequence[str], allowed: frozenset[str], *, label: str
) -> tuple[str, ...]:
    if not values:
        raise FactSetConfigError(f"{label} must name at least one symbol type")
    if len(values) > MAX_OUTPUT_TYPES:
        raise FactSetConfigError(
            f"{label} allows at most {MAX_OUTPUT_TYPES} symbol types per"
            f" request, got {len(values)}"
        )
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise FactSetConfigError(
            f"{label} contains undocumented symbol types {unknown}"
            " (FS003 enum is the wire contract, D-5)"
        )
    deduped = sorted(set(values))
    return tuple(deduped)


def _validate_ids(ids: Sequence[str]) -> tuple[str, ...]:
    normalized = normalize_id_list(ids)
    if len(normalized) > MAX_IDS_PER_REQUEST:
        raise FactSetConfigError(
            f"at most {MAX_IDS_PER_REQUEST} ids per symbology request"
            f" (FS003 D-1 safe ceiling), got {len(normalized)};"
            " chunk upstream with chunk_ids"
        )
    return normalized


def build_identifier_resolution_request(
    *,
    ids: Sequence[str],
    output_symbol_types: Sequence[str],
    input_symbol_type: str = "tickerRegion",
) -> NormalizedRequest:
    """Current-state resolution (POST, FLAT body — D-9).

    The server default ``inputSymbolType=tickerRegion`` is materialized
    explicitly (D-4 + FS002 §3.2 default-materialization rule).
    """
    if input_symbol_type not in INPUT_SYMBOL_TYPES:
        raise FactSetConfigError(
            f"inputSymbolType {input_symbol_type!r} is not in the documented"
            " current-resolution enum (FS003)"
        )
    return NormalizedRequest(
        api_family=API_FAMILY,
        api_version=API_VERSION,
        endpoint=_RESOLUTION_ENDPOINT,
        verb="POST",
        params={
            "ids": list(_validate_ids(ids)),
            "inputSymbolType": input_symbol_type,
            "outputSymbolTypes": list(
                _validate_symbol_types(
                    output_symbol_types,
                    OUTPUT_SYMBOL_TYPES,
                    label="outputSymbolTypes",
                )
            ),
        },
    )


def build_historical_resolution_request(
    *,
    ids: Sequence[str],
    input_symbol_type: str,
    output_symbol_types: Sequence[str],
    as_of_date: date | None = None,
) -> NormalizedRequest:
    """Historical resolution (POST, WRAPPED-IN-DATA body — D-9).

    ``as_of_date=None`` means full history (documented omitted-behavior);
    presence/absence of the key IS the logical request distinction, so the
    key is omitted rather than sent null. ``inputSymbolType`` has no
    server default here and is always explicit.
    """
    if input_symbol_type not in HISTORICAL_INPUT_SYMBOL_TYPES:
        raise FactSetConfigError(
            f"inputSymbolType {input_symbol_type!r} is not in the documented"
            " historical enum (FS003)"
        )
    body: dict[str, object] = {
        "ids": list(_validate_ids(ids)),
        "inputSymbolType": input_symbol_type,
        "outputSymbolTypes": list(
            _validate_symbol_types(
                output_symbol_types,
                HISTORICAL_OUTPUT_SYMBOL_TYPES,
                label="historical outputSymbolTypes",
            )
        ),
    }
    if as_of_date is not None:
        body["asOfDate"] = as_of_date.isoformat()
    return NormalizedRequest(
        api_family=API_FAMILY,
        api_version=API_VERSION,
        endpoint=_HISTORICAL_ENDPOINT,
        verb="POST",
        params={"data": body},
    )


@dataclass(frozen=True)
class ResolutionRow:
    """One current-resolution data row (FS003 ``identifierResolution``).

    ``outputs`` maps the REQUESTED output-type spelling to the resolved
    value; dynamic response keys are matched case-insensitively (D-6/U-5).
    """

    request_id: str
    input_symbol_type: str
    name: str | None
    fref_listing_exchange: str | None
    currency: str | None
    outputs: Mapping[str, str | None]


@dataclass(frozen=True)
class HistoricalResolutionRow:
    """One historical row: requestId x outputType x validity interval.

    Open-interval ``endDate`` representation is UNRESOLVED (U-7c): the
    raw value is preserved verbatim; NO closure convention is guessed.
    """

    request_id: str
    input_symbol_type: str
    output_type: str | None
    value: str | None
    start_date: str | None
    end_date: str | None
    name: str | None
    fref_listing_exchange: str | None
    currency: str | None


def _load_data_rows(body: bytes, *, endpoint: str) -> list[dict[str, object]]:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FactSetIntegrityError(
            f"malformed JSON body from {endpoint}: {exc}"
        ) from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise FactSetIntegrityError(
            f"response from {endpoint} lacks the documented"
            " {{'data': [...]}} envelope"
        )
    rows: list[dict[str, object]] = []
    for i, row in enumerate(payload["data"]):
        if not isinstance(row, dict):
            raise FactSetIntegrityError(
                f"data row {i} from {endpoint} is not an object"
            )
        rows.append(row)
    return rows


def _opt_str(row: Mapping[str, object], key: str) -> str | None:
    value = row.get(key)
    return value if isinstance(value, str) else None


def parse_identifier_resolution_response(
    body: bytes, *, requested_output_types: Sequence[str]
) -> tuple[ResolutionRow, ...]:
    """Parse the current-resolution response.

    A missing ``requestId`` is an integrity violation (the manifest marks
    it non-nullable — it is the join key). No-match representation is
    UNRESOLVED (U-8): absent output keys stay ``None``; rows are never
    dropped or fabricated here.
    """
    rows: list[ResolutionRow] = []
    for i, row in enumerate(_load_data_rows(body, endpoint=_RESOLUTION_ENDPOINT)):
        request_id = _opt_str(row, "requestId")
        if request_id is None:
            raise FactSetIntegrityError(
                f"data row {i} lacks the non-nullable requestId join key"
            )
        lowered = {k.lower(): v for k, v in row.items() if k not in _FIXED_ROW_FIELDS}
        outputs: dict[str, str | None] = {}
        for requested in requested_output_types:
            value = lowered.get(requested.lower())
            outputs[requested] = value if isinstance(value, str) else None
        rows.append(
            ResolutionRow(
                request_id=request_id,
                input_symbol_type=_opt_str(row, "inputSymbolType") or "",
                name=_opt_str(row, "name"),
                fref_listing_exchange=_opt_str(row, "frefListingExchange"),
                currency=_opt_str(row, "currency"),
                outputs=outputs,
            )
        )
    return tuple(rows)


def parse_historical_resolution_response(
    body: bytes,
) -> tuple[HistoricalResolutionRow, ...]:
    """Parse the historical response (long format supports multiplicity)."""
    rows: list[HistoricalResolutionRow] = []
    for i, row in enumerate(_load_data_rows(body, endpoint=_HISTORICAL_ENDPOINT)):
        request_id = _opt_str(row, "requestId")
        if request_id is None:
            raise FactSetIntegrityError(
                f"historical data row {i} lacks the non-nullable requestId"
            )
        rows.append(
            HistoricalResolutionRow(
                request_id=request_id,
                input_symbol_type=_opt_str(row, "inputSymbolType") or "",
                output_type=_opt_str(row, "outputType"),
                value=_opt_str(row, "value"),
                start_date=_opt_str(row, "startDate"),
                end_date=_opt_str(row, "endDate"),
                name=_opt_str(row, "name"),
                fref_listing_exchange=_opt_str(row, "frefListingExchange"),
                currency=_opt_str(row, "currency"),
            )
        )
    return tuple(rows)
