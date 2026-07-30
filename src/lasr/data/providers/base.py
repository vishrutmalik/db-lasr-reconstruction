"""Provider contract: interface, capability records, typed errors, grading.

# arch: provider_contract.md (G015 spec of record, amended by D-011/D-012).
One contract, three implementations (synthetic G019, local-file G018,
future API adapters G039); every provider passes the same contract-test
suite (CT-01..15, ``tests/integration/test_provider_contract.py``).

Principles enforced here (provider_contract.md preamble):

1. capabilities are declared, verified, and honest — a missing capability
   is a typed error, never silent degradation (MP §26);
2. providers emit raw-shaped frames only (``lasr.data.schemas.raw_*``);
   canonicalization is L-CANON's job;
3. no fake endpoints, no committed credentials (MP §16) — credentials come
   from environment variables read only by ``config``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from enum import StrEnum
from typing import Literal, Protocol

from lasr.core.enums import PitGrade, RevisionSupport
from lasr.core.errors import LasrError
from lasr.data.providers._frames import DataFrame

__all__ = [
    "DEFAULT_PRICE_FIELDS",
    "FAMILY_RAW_TABLES",
    "LISTED_ONLY_PRICE_FIELDS",
    "RETRO_WINDOW_FAMILIES",
    "REVISION_PRONE_FAMILIES",
    "CapabilityError",
    "CorporateActionBasis",
    "DataProvider",
    "DuplicateProviderIdError",
    "FamilyCapability",
    "FieldFamily",
    "FieldUnavailableError",
    "HistoryUnavailableError",
    "IntegrityError",
    "ProviderCapabilities",
    "ProviderError",
    "ProviderId",
    "RevisionSupport",
    "UnknownProviderIdError",
    "bar_knowledge_time",
    "grade_dataset",
    "require_unique_ids",
]


# ── field families and capability records (provider_contract.md §1) ─────────


class FieldFamily(StrEnum):
    """The unit at which capabilities are declared — matches the gap-list
    structure (# arch: provider_contract.md §1)."""

    SECURITY_MASTER = "security_master"  # gap §1
    MARKET_DAILY = "market_daily"  # gap §2
    FUNDAMENTALS = "fundamentals"  # gap §3
    ESTIMATES = "estimates"  # gap §4
    CORPORATE_ACTIONS = "corporate_actions"  # gap §5
    CLASSIFICATIONS = "classifications"  # gap §6
    UNIVERSE_MEMBERSHIP = "universe_membership"  # gap §8
    BORROW = "borrow"  # gap §7
    FX = "fx"  # gap §6 (FX row)
    CALENDAR = "calendar"  # gap §7


class CorporateActionBasis(StrEnum):
    """Adjustment basis of a provider's market prices
    (# arch: provider_contract.md §1)."""

    UNADJUSTED = "unadjusted"
    ADJUSTED = "adjusted"
    UNKNOWN = "unknown"  # FM-17: AlphaSense basis NOT_ESTABLISHED


@dataclass(frozen=True)
class FamilyCapability:
    """Per-family capability declaration (# arch: provider_contract.md §1).

    ``corporate_action_basis`` is meaningful for the market family only
    (FM-17); other families leave it at ``UNKNOWN``. ``notes`` must cite
    the evidence source (CT-01).
    """

    available: bool
    supports_pit: bool  # true knowledge timestamps exist
    revision_support: RevisionSupport
    fields: frozenset[str]  # canonical field names servable
    notes: str  # gap/FM citations (CT-01)
    history_start: date | None = None  # None = NOT_ESTABLISHED (depth caveat)
    corporate_action_basis: CorporateActionBasis = CorporateActionBasis.UNKNOWN

    def __post_init__(self) -> None:
        if not self.notes.strip():
            raise CapabilityError(
                "FamilyCapability.notes must cite an evidence source "
                "(provider_contract.md §5 CT-01)"
            )


@dataclass(frozen=True)
class ProviderCapabilities:
    """Provider-level capability record (# arch: provider_contract.md §1).

    Cross-family flags are the gap_list.md consequences list, verbatim.
    Construction validates completeness: every ``FieldFamily`` must be
    declared (CT-01 is the behavioral re-check per provider instance).
    """

    provider_name: str
    provider_version: str
    families: Mapping[FieldFamily, FamilyCapability]
    supports_universe_screening: bool  # gap §1: single-ticker templates
    supports_publication_timestamps: bool  # gap §3
    supports_delistings: bool  # gap §1
    supports_bid_ask: bool  # gap §2
    supports_borrow: bool  # gap §7
    supports_index_membership: bool  # gap §8
    supports_estimate_history: bool  # gap §4
    supports_vintages: bool  # pit_assessment verdict (A-001)

    def __post_init__(self) -> None:
        missing = [f.value for f in FieldFamily if f not in self.families]
        if missing:
            raise CapabilityError(
                f"capability record for {self.provider_name!r} is incomplete: "
                f"missing families {missing!r} (CT-01)"
            )

    def family(self, family: FieldFamily) -> FamilyCapability:
        """Return the declared capability for ``family``."""
        return self.families[family]


@dataclass(frozen=True)
class ProviderId:
    """Provider-native identifier (# arch: provider_contract.md §2 note).

    ``ticker+exchange`` for the local-file adapter, generator-assigned id
    for the synthetic provider (``exchange=None``). Mapping to the minted
    internal ``security_id`` happens in L-CANON (FM-02) — never here.
    """

    value: str
    exchange: str | None = None

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise UnknownProviderIdError("ProviderId.value must be non-empty")


# ── typed error set (provider_contract.md §3: closed, no silent fallback) ───


class ProviderError(LasrError):
    """Base class of the closed provider error set
    (# arch: provider_contract.md §3)."""


class CapabilityError(ProviderError):
    """Request requires a capability the provider declares false.

    NEVER caught-and-defaulted by callers; surfaces to the user
    (# arch: provider_contract.md §3; MP §26 silent-fallback rule).
    """


class FieldUnavailableError(ProviderError):
    """Requested field not in ``field_coverage(family)``
    (# arch: provider_contract.md §3; D-012 OHLV guard)."""


class HistoryUnavailableError(ProviderError):
    """Window outside ``available_history(family)``.

    Partial windows are NOT silently truncated: the provider returns what
    exists only when the requested window lies within the advertised one;
    otherwise it raises (# arch: provider_contract.md §3, CT-06).
    """


class IntegrityError(ProviderError):
    """Provider payload violates its own raw schema (malformed workbook /
    extract, corrupt file). Ingestion quarantines, never repairs (G021)
    (# arch: provider_contract.md §3)."""


class UnknownProviderIdError(ProviderError):
    """A requested ``ProviderId`` does not resolve to any entity the
    provider serves.

    Addition to the §3 set (flagged for provider_contract.md): silently
    returning an empty frame for a typo'd ticker is exactly the "empty
    frame to signal absence" failure §3 forbids, and none of the four
    documented errors covers entity resolution.
    """


class DuplicateProviderIdError(ProviderError):
    """The same ``ProviderId`` appears more than once in one request.

    G018-verification NB-1: duplicated ids used to produce frames that
    violate the raw schema's primary-key uniqueness. Per §3's
    no-silent-anything principle the fix is a typed REFUSAL, not a silent
    dedupe — a duplicated id is a caller bug (e.g. a double-counted
    portfolio join) that deduping would mask. Shared guard:
    :func:`require_unique_ids`; every adapter applies it before resolving.
    Addition to the §3 closed set (flagged for provider_contract.md).
    """


def require_unique_ids(ids: Sequence[ProviderId]) -> tuple[ProviderId, ...]:
    """NB-1 guard: refuse duplicated ``ProviderId``s in a single request.

    Returns the ids unchanged (as a tuple) when unique, so adapters can
    use it inline at the top of every id-taking fetch method.
    """
    seen: set[ProviderId] = set()
    duplicates: list[str] = []
    for pid in ids:
        if pid in seen:
            duplicates.append(f"{pid.value}/{pid.exchange}")
        seen.add(pid)
    if duplicates:
        raise DuplicateProviderIdError(
            f"duplicate ProviderIds in one request: {sorted(set(duplicates))} "
            "(a duplicated id is a caller bug; frames must keep raw-schema "
            "primary-key uniqueness — G018 verification NB-1)"
        )
    return tuple(ids)


# ── D-012: fetch_prices field defaults and the OHLV guard ───────────────────

#: Evidence-demonstrated default price fields (FM-11/FM-25/FM-31; G013).
DEFAULT_PRICE_FIELDS: tuple[str, ...] = ("close", "market_cap")

#: LISTED_ONLY bar fields (FM-12/13/14): explicit requests MUST raise
#: ``FieldUnavailableError`` (CT-07) until probe VP-01 demonstrates daily
#: retrieval (D-012).
LISTED_ONLY_PRICE_FIELDS: frozenset[str] = frozenset(
    {"open", "high", "low", "volume", "vwap", "shares_outstanding"}
)

# ── D-011: pit-grade split ───────────────────────────────────────────────────

#: Families whose values are restated after the fact — absent true
#: knowledge timestamps they can only be SNAPSHOT_STAMPED (D-011).
REVISION_PRONE_FAMILIES: frozenset[FieldFamily] = frozenset(
    {FieldFamily.FUNDAMENTALS, FieldFamily.ESTIMATES, FieldFamily.CLASSIFICATIONS}
)

#: Market-price families retrieved as retrospective daily windows: prices
#: are publicly knowable at the bar close and are not restated the way
#: filings are, so they may grade RETRO_WINDOW (D-011).
RETRO_WINDOW_FAMILIES: frozenset[FieldFamily] = frozenset(
    {FieldFamily.MARKET_DAILY, FieldFamily.FX}
)

#: Raw tables behind each family (schemas stay at Level 2; the mapping
#: lives here so ``lasr.data.schemas`` never imports providers,
#: system_design.md §4).
FAMILY_RAW_TABLES: Mapping[FieldFamily, tuple[str, ...]] = {
    FieldFamily.SECURITY_MASTER: ("raw_security_master",),
    FieldFamily.MARKET_DAILY: ("raw_market_daily", "raw_market_metrics"),
    FieldFamily.FUNDAMENTALS: ("raw_fundamentals",),
    FieldFamily.ESTIMATES: ("raw_estimates",),
    FieldFamily.CORPORATE_ACTIONS: ("raw_corporate_actions",),
    FieldFamily.CLASSIFICATIONS: ("raw_classifications",),
    FieldFamily.UNIVERSE_MEMBERSHIP: ("raw_universe_membership",),
    FieldFamily.BORROW: ("raw_borrow_daily",),
    FieldFamily.FX: ("raw_fx_rates",),
    FieldFamily.CALENDAR: ("raw_trading_calendars",),
}


def grade_dataset(
    family: FieldFamily,
    capability: FamilyCapability,
    *,
    synthetic_truth: bool = False,
    adjustment_basis_acknowledged: bool = False,
) -> PitGrade:
    """Assign the manifest ``pit_grade`` for a dataset of ``family`` (D-011).

    Decision table (# arch: provider_contract.md §1 as amended by D-011;
    system_design.md §2 L-CANON):

    - unavailable family: grading is a caller bug → ``CapabilityError``;
    - ``supports_pit=true``: ``FULL_VINTAGES`` (or ``SYNTHETIC_TRUTH`` when
      the knowledge times are generator-emitted);
    - market-price retro windows (``MARKET_DAILY``/``FX``): ``RETRO_WINDOW``
      with bar ``knowledge_time`` = close of event date
      (:func:`bar_knowledge_time`), PROVIDED the adjustment-basis check
      passes — the basis is declared (non-``UNKNOWN``, FM-17) or the run
      config explicitly acknowledges the unknown basis (CT-15 guard).
      A failed basis check downgrades to ``SNAPSHOT_STAMPED``
      (``knowledge_time = retrieval_time`` is strictly later than the bar
      close, so the downgrade can never introduce leakage; the downgrade
      is recorded in the manifest, not silent);
    - every other non-PIT family (the revision-prone set and current-value
      snapshots): ``SNAPSHOT_STAMPED``. Nothing downstream may upgrade a
      grade.
    """
    if not capability.available:
        raise CapabilityError(
            f"cannot grade family {family.value!r}: provider declares it "
            "unavailable (grading an unserved family is a caller bug)"
        )
    if capability.supports_pit:
        return PitGrade.SYNTHETIC_TRUTH if synthetic_truth else PitGrade.FULL_VINTAGES
    if family in RETRO_WINDOW_FAMILIES:
        basis_known = (
            capability.corporate_action_basis is not CorporateActionBasis.UNKNOWN
        )
        # FX carries no corporate-action basis; the check applies to
        # MARKET_DAILY only (FM-17 is a price-adjustment concern).
        basis_ok = (
            family is not FieldFamily.MARKET_DAILY
            or basis_known
            or adjustment_basis_acknowledged
        )
        if basis_ok:
            return PitGrade.RETRO_WINDOW
        return PitGrade.SNAPSHOT_STAMPED
    return PitGrade.SNAPSHOT_STAMPED


def bar_knowledge_time(event_date: date, close_time: time) -> datetime:
    """D-011 bar convention: ``knowledge_time`` = close of the event date.

    ``close_time`` is the configured market-close time
    (``data.bar_knowledge_convention``, system_design.md §1) — it is a
    caller-supplied config value, never a hard-coded exchange assumption.
    A naive ``close_time`` is interpreted as UTC per the repo-wide
    timestamp convention; tz-aware values are converted to UTC.
    """
    tz = close_time.tzinfo or UTC
    stamped = datetime.combine(event_date, close_time.replace(tzinfo=None), tzinfo=tz)
    return stamped.astimezone(UTC)


# ── the provider interface (provider_contract.md §2) ────────────────────────


class DataProvider(Protocol):
    """One contract for every provider (# arch: provider_contract.md §2;
    MP §16 capability list, one method per capability).

    All fetch methods return raw-shaped frames conforming to the
    per-family raw schemas (``FAMILY_RAW_TABLES`` →
    ``lasr.data.schemas.raw_registry``). Behavioral rules (§3): no method
    returns an empty frame to signal absence; no method mutates provider
    state; repeated identical calls return identical frames (CT-04).
    """

    def capabilities(self) -> ProviderCapabilities: ...

    # MP §16 "load" methods --------------------------------------------------
    def fetch_security_master(
        self, ids: Sequence[ProviderId] | None = None
    ) -> DataFrame: ...

    def fetch_prices(
        self,
        ids: Sequence[ProviderId],
        start: date,
        end: date,
        fields: Sequence[str] = DEFAULT_PRICE_FIELDS,
    ) -> DataFrame:
        """Default fields narrowed to the evidence-demonstrated set
        (FM-11/25; G013). open/high/low/volume are LISTED_ONLY
        (FM-12/13/14): explicit requests MUST raise
        ``FieldUnavailableError`` (CT-07) until VP-01 passes. (D-012)
        """
        ...

    def fetch_corporate_actions(
        self, ids: Sequence[ProviderId], start: date, end: date
    ) -> DataFrame: ...

    def fetch_fundamentals(
        self,
        ids: Sequence[ProviderId],
        metrics: Sequence[str],
        start: date,
        end: date,
        vintage: Literal["latest", "as_reported", "all"] = "latest",
    ) -> DataFrame:
        """``vintage="as_reported"``/``"all"`` MUST raise
        ``CapabilityError`` when ``supports_vintages`` is false — the
        A-001 guard in interface form (provider_contract.md §2 note).
        """
        ...

    def fetch_estimates(
        self, ids: Sequence[ProviderId], metrics: Sequence[str], start: date, end: date
    ) -> DataFrame: ...

    def fetch_classifications(
        self, ids: Sequence[ProviderId], schemes: Sequence[str]
    ) -> DataFrame: ...

    def fetch_market_metrics(  # ADV, multiples, technical raw material
        self, ids: Sequence[ProviderId], metrics: Sequence[str], start: date, end: date
    ) -> DataFrame: ...

    def fetch_borrow(
        self, ids: Sequence[ProviderId], start: date, end: date
    ) -> DataFrame: ...

    def fetch_universe_membership(
        self, universe_id: str, start: date, end: date
    ) -> DataFrame: ...

    def fetch_fx_rates(
        self, pairs: Sequence[tuple[str, str]], start: date, end: date
    ) -> DataFrame: ...

    def fetch_trading_calendar(
        self, calendar_id: str, start: date, end: date
    ) -> DataFrame: ...

    # MP §16 "report" methods ------------------------------------------------
    def available_history(self, family: FieldFamily) -> tuple[date | None, date | None]:
        """(earliest, latest) established; ``None`` where NOT_ESTABLISHED."""
        ...

    def field_coverage(self, family: FieldFamily) -> frozenset[str]: ...

    # revision/PIT support is reported via ``capabilities()``.
