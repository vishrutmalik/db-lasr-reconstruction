"""Symbology adapter — the single FactSet identity authority (FS011).

# arch: docs/architecture/factset_integration.md §5.4 — this module is the
ONLY one that (a) calls Symbology endpoints, (b) mints ``security_id``s
for FactSet data, (c) maintains the ProviderId → fsym resolution used by
every other family adapter (FS012-16 accept typed ids and delegate here).

Disciplines wired in:

- **FS010 transport only:** every wire interaction goes through
  :class:`FactSetTransport.execute` (cache-first, budgets, kill switch,
  sanitized telemetry). This module never constructs a network client.
- **normalize_id_list on every request path (VF-FS010-9):** values are
  normalized+deduplicated and deterministically chunked BEFORE request
  building, so a caller's ordering/duplication can never mint a second
  cache identity or spend a second quota unit.
- **Typed resolution only (D-020(b)):** inputs are
  :class:`~lasr.data.providers.factset.identity.TypedIdentifier`; one
  request per declared scheme — identifier schemes are never guessed.
- **Casing policy (RT-FS010-2):** TypedIdentifier construction has
  already uppercased values; ``requestId`` echoes therefore join back on
  the canonical spelling.
- **Mapped-or-explained (WP2/EA §9):** every resolve call returns an
  :class:`~lasr.data.providers.factset.identity.IdAccounting` covering
  every requested id; chunk-level vendor failures become per-id
  categories instead of silent loss.
- **No silent multi-match (D-017 spirit):** duplicate vendor rows for one
  requestId raise :class:`AmbiguousResolutionError` listing candidates.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date

from lasr.data.providers.base import ProviderError
from lasr.data.providers.factset.errors import (
    FactSetClientError,
    FactSetEntitlementError,
    FactSetRateLimitError,
    FactSetRequestTooLargeError,
    FactSetRetryExhaustedError,
    FactSetServerError,
    FactSetTransportError,
)
from lasr.data.providers.factset.identity import (
    AccountingCategory,
    BridgeOutcome,
    FactSetIdentityError,
    IdAccounting,
    IdentifierInterval,
    IdentifierScheme,
    IdentityMap,
    SecuritySeed,
    TypedIdentifier,
    evaluate_bridge,
)
from lasr.data.providers.factset.request_norm import chunk_ids, normalize_id_list
from lasr.data.providers.factset.symbology_models import (
    HISTORICAL_OUTPUT_SYMBOL_TYPES,
    MAX_IDS_PER_REQUEST,
    HistoricalResolutionRow,
    ResolutionRow,
    build_historical_resolution_request,
    build_identifier_resolution_request,
    parse_historical_resolution_response,
    parse_identifier_resolution_response,
)
from lasr.data.providers.factset.transport import FactSetTransport

__all__ = [
    "FSYM_OUTPUT_TYPES",
    "AmbiguousResolutionError",
    "CurrentResolution",
    "HistoricalResolution",
    "IdentityMapBuild",
    "SymbologyAdapter",
    "account_key",
]

logger = logging.getLogger(__name__)

#: The four fsym permanent-id levels requested when seeding (§5.2: all
#: four ARE outputs of CURRENT resolution — FS003 output_symbol_types).
FSYM_OUTPUT_TYPES: tuple[str, ...] = (
    "fsymEntityId",
    "fsymSecurityId",
    "fsymRegionalId",
    "fsymListingId",
)

#: Historical outputType → CE-2 ``identifier_map.id_scheme`` value.
_HISTORICAL_SCHEME: Mapping[str, str] = {
    "tickerregion": "ticker",
    "cusip": "cusip",
    "isin": "isin",
    "sedol": "sedol",
}

_OUTPUT_IDENTIFIER_SCHEME: Mapping[str, IdentifierScheme] = {
    scheme.value.lower(): scheme for scheme in IdentifierScheme
}


class AmbiguousResolutionError(ProviderError):
    """One requestId came back with conflicting rows: a one-to-many
    resolution is surfaced as a typed refusal LISTING the candidates —
    never a silent pick (D-017 spirit; FS003 U-6/U-25)."""


def account_key(identifier: TypedIdentifier) -> str:
    """Accounting key: ``scheme:value`` (two schemes may share a value
    string; the pair is the requested identity)."""
    return f"{identifier.scheme.value}:{identifier.value}"


@dataclass(frozen=True)
class CurrentResolution:
    """Result of one typed current-resolution pass."""

    rows: tuple[ResolutionRow, ...]
    accounting: IdAccounting
    requests_executed: int

    def outputs_for(self, identifier: TypedIdentifier) -> Mapping[str, str | None]:
        for row in self.rows:
            if (
                row.request_id == identifier.value
                and row.input_symbol_type == identifier.scheme.value
            ):
                return row.outputs
        raise FactSetIdentityError(
            f"no resolution row for {account_key(identifier)} (its accounting"
            f" category is {self.accounting.category_of(account_key(identifier))})"
        )


@dataclass(frozen=True)
class HistoricalResolution:
    """Result of one typed historical-resolution pass (dated intervals)."""

    rows: tuple[HistoricalResolutionRow, ...]
    accounting: IdAccounting
    requests_executed: int

    def intervals_for(
        self, identifier: TypedIdentifier
    ) -> tuple[HistoricalResolutionRow, ...]:
        return tuple(
            r
            for r in self.rows
            if r.request_id == identifier.value
            and r.input_symbol_type == identifier.scheme.value
        )


@dataclass(frozen=True)
class IdentityMapBuild:
    """Identity map + the accounting of both passes that built it."""

    identity_map: IdentityMap
    seed_accounting: IdAccounting
    hydrate_accounting: IdAccounting
    requests_executed: int


class SymbologyAdapter:
    """Typed resolution + identity-map construction over the FS010
    transport (see module docstring for the discipline list)."""

    def __init__(self, transport: FactSetTransport) -> None:
        self._transport = transport

    # ── typed current resolution ────────────────────────────────────────

    def resolve_current(
        self,
        identifiers: Sequence[TypedIdentifier],
        *,
        output_symbol_types: Sequence[str],
        force_refresh: bool = False,
    ) -> CurrentResolution:
        """Resolve typed identifiers via ``/identifier-resolution``.

        One request per DECLARED scheme (never mixed, never guessed),
        normalized+chunked deterministically. Chunk-level transport
        failures become per-id accounting categories (mapped-or-explained)
        except auth failures, which abort the run (they are never a per-id
        property).
        """
        groups = _group_by_scheme(identifiers)
        accounting = IdAccounting(
            requested=tuple(account_key(i) for i in _dedupe(identifiers))
        )
        rows: list[ResolutionRow] = []
        requests = 0
        for scheme, values in groups.items():
            for chunk in chunk_ids(values, MAX_IDS_PER_REQUEST):
                request = build_identifier_resolution_request(
                    ids=list(chunk),
                    input_symbol_type=scheme.value,
                    output_symbol_types=list(output_symbol_types),
                )
                requests += 1
                try:
                    response = self._transport.execute(
                        request, force_refresh=force_refresh
                    )
                except FactSetTransportError as exc:
                    _account_chunk_failure(accounting, scheme, chunk, exc)
                    continue
                parsed = parse_identifier_resolution_response(
                    response.body, requested_output_types=list(output_symbol_types)
                )
                parsed = _validate_current_rows(scheme, chunk, parsed)
                parsed = _refuse_ambiguous_current(parsed)
                rows.extend(parsed)
                returned = {r.request_id for r in parsed}
                for value in chunk:
                    key = f"{scheme.value}:{value}"
                    if value not in returned:
                        accounting.assign(
                            key,
                            AccountingCategory.NOT_COVERED,
                            "no row echoed for requestId (no-match shape is"
                            " U-8 UNRESOLVED; absence recorded verbatim)",
                        )
                        continue
                    row = next(r for r in parsed if r.request_id == value)
                    if any(v is not None for v in row.outputs.values()):
                        accounting.assign(
                            key,
                            AccountingCategory.SUCCESSFULLY_RETRIEVED,
                            "resolved with at least one requested output",
                        )
                    else:
                        accounting.assign(
                            key,
                            AccountingCategory.NOT_COVERED,
                            "row echoed but every requested output is null"
                            " (U-8 no-match shape preserved)",
                        )
        accounting.verify_complete()
        return CurrentResolution(
            rows=tuple(rows), accounting=accounting, requests_executed=requests
        )

    # ── typed historical resolution ─────────────────────────────────────

    def resolve_historical(
        self,
        identifiers: Sequence[TypedIdentifier],
        *,
        output_symbol_types: Sequence[str] = tuple(
            sorted(HISTORICAL_OUTPUT_SYMBOL_TYPES)
        ),
        as_of_date: date | None = None,
        force_refresh: bool = False,
    ) -> HistoricalResolution:
        """Resolve dated identifier intervals via
        ``/historical-identifier-resolution``.

        Outputs are structurally limited to SEDOL/CUSIP/ISIN/tickerRegion
        (F-004 — fsym ids are historical INPUTS only); ``as_of_date=None``
        requests full history. Interval dates are vendor strings preserved
        verbatim downstream (U-7c).
        """
        groups = _group_by_scheme(identifiers)
        accounting = IdAccounting(
            requested=tuple(account_key(i) for i in _dedupe(identifiers))
        )
        rows: list[HistoricalResolutionRow] = []
        requests = 0
        for scheme, values in groups.items():
            for chunk in chunk_ids(values, MAX_IDS_PER_REQUEST):
                request = build_historical_resolution_request(
                    ids=list(chunk),
                    input_symbol_type=scheme.value,
                    output_symbol_types=list(output_symbol_types),
                    as_of_date=as_of_date,
                )
                requests += 1
                try:
                    response = self._transport.execute(
                        request, force_refresh=force_refresh
                    )
                except FactSetTransportError as exc:
                    _account_chunk_failure(accounting, scheme, chunk, exc)
                    continue
                parsed = parse_historical_resolution_response(response.body)
                parsed = _validate_historical_rows(
                    scheme, chunk, output_symbol_types, parsed
                )
                rows.extend(parsed)
                by_id: dict[str, list[HistoricalResolutionRow]] = {}
                for row in parsed:
                    by_id.setdefault(row.request_id, []).append(row)
                for value in chunk:
                    key = f"{scheme.value}:{value}"
                    matched = by_id.get(value, [])
                    dated = [
                        m
                        for m in matched
                        if m.output_type is not None and m.value is not None
                    ]
                    if dated:
                        accounting.assign(
                            key,
                            AccountingCategory.SUCCESSFULLY_RETRIEVED,
                            f"{len(dated)} dated identifier interval(s)",
                        )
                    elif matched:
                        accounting.assign(
                            key,
                            AccountingCategory.VALIDLY_EMPTY,
                            "id echoed with no interval values (explicit"
                            " empty history)",
                        )
                    else:
                        accounting.assign(
                            key,
                            AccountingCategory.NOT_COVERED,
                            "no historical rows echoed (no-match shape is"
                            " U-8 UNRESOLVED; absence recorded verbatim)",
                        )
        accounting.verify_complete()
        return HistoricalResolution(
            rows=tuple(rows), accounting=accounting, requests_executed=requests
        )

    # ── identity map: seed + hydrate (§5.2) ─────────────────────────────

    def seed_securities(
        self,
        identifiers: Sequence[TypedIdentifier],
        *,
        output_symbol_types: Sequence[str] = FSYM_OUTPUT_TYPES,
        force_refresh: bool = False,
    ) -> tuple[tuple[SecuritySeed, ...], CurrentResolution]:
        """CURRENT resolution → fsym-level seeds (§5.2 seeding leg).

        A row missing ``fsymSecurityId`` cannot seed the spine; it stays
        explained in the accounting (its category is already NOT_COVERED
        or the row-level outputs simply lack the security level — the
        latter is re-accounted here as evidence in the returned rows).
        ``force_refresh`` re-attempts past cached entitlement evidence
        AFTER entitlements are fixed (D-020(d) error-cache policy).
        """
        resolution = self.resolve_current(
            identifiers,
            output_symbol_types=output_symbol_types,
            force_refresh=force_refresh,
        )
        seeds: list[SecuritySeed] = []
        seed_by_key: dict[str, SecuritySeed] = {}
        for row in resolution.rows:
            outputs = _fold_outputs(row.outputs)
            fsym_security = outputs.get("fsymsecurityid")
            if fsym_security is None:
                logger.info(
                    "row for requestId=%s carries no fsymSecurityId; cannot"
                    " seed the identity spine from it",
                    row.request_id,
                )
                continue
            seed = SecuritySeed(
                fsym_security_id=fsym_security,
                fsym_entity_id=outputs.get("fsymentityid"),
                fsym_regional_id=outputs.get("fsymregionalid"),
                fsym_listing_id=outputs.get("fsymlistingid"),
                name=row.name,
                fref_listing_exchange=row.fref_listing_exchange,
                currency=row.currency,
            )
            seeds.append(seed)
            seed_by_key[f"{row.input_symbol_type}:{row.request_id}"] = seed

        # The generic current resolver accounts any requested non-null output
        # as retrieved. Seeding has a stricter usable outcome: fsymSecurityId
        # must exist and validate. Re-account this operation so a row carrying
        # only entity/regional/listing data cannot silently disappear while
        # the mapped-or-explained ledger claims success (VF-FS011-1).
        seed_accounting = IdAccounting(requested=resolution.accounting.requested)
        for key in seed_accounting.requested:
            prior = resolution.accounting.category_of(key)
            if prior is not AccountingCategory.SUCCESSFULLY_RETRIEVED:
                seed_accounting.assign(key, prior, resolution.accounting.reason_of(key))
            elif key in seed_by_key:
                seed_accounting.assign(
                    key,
                    AccountingCategory.SUCCESSFULLY_RETRIEVED,
                    "identity spine seeded from a validated fsymSecurityId",
                )
            else:
                seed_accounting.assign(
                    key,
                    AccountingCategory.NOT_COVERED,
                    "response carried no usable fsymSecurityId; identity spine"
                    " was not seeded (mapped-or-explained, VF-FS011-1)",
                )
        seed_accounting.verify_complete()
        return (
            tuple(seeds),
            replace(resolution, accounting=seed_accounting),
        )

    def hydrate_identity_map(
        self,
        seeds: Sequence[SecuritySeed],
        *,
        force_refresh: bool = False,
    ) -> tuple[IdentityMap, IdAccounting, int]:
        """Hydration leg of §5.2: seeds in, dated intervals out.

        Historical resolution takes the seeds' fsymSecurityIds as INPUTS
        (the only dated direction that exists — pit_asymmetry) and hydrates
        dated CUSIP/SEDOL/ISIN/tickerRegion intervals, dates verbatim.
        Returns (map, hydration accounting, requests executed). Callers who
        already resolved their universe pass those seeds here so the
        seeding requests are never re-shaped into new cache identities.
        """
        identity_map = IdentityMap()
        for seed in seeds:
            identity_map.seed(seed)
        fsym_inputs = [
            TypedIdentifier(IdentifierScheme.FSYM_SECURITY, seed.fsym_security_id)
            for seed in seeds
        ]
        if not fsym_inputs:
            return identity_map, IdAccounting(requested=()), 0
        hydration = self.resolve_historical(fsym_inputs, force_refresh=force_refresh)
        for row in hydration.rows:
            if row.value is None or row.output_type is None:
                continue  # explicit-empty echo; accounted, not stored
            scheme = _HISTORICAL_SCHEME.get(row.output_type.lower())
            if scheme is None:
                raise FactSetIdentityError(
                    f"historical row carries undocumented outputType"
                    f" {row.output_type!r} (F-004 limits outputs to"
                    " SEDOL/CUSIP/ISIN/tickerRegion)"
                )
            identity_map.hydrate(
                IdentifierInterval(
                    security_id=identity_map.security_id_for(row.request_id),
                    id_scheme=scheme,
                    id_value=row.value,
                    start_date_raw=row.start_date,
                    end_date_raw=row.end_date,
                    source="symbology/historical-identifier-resolution",
                )
            )
        return identity_map, hydration.accounting, hydration.requests_executed

    def build_identity_map(
        self, identifiers: Sequence[TypedIdentifier]
    ) -> IdentityMapBuild:
        """Seed from fsym ids, hydrate outward with dated intervals (§5.2).

        Two passes: (1) current resolution mints the spine from
        fsymSecurityId; (2) :meth:`hydrate_identity_map`.
        """
        seeds, seed_resolution = self.seed_securities(identifiers)
        identity_map, hydrate_accounting, hydrate_requests = self.hydrate_identity_map(
            seeds
        )
        return IdentityMapBuild(
            identity_map=identity_map,
            seed_accounting=seed_resolution.accounting,
            hydrate_accounting=hydrate_accounting,
            requests_executed=seed_resolution.requests_executed + hydrate_requests,
        )

    # ── legacy bridge (§5.1) ────────────────────────────────────────────

    def bridge_legacy_security(
        self,
        *,
        ticker: str,
        exchange: str,
        first_seen: date,
        retrieval_date: date,
    ) -> BridgeOutcome:
        """Bridge a legacy (ticker, exchange) security onto the fsym spine.

        Current resolution (tickerExchange input) finds the candidate
        fsym; the DATED cross-check (historical tickerRegion intervals
        covering the drop's retrieval date with the same ticker) guards
        against recycled tickers before the bridge is accepted. All
        fallbacks are typed, counted decisions (§5.1).
        """
        candidate = TypedIdentifier(
            IdentifierScheme.TICKER_EXCHANGE,
            f"{ticker.strip().upper()}-{exchange.strip().upper()}",
        )
        resolution = self.resolve_current(
            [candidate], output_symbol_types=("fsymSecurityId",)
        )
        fsym: str | None = None
        key = account_key(candidate)
        if (
            resolution.accounting.category_of(key)
            is AccountingCategory.SUCCESSFULLY_RETRIEVED
        ):
            fsym = _fold_outputs(resolution.outputs_for(candidate)).get(
                "fsymsecurityid"
            )
        historical: list[tuple[str, str | None, str | None]] = []
        if fsym is not None:
            hist = self.resolve_historical(
                [TypedIdentifier(IdentifierScheme.FSYM_SECURITY, fsym)],
                output_symbol_types=("tickerRegion",),
            )
            historical = [
                (row.value, row.start_date, row.end_date)
                for row in hist.rows
                if row.value is not None
            ]
        return evaluate_bridge(
            ticker=ticker,
            exchange=exchange,
            first_seen=first_seen,
            retrieval_date=retrieval_date,
            resolved_fsym_security_id=fsym,
            historical_ticker_regions=historical,
        )


# ── helpers ──────────────────────────────────────────────────────────────


def _dedupe(identifiers: Sequence[TypedIdentifier]) -> tuple[TypedIdentifier, ...]:
    """Order-independent, duplicate-free identifier set (VF-FS010-9 at the
    typed level; values are already canonical via the casing policy)."""
    unique = sorted(set(identifiers), key=lambda i: (i.scheme.value, i.value))
    return tuple(unique)


def _group_by_scheme(
    identifiers: Sequence[TypedIdentifier],
) -> dict[IdentifierScheme, tuple[str, ...]]:
    if not identifiers:
        raise FactSetIdentityError("no identifiers to resolve (caller bug)")
    groups: dict[IdentifierScheme, list[str]] = {}
    for identifier in _dedupe(identifiers):
        groups.setdefault(identifier.scheme, []).append(identifier.value)
    # normalize_id_list on EVERY request path (VF-FS010-9): sorted+deduped
    # value tuples per scheme, deterministic chunk membership downstream.
    return {
        scheme: normalize_id_list(values)
        for scheme, values in sorted(groups.items(), key=lambda kv: kv[0].value)
    }


def _fold_outputs(outputs: Mapping[str, str | None]) -> dict[str, str | None]:
    """Case-fold requested-output keys (dynamic key casing is U-5)."""
    return {k.lower(): v for k, v in outputs.items()}


def _refuse_ambiguous_current(
    rows: Sequence[ResolutionRow],
) -> tuple[ResolutionRow, ...]:
    seen: dict[str, ResolutionRow] = {}
    unique: list[ResolutionRow] = []
    for row in rows:
        prior = seen.get(row.request_id)
        if prior is not None and prior != row:
            raise AmbiguousResolutionError(
                f"requestId {row.request_id!r} resolved to multiple"
                f" conflicting candidates: {dict(prior.outputs)!r} vs"
                f" {dict(row.outputs)!r}; refusing to pick silently"
                " (D-017 spirit; record as U-6 evidence)"
            )
        if prior is not None:
            continue  # exact duplicate payload: one output grain
        seen[row.request_id] = row
        unique.append(row)
    return tuple(unique)


def _validate_current_rows(
    scheme: IdentifierScheme,
    chunk: Sequence[str],
    rows: Sequence[ResolutionRow],
) -> tuple[ResolutionRow, ...]:
    """Validate typed response echoes and normalize supported outputs."""
    _check_unrequested(scheme, chunk, [row.request_id for row in rows])
    validated: list[ResolutionRow] = []
    for row in rows:
        _check_echoed_input_scheme(scheme, row.input_symbol_type, row.request_id)
        outputs: dict[str, str | None] = {}
        for output_type, value in row.outputs.items():
            declared = _OUTPUT_IDENTIFIER_SCHEME.get(output_type.lower())
            outputs[output_type] = (
                TypedIdentifier(declared, value).value
                if declared is not None and value is not None
                else value
            )
        validated.append(replace(row, outputs=outputs))
    return tuple(validated)


def _validate_historical_rows(
    scheme: IdentifierScheme,
    chunk: Sequence[str],
    requested_output_types: Sequence[str],
    rows: Sequence[HistoricalResolutionRow],
) -> tuple[HistoricalResolutionRow, ...]:
    """Validate typed echoes/output levels and canonicalize interval ids."""
    _check_unrequested(scheme, chunk, [row.request_id for row in rows])
    requested = {output.lower(): output for output in requested_output_types}
    validated: list[HistoricalResolutionRow] = []
    for row in rows:
        _check_echoed_input_scheme(scheme, row.input_symbol_type, row.request_id)
        if row.output_type is None:
            if row.value is not None:
                raise FactSetIdentityError(
                    f"historical row for {row.request_id!r} carries a value"
                    " without outputType; unusable identity evidence"
                )
            validated.append(row)
            continue
        canonical_output = requested.get(row.output_type.lower())
        if canonical_output is None:
            raise FactSetIdentityError(
                f"historical row for {row.request_id!r} returned outputType"
                f" {row.output_type!r} that was not requested"
            )
        declared = _OUTPUT_IDENTIFIER_SCHEME.get(canonical_output.lower())
        if declared is None:
            raise FactSetIdentityError(
                f"historical outputType {canonical_output!r} has no typed"
                " identity validator (F-004)"
            )
        normalized_value = (
            TypedIdentifier(declared, row.value).value
            if row.value is not None
            else None
        )
        validated.append(
            replace(
                row,
                output_type=canonical_output,
                value=normalized_value,
            )
        )
    return tuple(validated)


def _check_echoed_input_scheme(
    requested: IdentifierScheme, echoed: str, request_id: str
) -> None:
    if echoed != requested.value:
        rendered = echoed if echoed else "<missing>"
        raise FactSetIdentityError(
            f"response row for {request_id!r} echoed inputSymbolType"
            f" {rendered!r}, expected declared scheme {requested.value!r};"
            " typed resolution refuses response scheme confusion"
        )


def _check_unrequested(
    scheme: IdentifierScheme, chunk: Sequence[str], returned_ids: Sequence[str]
) -> None:
    unrequested = sorted(set(returned_ids) - set(chunk))
    if unrequested:
        raise FactSetIdentityError(
            f"vendor echoed requestIds that were never requested for scheme"
            f" {scheme.value}: {unrequested!r} (join keys must echo inputs"
            " verbatim — identity_semantics.join_key)"
        )


def _account_chunk_failure(
    accounting: IdAccounting,
    scheme: IdentifierScheme,
    chunk: Sequence[str],
    exc: FactSetTransportError,
) -> None:
    """Map a chunk-level transport failure onto per-id categories.

    Auth errors, kill-switch/budget refusals, cache misses, and config
    errors are NOT per-id outcomes — they re-raise (aborting is honest;
    accounting them as id failures would fabricate vendor evidence).
    """
    if isinstance(exc, FactSetEntitlementError):
        category = AccountingCategory.NOT_ENTITLED
        reason = f"entitlement refusal for the chunk: {exc}"
    elif isinstance(exc, FactSetRequestTooLargeError | FactSetClientError):
        category = AccountingCategory.INVALID_REQUEST
        reason = f"request refused by vendor: {exc}"
    elif isinstance(
        exc,
        FactSetServerError | FactSetRetryExhaustedError | FactSetRateLimitError,
    ):
        category = AccountingCategory.VENDOR_API_FAILURE
        reason = f"vendor/API failure after retries: {exc}"
    else:
        raise exc
    logger.warning(
        "accounting %d id(s) of scheme %s as %s",
        len(chunk),
        scheme.value,
        category.value,
    )
    for value in chunk:
        accounting.assign(f"{scheme.value}:{value}", category, reason)
