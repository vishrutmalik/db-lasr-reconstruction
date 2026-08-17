"""FS011 — identity spine: typed identifiers, minting v2, map, bridge,
7-way accounting.

Fixtures are hand-synthesized (CFC-8: never copied from spec examples).
Hash expectations are recomputed inline from the documented payload
formats so the minting policy is pinned formula-level, not
implementation-level.
"""

from __future__ import annotations

import hashlib
from datetime import date

import pytest

from lasr.core.ids import mint_security_id
from lasr.data.providers.factset.identity import (
    AccountingCategory,
    BridgeDecision,
    DuplicateIdentityError,
    FactSetIdentityError,
    IdAccounting,
    IdentifierInterval,
    IdentifierScheme,
    IdentityMap,
    SecuritySeed,
    TypedIdentifier,
    evaluate_bridge,
    merge_accounting,
    mint_security_id_v2,
    normalize_identifier_value,
)

pytestmark = pytest.mark.unit


# ── casing policy (RT-FS010-2 → FS011) ──────────────────────────────────


def test_casing_policy_strips_and_uppercases() -> None:
    assert normalize_identifier_value("  aapl-us ") == "AAPL-US"
    assert normalize_identifier_value("mh33d6-s") == "MH33D6-S"


def test_casing_policy_refuses_blank() -> None:
    with pytest.raises(FactSetIdentityError, match="empty"):
        normalize_identifier_value("   ")


def test_typed_identifier_is_canonical_after_construction() -> None:
    a = TypedIdentifier(IdentifierScheme.TICKER_REGION, "aapl-us")
    b = TypedIdentifier(IdentifierScheme.TICKER_REGION, "AAPL-US")
    assert a == b  # one logical identifier, one cache identity (RT-FS010-2)
    assert a.value == "AAPL-US"


# ── typed validation (D-020(b): declared scheme, never guessed) ─────────


@pytest.mark.parametrize(
    ("scheme", "value"),
    [
        (IdentifierScheme.CUSIP, "037833100"),
        (IdentifierScheme.ISIN, "US0378331005"),
        (IdentifierScheme.SEDOL, "2046251"),
        (IdentifierScheme.TICKER_REGION, "BRK.B-US"),
        (IdentifierScheme.TICKER_EXCHANGE, "GOOGL-NAS"),
        (IdentifierScheme.FSYM_SECURITY, "MH33D6-S"),
        (IdentifierScheme.FSYM_REGIONAL, "MH33D6-R"),
        (IdentifierScheme.FSYM_LISTING, "MH33D6-L"),
        (IdentifierScheme.FSYM_ENTITY, "000C7F-E"),
    ],
)
def test_valid_values_accepted(scheme: IdentifierScheme, value: str) -> None:
    assert TypedIdentifier(scheme, value).value == value


@pytest.mark.parametrize(
    ("scheme", "value"),
    [
        (IdentifierScheme.CUSIP, "03783310"),  # 8 chars
        (IdentifierScheme.CUSIP, "US0378331005"),  # an ISIN declared CUSIP
        (IdentifierScheme.ISIN, "0378331005US"),  # country code not leading
        (IdentifierScheme.ISIN, "US037833100X"),  # non-digit check position
        (IdentifierScheme.SEDOL, "20462510"),  # 8 chars
        (IdentifierScheme.TICKER_REGION, "AAPL"),  # no region suffix
        (IdentifierScheme.TICKER_REGION, "AAPL-12"),  # non-alpha region
        (IdentifierScheme.FSYM_SECURITY, "MH33D6S"),  # missing hyphen
        (IdentifierScheme.FSYM_SECURITY, "MH33D6-X"),  # unknown level
    ],
)
def test_mismatched_values_refused(scheme: IdentifierScheme, value: str) -> None:
    with pytest.raises(FactSetIdentityError):
        TypedIdentifier(scheme, value)


def test_fsym_level_marker_must_match_declared_scheme() -> None:
    # Declaring fsymSecurityId for a -R value is a caller bug, refused —
    # typed resolution never reinterprets levels.
    with pytest.raises(FactSetIdentityError, match="level marker mismatch"):
        TypedIdentifier(IdentifierScheme.FSYM_SECURITY, "MH33D6-R")
    with pytest.raises(FactSetIdentityError, match="level marker mismatch"):
        TypedIdentifier(IdentifierScheme.FSYM_ENTITY, "MH33D6-S")


# ── minting v2 (CE-7) — formula-level pins ───────────────────────────────


