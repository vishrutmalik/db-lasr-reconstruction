"""FactSet identity spine: typed identifiers, minting v2, identity map (FS011).

# arch: docs/architecture/factset_integration.md §5 (identity design);
docs/factset/capability/MANIFEST.md + symbology.json identity_semantics
(normative); D-020(b); CE-2/CE-7; EA WP2 + §9 accounting.

Rules encoded here (all pure logic — no I/O, no transport):

- **Typed resolution only (D-020(b)):** identifier schemes are DECLARED by
  the caller, never guessed from string shape. Values are validated
  against the declared scheme's documented structure and refused on
  mismatch (a typed refusal is validation, not guessing).
- **Casing policy (RT-FS010-2 → FS011):** identifier values are
  normalized to stripped UPPERCASE before any request is built, so
  ``aapl-us`` and ``AAPL-US`` are ONE logical identifier, one cache
  identity, one quota unit. CUSIP/ISIN/SEDOL are defined over uppercase
  alphanumerics; FactSet tickerRegion/tickerExchange and fsym ids are
  uppercase in every documented example (A-FS011-02).
- **Minting v2 (CE-7):** ``mint_security_id_v2(scheme, value)`` — fsym-first
  deterministic minting alongside (never replacing) the v1 policy in
  ``lasr.core.ids``. Domain-separated from v1 by a lowercase payload
  sentinel that v1 (which uppercases its ticker field) can never produce.
- **fsym-seeded, hydrated outward (§5.2):** the identity map is seeded
  from fsym ids; historical hydration stores dated
  CUSIP/SEDOL/ISIN/tickerRegion intervals (F-004) with the raw
  ``endDate`` preserved VERBATIM — open-interval closure convention is
  UNRESOLVED (U-7c) and is never guessed at storage time.
- **No silent duplicate identities (WP2):** minting collisions and
  conflicting interval claims are typed errors, never silent picks.
- **Bridge with dated cross-check (§5.1):** legacy (ticker, exchange)
  securities bridge onto fsym-minted ids only after a dated historical
  cross-check; failure/disagreement falls back to v1 minting as a TYPED,
  COUNTED event.
- **7-way accounting (EA §9):** every requested id lands in exactly one
  of seven categories; silent loss is prohibited.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

from lasr.core.ids import SECURITY_ID_PREFIX, SecurityId, mint_security_id
from lasr.data.providers.base import ProviderError

__all__ = [
    "CE2_ID_SCHEME",
    "FSYM_LEVEL_SUFFIX",
    "AccountingCategory",
    "BridgeDecision",
    "BridgeOutcome",
    "DuplicateIdentityError",
    "FactSetIdentityError",
    "IdAccounting",
    "IdentifierInterval",
    "IdentifierScheme",
    "IdentityMap",
    "SecuritySeed",
    "TypedIdentifier",
    "evaluate_bridge",
    "merge_accounting",
    "mint_security_id_v2",
    "normalize_identifier_value",
]


class FactSetIdentityError(ProviderError):
    """Typed refusal from the identity layer: a value that does not match
    its DECLARED scheme, an unsupported scheme, or a malformed request.

    Never a silent skip — D-020(b) forbids shape-guessing, so a mismatch
    between declared scheme and value structure surfaces loudly.
    """


class DuplicateIdentityError(ProviderError):
    """Two distinct identity claims collide (minting collision, or one
    market identifier claimed by two securities over overlapping validity)
    — WP2: corporate actions must not create SILENT duplicate identities,
    so collisions are typed errors, never silent picks."""


# ── typed identifier schemes (D-020(b)) ─────────────────────────────────


class IdentifierScheme(StrEnum):
    """Identifier schemes the identity authority accepts, spelled as the
    symbology wire ``inputSymbolType`` values (FS003 enum subset).

    The subset is the FS011 charter surface: market identifiers
    (CUSIP/ISIN/SEDOL/tickerRegion/tickerExchange) plus the four fsym
    permanent-id levels. Other FS003 enum values (LEI, CIK, ...) are out
    of the charter's typed surface and refuse loudly.
    """

    CUSIP = "CUSIP"
    ISIN = "ISIN"
    SEDOL = "SEDOL"
    TICKER_REGION = "tickerRegion"
    TICKER_EXCHANGE = "tickerExchange"
    FSYM_ENTITY = "fsymEntityId"
    FSYM_SECURITY = "fsymSecurityId"
    FSYM_REGIONAL = "fsymRegionalId"
    FSYM_LISTING = "fsymListingId"


#: fsym level marker suffix per scheme (documented id shape: 6 uppercase
#: alphanumerics, hyphen, level letter — e.g. ``MH33D6-S``; the letter IS
#: the level: E=entity, S=security, R=regional, L=listing).
FSYM_LEVEL_SUFFIX: Mapping[IdentifierScheme, str] = {
    IdentifierScheme.FSYM_ENTITY: "E",
    IdentifierScheme.FSYM_SECURITY: "S",
    IdentifierScheme.FSYM_REGIONAL: "R",
    IdentifierScheme.FSYM_LISTING: "L",
}

#: CE-2 provider-neutral ``identifier_map.id_scheme`` values for the four
#: fsym levels (docs/architecture/factset_integration.md §5.2). Recorded
#: here as the FS011-side mapping; the core ``IdScheme`` enum extension is
#: a separate additive edit outside this goal's owned paths.
CE2_ID_SCHEME: Mapping[IdentifierScheme, str] = {
    IdentifierScheme.FSYM_ENTITY: "vendor_entity",
    IdentifierScheme.FSYM_SECURITY: "vendor_security_perm",
    IdentifierScheme.FSYM_REGIONAL: "vendor_regional",
    IdentifierScheme.FSYM_LISTING: "vendor_listing",
    IdentifierScheme.CUSIP: "cusip",
    IdentifierScheme.ISIN: "isin",
    IdentifierScheme.SEDOL: "sedol",
    IdentifierScheme.TICKER_REGION: "ticker",
    IdentifierScheme.TICKER_EXCHANGE: "ticker",
}

# Historical Symbology outputs are stored in the provider-neutral CE-2
# vocabulary, but validation still uses the declared FactSet wire scheme.
_INTERVAL_IDENTIFIER_SCHEME: Mapping[str, IdentifierScheme] = {
    "ticker": IdentifierScheme.TICKER_REGION,
    "cusip": IdentifierScheme.CUSIP,
    "isin": IdentifierScheme.ISIN,
    "sedol": IdentifierScheme.SEDOL,
}

_CUSIP_RE = re.compile(r"^[A-Z0-9]{9}$")
_ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
_SEDOL_RE = re.compile(r"^[A-Z0-9]{7}$")
_FSYM_RE = re.compile(r"^[A-Z0-9]{6}-[ESRL]$")
#: ticker part may carry '.' (share classes, e.g. BRK.B) — suffix after the
#: LAST hyphen is the region/exchange code (2-4 letters).
_TICKER_SUFFIXED_RE = re.compile(r"^[A-Z0-9.\-]+-[A-Z]{2,4}$")


def normalize_identifier_value(value: str) -> str:
    """The FS011 casing policy (RT-FS010-2): strip + UPPERCASE.

    Applied before validation, minting, and request building, so one
    logical identifier can never occupy two cache identities or spend two
    quota units on casing alone. Empty values refuse loudly.
    """
    normalized = value.strip().upper()
    if not normalized:
        raise FactSetIdentityError(
            "identifier value is empty after normalization (a blank id is"
            " a caller bug, not a query)"
        )
    return normalized


def _validate_value(scheme: IdentifierScheme, value: str) -> None:
    """Structural validation of ``value`` against its DECLARED scheme.

    This is the D-020(b) discipline in reverse: we never infer a scheme
    from a shape, but a declared scheme whose value cannot structurally be
    that scheme is a typed refusal (it would otherwise burn quota on a
    guaranteed non-resolution or, worse, resolve as the WRONG scheme).
    """
    checks: Mapping[IdentifierScheme, re.Pattern[str]] = {
        IdentifierScheme.CUSIP: _CUSIP_RE,
        IdentifierScheme.ISIN: _ISIN_RE,
        IdentifierScheme.SEDOL: _SEDOL_RE,
        IdentifierScheme.TICKER_REGION: _TICKER_SUFFIXED_RE,
        IdentifierScheme.TICKER_EXCHANGE: _TICKER_SUFFIXED_RE,
    }
    pattern = checks.get(scheme)
    if pattern is not None:
        if not pattern.match(value):
            raise FactSetIdentityError(
                f"value {value!r} does not match the declared scheme"
                f" {scheme.value}: expected {pattern.pattern}"
            )
        return
    # fsym levels: shape + the level letter must MATCH the declared level
    # (declaring fsymSecurityId for 'MH33D6-R' is a caller bug).
    if not _FSYM_RE.match(value):
        raise FactSetIdentityError(
            f"value {value!r} does not match the fsym id shape"
            f" {_FSYM_RE.pattern} for declared scheme {scheme.value}"
        )
    expected = FSYM_LEVEL_SUFFIX[scheme]
    actual = value[-1]
    if actual != expected:
        raise FactSetIdentityError(
            f"fsym level marker mismatch: value {value!r} carries level"
            f" -{actual} but the declared scheme {scheme.value} requires"
            f" -{expected} (typed resolution never reinterprets levels)"
        )


@dataclass(frozen=True)
class TypedIdentifier:
    """One identifier with its caller-DECLARED scheme (D-020(b)).

    Construction normalizes (casing policy) and validates the value
    against the declared scheme; an instance is therefore always
    well-formed and canonical.
    """

    scheme: IdentifierScheme
    value: str

    def __post_init__(self) -> None:
        normalized = normalize_identifier_value(self.value)
        object.__setattr__(self, "value", normalized)
        _validate_value(self.scheme, normalized)


# ── minting v2 (CE-7) ────────────────────────────────────────────────────

#: Lowercase domain sentinel: v1 payloads are ``TICKER|EXCHANGE|date``
#: with ticker/exchange UPPERCASED, so no v1 payload can ever start with
#: this lowercase token — the two minting domains cannot collide.
_MINT_V2_SENTINEL = "mintv2"


def mint_security_id_v2(scheme: str, value: str) -> SecurityId:
    """Mint an internal ``security_id`` from a permanent identifier (CE-7).

    fsym-first policy (§5.1): for FactSet-resolved securities call with
    ``scheme="vendor_security_perm"`` (CE-2 vocabulary) and the
    fsymSecurityId — deterministic and stable across ticker changes,
    listing moves, and delisting/relisting. Lives beside (never replacing)
    v1: identifier-less providers keep ``mint_security_id``.

    Deterministic + normalization-invariant: scheme is lowercased, value
    goes through the casing policy, so re-ingestion re-mints identically.
    Same ``SEC-`` + 12-hex convention as v1 (the spine stays opaque);
    domain separation is structural via the lowercase sentinel.
    """
    scheme_norm = scheme.strip().lower()
    if not scheme_norm:
        raise FactSetIdentityError("mint_security_id_v2 requires a non-empty scheme")
    value_norm = normalize_identifier_value(value)
    payload = f"{_MINT_V2_SENTINEL}|{scheme_norm}|{value_norm}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{SECURITY_ID_PREFIX}-{digest[:12]}"


# ── identity map: fsym-seeded, hydrated outward (§5.2) ──────────────────


@dataclass(frozen=True)
class SecuritySeed:
    """One fsym-resolved security seeding the identity map.

    ``fsym_security_id`` is the spine (mints the internal id); regional/
    listing/entity ids keep primary vs secondary listings distinguishable
    (WP2) and carry the security→entity edge (CFC-9: RBICS is
    entity-level). Enrichment fields are evidence, never identity.
    """

    fsym_security_id: str
    fsym_entity_id: str | None = None
    fsym_regional_id: str | None = None
    fsym_listing_id: str | None = None
    name: str | None = None
    fref_listing_exchange: str | None = None
    currency: str | None = None

    def __post_init__(self) -> None:
        normalized = normalize_identifier_value(self.fsym_security_id)
        _validate_value(IdentifierScheme.FSYM_SECURITY, normalized)
        object.__setattr__(self, "fsym_security_id", normalized)
        for attr, scheme in (
            ("fsym_entity_id", IdentifierScheme.FSYM_ENTITY),
            ("fsym_regional_id", IdentifierScheme.FSYM_REGIONAL),
            ("fsym_listing_id", IdentifierScheme.FSYM_LISTING),
        ):
            raw = getattr(self, attr)
            if raw is not None:
                value = normalize_identifier_value(raw)
                _validate_value(scheme, value)
                object.__setattr__(self, attr, value)

    @property
    def security_id(self) -> SecurityId:
        return mint_security_id_v2(
            CE2_ID_SCHEME[IdentifierScheme.FSYM_SECURITY], self.fsym_security_id
        )


@dataclass(frozen=True)
class IdentifierInterval:
    """One dated identifier claim: security x scheme x value x validity.

    ``start_date_raw``/``end_date_raw`` are the VENDOR strings verbatim
    (U-7c: the open-interval ``endDate`` convention is UNRESOLVED — no
    closure convention is guessed; ``None`` means the vendor sent no
    value). Knowledge-time note (D-009): these are EFFECTIVE dates, not
    publication timestamps — event time, not knowledge time.
    """

    security_id: SecurityId
    id_scheme: str
    id_value: str
    start_date_raw: str | None
    end_date_raw: str | None
    source: str

    def __post_init__(self) -> None:
        scheme_key = self.id_scheme.strip().lower()
        declared_scheme = _INTERVAL_IDENTIFIER_SCHEME.get(scheme_key)
        if declared_scheme is None:
            raise FactSetIdentityError(
                f"historical identifier scheme {self.id_scheme!r} is not"
                " one of ticker/cusip/isin/sedol (F-004)"
            )
        normalized_value = normalize_identifier_value(self.id_value)
        _validate_value(declared_scheme, normalized_value)
        object.__setattr__(self, "id_scheme", scheme_key)
        object.__setattr__(self, "id_value", normalized_value)

        # Eager parse check: raw strings are stored VERBATIM, but a vendor
        # date that is not ISO-8601 is quarantined at construction, never
        # discovered lazily mid-join.
        start = _parse_iso(self.start_date_raw)
        end = _parse_iso(self.end_date_raw)
        if start is not None and end is not None and start > end:
            raise FactSetIdentityError(
                f"vendor interval is inverted: startDate"
                f" {self.start_date_raw!r} is after endDate"
                f" {self.end_date_raw!r}; quarantine, never repair"
            )

    def parsed_start(self) -> date | None:
        return _parse_iso(self.start_date_raw)

    def parsed_end(self) -> date | None:
        return _parse_iso(self.end_date_raw)


def _parse_iso(raw: str | None) -> date | None:
    if raw is None:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise FactSetIdentityError(
            f"vendor interval date {raw!r} is not ISO-8601; quarantine, never repair"
        ) from exc


def _overlaps(a: IdentifierInterval, b: IdentifierInterval) -> bool:
    """Conservative overlap test for duplicate-identity DETECTION only.

    A ``None`` end bounds nothing (treated as open) — this deliberately
    over-flags rather than under-flags; it never writes a closure
    convention into stored data (U-7c stays verbatim).
    """
    a_start, a_end = a.parsed_start(), a.parsed_end()
    b_start, b_end = b.parsed_start(), b.parsed_end()
    lo_a = a_start or date.min
    hi_a = a_end or date.max
    lo_b = b_start or date.min
    hi_b = b_end or date.max
    return lo_a <= hi_b and lo_b <= hi_a


class IdentityMap:
    """fsym-seeded identity map, hydrated outward (§5.2).

    Seeding registers a :class:`SecuritySeed` (minting its internal id and
    the four fsym-level identifier rows); hydration appends dated
    market-identifier intervals from historical resolution. Identifier
    reuse (a recycled ticker) is legal as two NON-overlapping intervals
    pointing at different securities; an OVERLAPPING claim of one
    (scheme, value) by two securities is a typed
    :class:`DuplicateIdentityError` — never a silent pick.
    """

    def __init__(self) -> None:
        self._seeds: dict[str, SecuritySeed] = {}
        self._by_security: dict[SecurityId, str] = {}
        self._intervals: list[IdentifierInterval] = []

    # ── seeding ─────────────────────────────────────────────────────────

    def seed(self, seed: SecuritySeed) -> SecurityId:
        """Register one fsym-resolved security.

        An exactly equivalent reassertion is idempotent. The same fsym with
        any different entity/regional/listing or enrichment claim is a typed
        refusal: first-write-wins would silently erase cross-API evidence.
        """
        fsym = normalize_identifier_value(seed.fsym_security_id)
        security_id = seed.security_id
        existing = self._seeds.get(fsym)
        if existing is not None:
            if existing == seed:
                return existing.security_id
            raise DuplicateIdentityError(
                f"conflicting re-seed for fsym {fsym!r}: the existing and"
                " repeated SecuritySeed claims are not exactly equivalent;"
                " refusing first-write-wins identity loss (WP2)"
            )
        claimed = self._by_security.get(security_id)
        if claimed is not None and claimed != fsym:
            raise DuplicateIdentityError(
                f"minting collision: fsym ids {claimed!r} and {fsym!r} both"
                f" mint {security_id!r}; no silent duplicate identities"
                " (WP2) — widen the mint digest before proceeding"
            )
        self._seeds[fsym] = seed
        self._by_security[security_id] = fsym
        return security_id

    def security_id_for(self, fsym_security_id: str) -> SecurityId:
        fsym = normalize_identifier_value(fsym_security_id)
        seed = self._seeds.get(fsym)
        if seed is None:
            raise FactSetIdentityError(
                f"fsym id {fsym!r} is not seeded in the identity map; seed"
                " from current resolution before hydrating (§5.2: the map"
                " is seeded from fsym ids, hydrated outward)"
            )
        return seed.security_id

    @property
    def seeds(self) -> tuple[SecuritySeed, ...]:
        return tuple(self._seeds.values())

    # ── hydration (historical intervals) ────────────────────────────────

    def hydrate(self, interval: IdentifierInterval) -> None:
        """Append one dated identifier interval (verbatim dates).

        Refuses (typed) when the same (scheme, value) is claimed by a
        DIFFERENT security over an overlapping window; an identical
        re-assertion is an idempotent no-op.
        """
        if interval.security_id not in self._by_security:
            raise FactSetIdentityError(
                f"interval references unseeded security {interval.security_id!r}"
            )
        for existing in self._intervals:
            if (
                existing.id_scheme == interval.id_scheme
                and existing.id_value == interval.id_value
            ):
                if existing == interval:
                    return  # idempotent re-assertion
                if existing.security_id != interval.security_id and _overlaps(
                    existing, interval
                ):
                    raise DuplicateIdentityError(
                        f"identifier {interval.id_scheme}:{interval.id_value!r}"
                        f" is claimed by {existing.security_id!r}"
                        f" [{existing.start_date_raw}..{existing.end_date_raw}]"
                        f" AND {interval.security_id!r}"
                        f" [{interval.start_date_raw}..{interval.end_date_raw}]"
                        " over overlapping validity; no silent duplicate"
                        " identities (WP2)"
                    )
        self._intervals.append(interval)

    @property
    def intervals(self) -> tuple[IdentifierInterval, ...]:
        return tuple(self._intervals)

    def intervals_for(self, security_id: SecurityId) -> tuple[IdentifierInterval, ...]:
        return tuple(i for i in self._intervals if i.security_id == security_id)


# ── bridge: legacy (ticker, exchange) → fsym (§5.1) ─────────────────────


class BridgeDecision(StrEnum):
    """Typed, counted bridge outcomes (§5.1: never a silent second
    identity)."""

    BRIDGED_FSYM = "bridged_fsym"  # resolution + dated cross-check agree
    FALLBACK_NO_RESOLUTION = "fallback_no_resolution"  # v1 mint retained
    FALLBACK_CROSSCHECK_DISAGREE = "fallback_crosscheck_disagree"  # v1 mint
    FALLBACK_CROSSCHECK_UNVERIFIABLE = "fallback_crosscheck_unverifiable"


@dataclass(frozen=True)
class BridgeOutcome:
    """Result of bridging one legacy (ticker, exchange) security."""

    decision: BridgeDecision
    security_id: SecurityId
    minting_policy: str  # "fsym_first" | "legacy_v1"
    fsym_security_id: str | None
    legacy_alias_id: SecurityId  # v1 id, recorded as provider_native alias
    reason: str


@dataclass(frozen=True)
class _CrosscheckInterval:
    """One historical tickerRegion interval used by the bridge check."""

    value: str
    start: date | None
    end: date | None


def _covers(interval: _CrosscheckInterval, on: date) -> bool:
    """Coverage test for the bridge cross-check.

    A ``None`` end is read as open-through-present (A-FS011-03): rejecting
    every open interval would fail the cross-check for ALL currently
    active securities, which is unambiguously wrong; the reading is an
    assumption pending U-7c observation, recorded, and applied ONLY to
    this decision — stored intervals stay verbatim.
    """
    lo = interval.start or date.min
    hi = interval.end or date.max
    return lo <= on <= hi


def evaluate_bridge(
    *,
    ticker: str,
    exchange: str,
    first_seen: date,
    retrieval_date: date,
    resolved_fsym_security_id: str | None,
    historical_ticker_regions: Sequence[tuple[str, str | None, str | None]],
) -> BridgeOutcome:
    """Decide fsym-first vs legacy-v1 minting for one legacy security.

    Pure §5.1 logic (the adapter supplies the resolution evidence):

    - ``resolved_fsym_security_id``: fsymSecurityId from CURRENT
      resolution of the (ticker, exchange) — ``None`` when unresolved;
    - ``historical_ticker_regions``: dated tickerRegion rows for that
      fsym as (value, startDate, endDate) vendor strings.

    Accept the bridge only when some historical tickerRegion interval
    covers ``retrieval_date`` with the SAME ticker (current resolution is
    UNDATED — a recycled ticker could mis-map an old drop without this
    check). Any failure → v1 fallback with a typed, counted decision.
    """
    legacy_id = mint_security_id(ticker, exchange, first_seen)
    ticker_norm = normalize_identifier_value(ticker)

    if resolved_fsym_security_id is None:
        return BridgeOutcome(
            decision=BridgeDecision.FALLBACK_NO_RESOLUTION,
            security_id=legacy_id,
            minting_policy="legacy_v1",
            fsym_security_id=None,
            legacy_alias_id=legacy_id,
            reason=(
                f"current resolution returned no fsymSecurityId for"
                f" {ticker_norm}/{exchange.strip().upper()}; v1 minting"
                " retained (typed fallback, §5.1)"
            ),
        )

    fsym = normalize_identifier_value(resolved_fsym_security_id)
    _validate_value(IdentifierScheme.FSYM_SECURITY, fsym)

    if not historical_ticker_regions:
        return BridgeOutcome(
            decision=BridgeDecision.FALLBACK_CROSSCHECK_UNVERIFIABLE,
            security_id=legacy_id,
            minting_policy="legacy_v1",
            fsym_security_id=fsym,
            legacy_alias_id=legacy_id,
            reason=(
                f"no historical tickerRegion intervals returned for {fsym};"
                " the dated cross-check cannot verify the undated current"
                " resolution — v1 minting retained"
            ),
        )

    intervals = [
        _CrosscheckInterval(
            value=normalize_identifier_value(value),
            start=_parse_iso(start),
            end=_parse_iso(end),
        )
        for value, start, end in historical_ticker_regions
    ]
    covering = [i for i in intervals if _covers(i, retrieval_date)]
    matching = [i for i in covering if i.value.rsplit("-", 1)[0] == ticker_norm]
    if matching:
        return BridgeOutcome(
            decision=BridgeDecision.BRIDGED_FSYM,
            security_id=mint_security_id_v2(
                CE2_ID_SCHEME[IdentifierScheme.FSYM_SECURITY], fsym
            ),
            minting_policy="fsym_first",
            fsym_security_id=fsym,
            legacy_alias_id=legacy_id,
            reason=(
                f"dated cross-check agreed: {matching[0].value} covers"
                f" {retrieval_date.isoformat()} with ticker {ticker_norm};"
                " legacy v1 id recorded as provider_native alias (§5.1)"
            ),
        )
    return BridgeOutcome(
        decision=BridgeDecision.FALLBACK_CROSSCHECK_DISAGREE,
        security_id=legacy_id,
        minting_policy="legacy_v1",
        fsym_security_id=fsym,
        legacy_alias_id=legacy_id,
        reason=(
            f"dated cross-check disagreed: no historical tickerRegion"
            f" interval for {fsym} covers {retrieval_date.isoformat()} with"
            f" ticker {ticker_norm} (recycled-ticker hazard); v1 minting"
            " retained (typed fallback, §5.1)"
        ),
    )


# ── 7-way accounting (EA §9) ─────────────────────────────────────────────


class AccountingCategory(StrEnum):
    """EA §9: every requested record set is accounted for as ONE of these
    seven outcomes; silent loss is prohibited."""

    SUCCESSFULLY_RETRIEVED = "successfully_retrieved"
    VALIDLY_EMPTY = "validly_empty"
    INELIGIBLE_IDENTIFIER = "ineligible_identifier"
    NOT_COVERED = "not_covered"
    NOT_ENTITLED = "not_entitled"
    INVALID_REQUEST = "invalid_request"
    VENDOR_API_FAILURE = "vendor_api_failure"


@dataclass(frozen=True)
class _AccountingEntry:
    category: AccountingCategory
    reason: str


@dataclass
class IdAccounting:
    """Mapped-or-explained ledger for one identity operation (WP2/EA §9).

    Every requested id must be ``assign``-ed exactly once;
    ``verify_complete`` is the silent-loss gate (raises when any id is
    unaccounted or double-accounted — re-assignment refuses immediately).
    """

    requested: tuple[str, ...]
    _entries: dict[str, _AccountingEntry] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if len(set(self.requested)) != len(self.requested):
            raise FactSetIdentityError(
                "accounting requires a deduplicated requested-id list"
                " (normalize_id_list upstream)"
            )

    def assign(self, id_value: str, category: AccountingCategory, reason: str) -> None:
        if id_value not in self.requested:
            raise FactSetIdentityError(
                f"cannot account for {id_value!r}: not in the requested set"
            )
        existing = self._entries.get(id_value)
        if existing is not None:
            raise FactSetIdentityError(
                f"id {id_value!r} is already accounted as"
                f" {existing.category.value} ({existing.reason}); exactly one"
                " category per id (EA §9)"
            )
        if not reason.strip():
            raise FactSetIdentityError(
                f"accounting for {id_value!r} requires an explicit reason"
                " (mapped-or-EXPLAINED)"
            )
        self._entries[id_value] = _AccountingEntry(category=category, reason=reason)

    def category_of(self, id_value: str) -> AccountingCategory:
        entry = self._entries.get(id_value)
        if entry is None:
            raise FactSetIdentityError(f"id {id_value!r} is unaccounted")
        return entry.category

    def reason_of(self, id_value: str) -> str:
        entry = self._entries.get(id_value)
        if entry is None:
            raise FactSetIdentityError(f"id {id_value!r} is unaccounted")
        return entry.reason

    def unaccounted(self) -> tuple[str, ...]:
        return tuple(i for i in self.requested if i not in self._entries)

    def verify_complete(self) -> None:
        missing = self.unaccounted()
        if missing:
            raise FactSetIdentityError(
                f"silent loss detected: {len(missing)} requested id(s) are"
                f" unaccounted {list(missing)!r} (EA §9: silent loss is"
                " prohibited)"
            )

    def summary(self) -> dict[str, int]:
        """Category → count over all SEVEN categories (zeros included)."""
        counts = {c.value: 0 for c in AccountingCategory}
        for entry in self._entries.values():
            counts[entry.category.value] += 1
        return counts

    def rows(self) -> tuple[tuple[str, str, str], ...]:
        """(id, category, reason) rows in requested order (report file)."""
        return tuple(
            (i, self._entries[i].category.value, self._entries[i].reason)
            for i in self.requested
            if i in self._entries
        )


def merge_accounting(parts: Iterable[IdAccounting]) -> dict[str, int]:
    """Aggregate summaries across operations (battery report)."""
    total = {c.value: 0 for c in AccountingCategory}
    for part in parts:
        part.verify_complete()
        for key, count in part.summary().items():
            total[key] += count
    return total