def test_mint_v2_formula_is_pinned() -> None:
    # Hand-computed: sha256("mintv2|vendor_security_perm|MH33D6-S")[:12].
    expected = hashlib.sha256(b"mintv2|vendor_security_perm|MH33D6-S").hexdigest()[:12]
    assert mint_security_id_v2("vendor_security_perm", "MH33D6-S") == f"SEC-{expected}"


def test_mint_v2_is_normalization_invariant() -> None:
    a = mint_security_id_v2("vendor_security_perm", "mh33d6-s")
    b = mint_security_id_v2(" VENDOR_SECURITY_PERM ", "  MH33D6-S ")
    assert a == b


def test_mint_v2_distinct_schemes_mint_distinct_ids() -> None:
    a = mint_security_id_v2("vendor_security_perm", "MH33D6-S")
    b = mint_security_id_v2("vendor_regional", "MH33D6-S")
    assert a != b


def test_mint_v2_domain_separated_from_v1() -> None:
    # A crafted v1 call whose fields spell the v2 payload cannot collide:
    # v1 uppercases its ticker, so its payload can never start "mintv2|".
    v2 = mint_security_id_v2("vendor_security_perm", "MH33D6-S")
    v1 = mint_security_id("mintv2", "vendor_security_perm", date(2020, 1, 1))
    assert v1 != v2
    v1_payload = "MINTV2|VENDOR_SECURITY_PERM|2020-01-01"
    assert mint_security_id("mintv2", "vendor_security_perm", date(2020, 1, 1)) == (
        "SEC-" + hashlib.sha256(v1_payload.encode()).hexdigest()[:12]
    )


def test_mint_v2_refuses_empty_inputs() -> None:
    with pytest.raises(FactSetIdentityError):
        mint_security_id_v2("", "MH33D6-S")
    with pytest.raises(FactSetIdentityError):
        mint_security_id_v2("vendor_security_perm", "  ")


# ── identity map: seed + hydrate (§5.2) ──────────────────────────────────


def _seed(fsym: str = "MH33D6-S") -> SecuritySeed:
    return SecuritySeed(
        fsym_security_id=fsym,
        fsym_entity_id="000C7F-E",
        fsym_regional_id=fsym[:-1] + "R",
        fsym_listing_id=fsym[:-1] + "L",
        name="Example Corp",
        fref_listing_exchange="NAS",
        currency="USD",
    )


def test_seed_mints_v2_and_is_idempotent() -> None:
    imap = IdentityMap()
    sid1 = imap.seed(_seed())
    sid2 = imap.seed(_seed())
    assert sid1 == sid2 == mint_security_id_v2("vendor_security_perm", "MH33D6-S")
    assert len(imap.seeds) == 1


def test_seed_normalizes_fsym_casing() -> None:
    imap = IdentityMap()
    sid = imap.seed(SecuritySeed(fsym_security_id="mh33d6-s"))
    assert sid == imap.security_id_for("MH33D6-S")


def test_hydrate_requires_seeding_first() -> None:
    imap = IdentityMap()
    interval = IdentifierInterval(
        security_id="SEC-000000000000",
        id_scheme="ticker",
        id_value="AAPL-US",
        start_date_raw="2010-01-01",
        end_date_raw=None,
        source="historical-identifier-resolution",
    )
    with pytest.raises(FactSetIdentityError, match="unseeded"):
        imap.hydrate(interval)


def test_hydrate_preserves_open_end_verbatim_u7c() -> None:
    imap = IdentityMap()
    sid = imap.seed(_seed())
    imap.hydrate(
        IdentifierInterval(
            security_id=sid,
            id_scheme="ticker",
            id_value="EXMP-US",
            start_date_raw="2012-05-31",
            end_date_raw=None,  # open interval: convention UNRESOLVED (U-7c)
            source="historical-identifier-resolution",
        )
    )
    stored = imap.intervals_for(sid)[0]
    assert stored.end_date_raw is None  # verbatim; no closure guessed
    assert stored.parsed_start() == date(2012, 5, 31)
    assert stored.parsed_end() is None


def test_recycled_ticker_two_nonoverlapping_intervals_is_legal() -> None:
    imap = IdentityMap()
    dead = imap.seed(_seed("AAAAAA-S"))
    alive = imap.seed(_seed("BBBBBB-S"))
    imap.hydrate(
        IdentifierInterval(
            security_id=dead,
            id_scheme="ticker",
            id_value="RCYC-US",
            start_date_raw="2005-01-01",
            end_date_raw="2012-06-30",
            source="historical-identifier-resolution",
        )
    )
    imap.hydrate(  # same ticker, later window, DIFFERENT security: legal
        IdentifierInterval(
            security_id=alive,
            id_scheme="ticker",
            id_value="RCYC-US",
            start_date_raw="2015-03-01",
            end_date_raw=None,
            source="historical-identifier-resolution",
        )
    )
    assert len(imap.intervals) == 2


def test_overlapping_duplicate_identity_is_typed_error() -> None:
    imap = IdentityMap()
    a = imap.seed(_seed("AAAAAA-S"))
    b = imap.seed(_seed("BBBBBB-S"))
    imap.hydrate(
        IdentifierInterval(
            security_id=a,
            id_scheme="cusip",
            id_value="037833100",
            start_date_raw="2010-01-01",
            end_date_raw=None,
            source="historical-identifier-resolution",
        )
    )
    with pytest.raises(DuplicateIdentityError, match="overlapping"):
        imap.hydrate(
            IdentifierInterval(
                security_id=b,
                id_scheme="cusip",
                id_value="037833100",
                start_date_raw="2018-01-01",
                end_date_raw=None,
                source="historical-identifier-resolution",
            )
        )


def test_identical_reassertion_is_idempotent() -> None:
    imap = IdentityMap()
    sid = imap.seed(_seed())
    row = IdentifierInterval(
        security_id=sid,
        id_scheme="isin",
        id_value="US0378331005",
        start_date_raw="2010-01-01",
        end_date_raw="2020-01-01",
        source="historical-identifier-resolution",
    )
    imap.hydrate(row)
    imap.hydrate(row)
    assert len(imap.intervals) == 1


def test_malformed_vendor_date_is_quarantined_not_repaired() -> None:
    # Eager at interval construction: verbatim storage, but a non-ISO
    # vendor date refuses immediately (quarantine, never repair).
    with pytest.raises(FactSetIdentityError, match="ISO-8601"):
        IdentifierInterval(
            security_id="SEC-000000000000",
            id_scheme="ticker",
            id_value="EXMP-US",
            start_date_raw="31/05/2012",  # not ISO-8601
            end_date_raw=None,
            source="historical-identifier-resolution",
        )


def test_seed_validates_all_fsym_levels() -> None:
    with pytest.raises(FactSetIdentityError):
        SecuritySeed(fsym_security_id="MH33D6-S", fsym_regional_id="MH33D6-S")


# ── bridge (§5.1): fsym-first with dated cross-check ─────────────────────


def test_bridge_accepts_when_dated_crosscheck_agrees() -> None:
    outcome = evaluate_bridge(
        ticker="exmp",
        exchange="nas",
        first_seen=date(2015, 1, 2),
        retrieval_date=date(2019, 6, 28),
        resolved_fsym_security_id="MH33D6-S",
        historical_ticker_regions=[
            ("EXMP-US", "2012-05-31", None),  # covers retrieval, same ticker
        ],
    )
    assert outcome.decision is BridgeDecision.BRIDGED_FSYM
    assert outcome.minting_policy == "fsym_first"
    assert outcome.security_id == mint_security_id_v2(
        "vendor_security_perm", "MH33D6-S"
    )
    # Legacy v1 id is retained as an auditable alias, never orphaned.
    assert outcome.legacy_alias_id == mint_security_id("EXMP", "NAS", date(2015, 1, 2))


def test_bridge_falls_back_when_unresolved() -> None:
    outcome = evaluate_bridge(
        ticker="EXMP",
        exchange="NAS",
        first_seen=date(2015, 1, 2),
        retrieval_date=date(2019, 6, 28),
        resolved_fsym_security_id=None,
        historical_ticker_regions=[],
    )
    assert outcome.decision is BridgeDecision.FALLBACK_NO_RESOLUTION
    assert outcome.minting_policy == "legacy_v1"
    assert outcome.security_id == mint_security_id("EXMP", "NAS", date(2015, 1, 2))


def test_bridge_falls_back_on_recycled_ticker_disagreement() -> None:
    # The drop's retrieval date predates the fsym's tenure of this ticker:
    # current resolution found the RECYCLER, not the original security.
    outcome = evaluate_bridge(
        ticker="RCYC",
        exchange="NYS",
        first_seen=date(2008, 3, 3),
        retrieval_date=date(2010, 6, 30),
        resolved_fsym_security_id="BBBBBB-S",
        historical_ticker_regions=[
            ("RCYC-US", "2015-03-01", None),  # recycler's tenure starts 2015
        ],
    )
    assert outcome.decision is BridgeDecision.FALLBACK_CROSSCHECK_DISAGREE
    assert outcome.minting_policy == "legacy_v1"
    assert outcome.fsym_security_id == "BBBBBB-S"  # evidence retained


def test_bridge_falls_back_when_crosscheck_unverifiable() -> None:
    outcome = evaluate_bridge(
        ticker="EXMP",
        exchange="NAS",
        first_seen=date(2015, 1, 2),
        retrieval_date=date(2019, 6, 28),
        resolved_fsym_security_id="MH33D6-S",
        historical_ticker_regions=[],
    )
    assert outcome.decision is BridgeDecision.FALLBACK_CROSSCHECK_UNVERIFIABLE
    assert outcome.minting_policy == "legacy_v1"


def test_bridge_ticker_match_ignores_region_suffix_and_case() -> None:
    outcome = evaluate_bridge(
        ticker="brk.b",
        exchange="NYS",
        first_seen=date(2016, 1, 4),
        retrieval_date=date(2018, 2, 1),
        resolved_fsym_security_id="CCCCCC-S",
        historical_ticker_regions=[("brk.b-us", "2010-01-01", None)],
    )
    assert outcome.decision is BridgeDecision.BRIDGED_FSYM


def test_bridge_closed_interval_boundaries_are_inclusive() -> None:
    kwargs = {
        "ticker": "EXMP",
        "exchange": "NAS",
        "first_seen": date(2015, 1, 2),
        "resolved_fsym_security_id": "MH33D6-S",
        "historical_ticker_regions": [("EXMP-US", "2012-05-31", "2019-06-28")],
    }
    on_end = evaluate_bridge(retrieval_date=date(2019, 6, 28), **kwargs)
    assert on_end.decision is BridgeDecision.BRIDGED_FSYM
    after_end = evaluate_bridge(retrieval_date=date(2019, 6, 29), **kwargs)
    assert after_end.decision is BridgeDecision.FALLBACK_CROSSCHECK_DISAGREE


# ── 7-way accounting (EA §9) ─────────────────────────────────────────────


def test_accounting_has_exactly_seven_categories() -> None:
    assert {c.value for c in AccountingCategory} == {
        "successfully_retrieved",
        "validly_empty",
        "ineligible_identifier",
        "not_covered",
        "not_entitled",
        "invalid_request",
        "vendor_api_failure",
    }


def test_every_id_mapped_or_explained() -> None:
    acc = IdAccounting(requested=("AAPL-US", "MSFT-US", "ZZZZ-US"))
    acc.assign("AAPL-US", AccountingCategory.SUCCESSFULLY_RETRIEVED, "resolved")
    acc.assign("MSFT-US", AccountingCategory.SUCCESSFULLY_RETRIEVED, "resolved")
    with pytest.raises(FactSetIdentityError, match="silent loss"):
        acc.verify_complete()
    acc.assign("ZZZZ-US", AccountingCategory.NOT_COVERED, "no vendor row")
    acc.verify_complete()
    assert acc.summary()["successfully_retrieved"] == 2
    assert acc.summary()["not_covered"] == 1
    assert acc.summary()["not_entitled"] == 0  # zeros present for all 7
    assert len(acc.summary()) == 7


def test_accounting_refuses_double_and_foreign_assignment() -> None:
    acc = IdAccounting(requested=("AAPL-US",))
    acc.assign("AAPL-US", AccountingCategory.SUCCESSFULLY_RETRIEVED, "resolved")
    with pytest.raises(FactSetIdentityError, match="already accounted"):
        acc.assign("AAPL-US", AccountingCategory.NOT_COVERED, "again")
    with pytest.raises(FactSetIdentityError, match="not in the requested set"):
        acc.assign("MSFT-US", AccountingCategory.NOT_COVERED, "foreign")


def test_accounting_requires_reason_and_dedup() -> None:
    acc = IdAccounting(requested=("AAPL-US",))
    with pytest.raises(FactSetIdentityError, match="reason"):
        acc.assign("AAPL-US", AccountingCategory.NOT_COVERED, "  ")
    with pytest.raises(FactSetIdentityError, match="deduplicated"):
        IdAccounting(requested=("AAPL-US", "AAPL-US"))


def test_merge_accounting_aggregates_and_gates_completeness() -> None:
    a = IdAccounting(requested=("AAPL-US",))
    a.assign("AAPL-US", AccountingCategory.SUCCESSFULLY_RETRIEVED, "resolved")
    b = IdAccounting(requested=("TWTR-US",))
    b.assign("TWTR-US", AccountingCategory.NOT_COVERED, "delisted; no row")
    merged = merge_accounting([a, b])
    assert merged["successfully_retrieved"] == 1
    assert merged["not_covered"] == 1
    incomplete = IdAccounting(requested=("GOOG-US",))
    with pytest.raises(FactSetIdentityError, match="silent loss"):
        merge_accounting([incomplete])
