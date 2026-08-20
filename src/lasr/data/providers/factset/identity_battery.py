"""FS011 WP2 identity acceptance battery (<=60 live requests, cache-first).

# arch: fs_goals.md FS011 charter — the WP2 acceptance battery run against
the REAL symbology API through the FS010 transport (never around it):
cross-scheme join consistency, primary/secondary distinguishability,
historical tickers, inactive/delisted probes, no silent duplicate
identities, and the EA §9 7-way mapped-or-explained accounting.

Execution discipline:

- every request is cache-first (:class:`FactSetTransport`); a re-run of a
  completed battery spends ZERO live quota;
- the battery derives its OWN budget-capped config IN-PROCESS from the
  committed trial.yaml (``configs/factset/trial.yaml`` is never edited —
  family enables are FS024-exclusive); the derived budgets keep the whole
  battery inside the charter's 60-request ceiling;
- credentials may be parsed from a local credential file IN-PROCESS
  (user authorization 2026-08-17): values go into the environ mapping
  handed to ``build_transport`` and are NEVER printed/logged/persisted;
- the battery id spec is a deterministic, documented constant
  (:data:`DEFAULT_BATTERY_SPEC`) — public reference identifiers only;
  callers may substitute their own spec (configuration-driven);
- the report (statuses/counts + vendor evidence) lands under
  ``<FACTSET_TRIAL_DATA_ROOT>/runs/<run_id>/`` — outside git.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from lasr.data.providers.factset.config import (
    EndpointPolicy,
    FactSetTrialConfig,
    load_trial_config,
    trial_config_hash,
)
from lasr.data.providers.factset.errors import FactSetConfigError
from lasr.data.providers.factset.http import HttpSender
from lasr.data.providers.factset.identity import (
    AccountingCategory,
    DuplicateIdentityError,
    FactSetIdentityError,
    IdAccounting,
    IdentifierScheme,
    IdentityMap,
    TypedIdentifier,
    merge_accounting,
)
from lasr.data.providers.factset.run_manifest import (
    build_run_manifest,
    write_run_manifest,
)
from lasr.data.providers.factset.sanitize import (
    ENV_API_KEY,
    ENV_USERNAME,
    Sanitizer,
    resolve_auth,
    validate_trial_data_root,
)
from lasr.data.providers.factset.symbology_adapter import (
    CurrentResolution,
    SymbologyAdapter,
    account_key,
)
from lasr.data.providers.factset.transport import build_transport

__all__ = [
    "DEFAULT_BATTERY_SPEC",
    "BatterySpec",
    "CheckResult",
    "JoinExpectation",
    "TickerChangeProbe",
    "load_credentials_file",
    "run_identity_battery",
]

#: Charter ceiling for the whole battery (fs_goals.md FS011).
MAX_BATTERY_LIVE_REQUESTS = 60


@dataclass(frozen=True)
class JoinExpectation:
    """Two typed roads that must reach the SAME fsymSecurityId."""

    left: TypedIdentifier
    right: TypedIdentifier


@dataclass(frozen=True)
class TickerChangeProbe:
    """A documented ticker change: the fsym behind ``current_ticker_region``
    must show ``old_ticker_region`` at ``as_of_old`` and the current one at
    ``as_of_new`` (WP2: historical tickers resolve correctly)."""

    current_ticker_region: str
    old_ticker_region: str
    as_of_old: date
    as_of_new: date


@dataclass(frozen=True)
class BatterySpec:
    """Deterministic battery inputs (public reference identifiers only)."""

    active_ticker_regions: tuple[str, ...]
    inactive_ticker_regions: tuple[str, ...]
    cusips: tuple[str, ...]
    isins: tuple[str, ...]
    sedols: tuple[str, ...]
    join_expectations: tuple[JoinExpectation, ...]
    share_class_pairs: tuple[tuple[str, str], ...]
    ticker_change_probes: tuple[TickerChangeProbe, ...]


#: Public reference identifiers (documented, hand-checked):
#: AAPL CUSIP 037833100 / ISIN US0378331005 / SEDOL 2046251;
#: MSFT CUSIP 594918104 / ISIN US5949181045 / SEDOL 2588173;
#: GOOG/GOOGL = one issuer, two share classes (primary/secondary probe);
#: META traded as FB-US until 2022-06-08, META-US since 2022-06-09;
#: TWTR (delisted 2022), AABA (dissolved 2019) = inactive probes;
#: DELL (delisted 2013, relisted 2018) = relisting probe.
DEFAULT_BATTERY_SPEC = BatterySpec(
    active_ticker_regions=(
        "AAPL-US",
        "FDS-US",
        "GOOG-US",
        "GOOGL-US",
        "IBM-US",
        "META-US",
        "MSFT-US",
        "NVDA-US",
    ),
    inactive_ticker_regions=("AABA-US", "DELL-US", "TWTR-US"),
    cusips=("037833100", "594918104"),
    isins=("US0378331005", "US5949181045"),
    sedols=("2046251", "2588173"),
    join_expectations=(
        JoinExpectation(
            left=TypedIdentifier(IdentifierScheme.CUSIP, "037833100"),
            right=TypedIdentifier(IdentifierScheme.TICKER_REGION, "AAPL-US"),
        ),
        JoinExpectation(
            left=TypedIdentifier(IdentifierScheme.ISIN, "US0378331005"),
            right=TypedIdentifier(IdentifierScheme.TICKER_REGION, "AAPL-US"),
        ),
        JoinExpectation(
            left=TypedIdentifier(IdentifierScheme.SEDOL, "2046251"),
            right=TypedIdentifier(IdentifierScheme.TICKER_REGION, "AAPL-US"),
        ),
        JoinExpectation(
            left=TypedIdentifier(IdentifierScheme.CUSIP, "594918104"),
            right=TypedIdentifier(IdentifierScheme.TICKER_REGION, "MSFT-US"),
        ),
    ),
    share_class_pairs=(("GOOG-US", "GOOGL-US"),),
    ticker_change_probes=(
        TickerChangeProbe(
            current_ticker_region="META-US",
            old_ticker_region="FB-US",
            as_of_old=date(2021, 6, 30),
            as_of_new=date(2023, 6, 30),
        ),
    ),
)


@dataclass(frozen=True)
class CheckResult:
    """One WP2 acceptance check: PASS / FAIL / UNRESOLVED + evidence."""

    name: str
    status: str
    detail: dict[str, object]

    def as_record(self) -> dict[str, object]:
        return {"name": self.name, "status": self.status, "detail": self.detail}


# ── credentials (user authorization 2026-08-17) ─────────────────────────


def load_credentials_file(path: Path) -> dict[str, str]:
    """Parse ``Username:`` / ``API Key:`` lines into env-var additions.

    IN-PROCESS ONLY: returned values are merged into the environ mapping
    handed to ``build_transport`` and must never be printed, logged, or
    written anywhere. The file itself stays outside the repository.
    """
    if not path.is_file():
        raise FactSetConfigError(f"credentials file not found: {path}")
    username = ""
    api_key = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" not in line:
            continue
        label, _, value = line.partition(":")
        label_norm = label.strip().lower()
        if label_norm == "username":
            username = value.strip()
        elif label_norm in ("api key", "apikey", "api_key"):
            api_key = value.strip()
    if not username or not api_key:
        raise FactSetConfigError(
            "credentials file lacks 'Username:' and/or 'API Key:' lines"
            " (labels only in this message; values are never logged)"
        )
    return {ENV_USERNAME: username, ENV_API_KEY: api_key}


# ── battery config derivation (trial.yaml is never edited) ──────────────


def derive_battery_config(
    base: FactSetTrialConfig, *, live: bool
) -> FactSetTrialConfig:
    """Budget-capped in-process derivation of the committed trial config.

    Splits the 60-request charter ceiling across the two symbology
    endpoints (30 + 30) and raises the shared daily cap to the ceiling
    for the battery run. Family ENABLES are untouched (FS024-exclusive);
    only the already-enabled symbology family's endpoint budgets change.
    """
    symbology = base.family("symbology")
    if not symbology.enabled:
        raise FactSetConfigError(
            "symbology family is not enabled in the trial config; FS011"
            " cannot enable families (FS024-exclusive ownership)"
        )
    per_endpoint = MAX_BATTERY_LIVE_REQUESTS // 2
    endpoints = (
        EndpointPolicy(
            endpoint="/identifier-resolution",
            verb="POST",
            max_live_requests=per_endpoint,
        ),
        EndpointPolicy(
            endpoint="/historical-identifier-resolution",
            verb="POST",
            max_live_requests=per_endpoint,
        ),
    )
    families = dict(base.families)
    families["symbology"] = symbology.model_copy(update={"endpoints": endpoints})
    return base.model_copy(
        update={
            "transport": base.transport.model_copy(
                update={
                    "live": live,
                    "max_live_calls_per_day": MAX_BATTERY_LIVE_REQUESTS,
                }
            ),
            "families": families,
        }
    )


# ── battery ──────────────────────────────────────────────────────────────


def run_identity_battery(
    *,
    config_path: Path,
    environ: Mapping[str, str],
    repo_root: Path,
    code_revision: str,
    now: datetime,
    spec: BatterySpec = DEFAULT_BATTERY_SPEC,
    run_id: str = "fs011-identity-battery",
    sender: HttpSender | None = None,
    cache_root: Path | None = None,
    force_refresh: bool = False,
) -> dict[str, object]:
    """Execute the WP2 battery; returns the value-free summary mapping.

    ``cache_root`` set → REPLAY mode (tests / free re-runs without a data
    root); otherwise LIVE mode is requested and still passes through every
    FS010 gate (env consent, kill switches, data-root validation, budgets).
    ``force_refresh=True`` re-attempts past cached entitlement evidence
    after entitlements are fixed (D-020(d)); it also bypasses success
    caches, so it re-spends live quota — still budget-capped.
    """
    base = load_trial_config(config_path)
    live = cache_root is None
    config = derive_battery_config(base, live=live)
    sanitizer = resolve_auth(environ).sanitizer() if live else Sanitizer(())
    transport = build_transport(
        config=config,
        environ=environ,
        repo_root=repo_root,
        cache_root=cache_root,
        sender=sender,
    )
    adapter = SymbologyAdapter(transport)
    started = now

    accountings: list[IdAccounting] = []
    checks: list[CheckResult] = []

    # Pass 1 — active universe: tickerRegion → all four fsym levels
    # (seed_securities = resolve_current with FSYM_OUTPUT_TYPES).
    active_ids = [
        TypedIdentifier(IdentifierScheme.TICKER_REGION, t)
        for t in spec.active_ticker_regions
    ]
    seeds_active, active = adapter.seed_securities(
        active_ids, force_refresh=force_refresh
    )
    accountings.append(active.accounting)
    checks.append(_check_active_resolution(spec, active))
    checks.append(_check_share_classes(spec, active))

    # Pass 2 — inactive/delisted probes (separate request: a dead id must
    # never be able to poison the active chunk's outcome).
    inactive_ids = [
        TypedIdentifier(IdentifierScheme.TICKER_REGION, t)
        for t in spec.inactive_ticker_regions
    ]
    seeds_inactive, inactive = adapter.seed_securities(
        inactive_ids, force_refresh=force_refresh
    )
    accountings.append(inactive.accounting)
    checks.append(_check_inactive_probes(spec, inactive))

    # Pass 3 — market-id schemes (typed; subscription-gated types are
    # FS-VQ-02 evidence when they refuse).
    scheme_results: dict[str, CurrentResolution] = {}
    for scheme, values in (
        (IdentifierScheme.CUSIP, spec.cusips),
        (IdentifierScheme.ISIN, spec.isins),
        (IdentifierScheme.SEDOL, spec.sedols),
    ):
        if not values:
            continue
        result = adapter.resolve_current(
            [TypedIdentifier(scheme, v) for v in values],
            output_symbol_types=("fsymSecurityId",),
            force_refresh=force_refresh,
        )
        scheme_results[scheme.value] = result
        accountings.append(result.accounting)
    checks.append(_check_join_consistency(spec, active, scheme_results))

    # Pass 4 — identity map hydration from the ALREADY-RESOLVED seeds
    # (zero re-seeding requests; one historical full-history request).
    identity_map = IdentityMap()
    try:
        identity_map, hydrate_accounting, _ = adapter.hydrate_identity_map(
            [*seeds_active, *seeds_inactive], force_refresh=force_refresh
        )
        accountings.append(hydrate_accounting)
        checks.append(_check_identity_map(identity_map, hydrate_accounting))
    except (DuplicateIdentityError, FactSetIdentityError) as exc:
        checks.append(
            CheckResult(
                name="no_silent_duplicate_identities",
                status="FAIL",
                detail={"error": str(exc)},
            )
        )

    # Pass 5 — historical ticker changes (full history + asOf straddles).
    for probe in spec.ticker_change_probes:
        probe_check, probe_accountings = _run_ticker_change_probe(
            adapter, active, identity_map, probe, force_refresh=force_refresh
        )
        checks.append(probe_check)
        accountings.extend(probe_accountings)

    seven_way = merge_accounting(accountings)
    total_accounted = sum(seven_way.values())
    checks.append(
        CheckResult(
            name="seven_way_accounting",
            status="PASS" if total_accounted > 0 else "FAIL",
            detail={
                "categories": seven_way,
                "total_accounted": total_accounted,
                "unexplained": 0,  # verify_complete() raised otherwise
            },
        )
    )

    within_budget = transport.stats.live_calls <= MAX_BATTERY_LIVE_REQUESTS
    checks.append(
        CheckResult(
            name="live_budget",
            status="PASS" if within_budget else "FAIL",
            detail={
                "live_calls": transport.stats.live_calls,
                "cache_hits": transport.stats.cache_hits,
                "ceiling": MAX_BATTERY_LIVE_REQUESTS,
            },
        )
    )

    report: dict[str, object] = {
        "run_id": run_id,
        "battery": "FS011 WP2 identity acceptance",
        "config_hash": trial_config_hash(config),
        "code_revision": code_revision,
        "started": started.astimezone(UTC).isoformat(),
        "mode": "live" if live else "replay",
        "checks": [c.as_record() for c in checks],
        "seven_way_accounting": seven_way,
        "live_calls": transport.stats.live_calls,
        "cache_hits": transport.stats.cache_hits,
        "errors": transport.stats.errors,
        "entitlement_results": dict(transport.stats.entitlement_results),
        "overall": _overall(checks),
    }

    data_root = validate_trial_data_root(environ, repo_root=repo_root, require=False)
    if data_root is not None:
        manifest = build_run_manifest(
            run_id=run_id,
            config=config,
            code_revision=code_revision,
            stats=transport.stats,
            environ=environ,
            started=started,
            finished=datetime.now(UTC),
            notes=f"FS011 identity battery; overall={report['overall']}",
        )
        write_run_manifest(manifest, runs_root=data_root / "runs", sanitizer=sanitizer)
        report_path = data_root / "runs" / run_id / "fs011_identity_battery.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(
                sanitizer.clean_tree(dict(report)),
                sort_keys=True,
                indent=1,
                ensure_ascii=True,
            ),
            encoding="utf-8",
        )
    return report


def _overall(checks: list[CheckResult]) -> str:
    statuses = {c.status for c in checks}
    if "FAIL" in statuses:
        return "FAIL"
    if "UNRESOLVED" in statuses:
        return "PASS_WITH_UNRESOLVED"
    return "PASS"


# ── individual checks ────────────────────────────────────────────────────


def _fsym_security(
    resolution: CurrentResolution, identifier: TypedIdentifier
) -> str | None:
    key = account_key(identifier)
    if (
        resolution.accounting.category_of(key)
        is not AccountingCategory.SUCCESSFULLY_RETRIEVED
    ):
        return None
    outputs = {k.lower(): v for k, v in resolution.outputs_for(identifier).items()}
    return outputs.get("fsymsecurityid")


def _check_active_resolution(
    spec: BatterySpec, active: CurrentResolution
) -> CheckResult:
    resolved = 0
    missing: list[str] = []
    for ticker in spec.active_ticker_regions:
        identifier = TypedIdentifier(IdentifierScheme.TICKER_REGION, ticker)
        if _fsym_security(active, identifier) is not None:
            resolved += 1
        else:
            missing.append(ticker)
    return CheckResult(
        name="active_universe_resolves_to_fsym",
        status="PASS" if not missing else "FAIL",
        detail={
            "requested": len(spec.active_ticker_regions),
            "resolved_with_fsym_security": resolved,
            "unresolved": missing,
        },
    )


def _check_share_classes(spec: BatterySpec, active: CurrentResolution) -> CheckResult:
    """Primary/secondary distinguishability: one issuer's share classes
    share the ENTITY id but keep distinct security/regional/listing ids."""
    outcomes: list[dict[str, object]] = []
    status = "PASS"
    for left_ticker, right_ticker in spec.share_class_pairs:
        left = TypedIdentifier(IdentifierScheme.TICKER_REGION, left_ticker)
        right = TypedIdentifier(IdentifierScheme.TICKER_REGION, right_ticker)
        try:
            lo = {k.lower(): v for k, v in active.outputs_for(left).items()}
            ro = {k.lower(): v for k, v in active.outputs_for(right).items()}
        except FactSetIdentityError:
            status = "UNRESOLVED"
            outcomes.append(
                {"pair": [left_ticker, right_ticker], "outcome": "unresolved"}
            )
            continue
        same_entity = lo.get("fsymentityid") is not None and lo.get(
            "fsymentityid"
        ) == ro.get("fsymentityid")
        distinct_security = (
            lo.get("fsymsecurityid") is not None
            and ro.get("fsymsecurityid") is not None
            and lo.get("fsymsecurityid") != ro.get("fsymsecurityid")
        )
        distinct_listing = lo.get("fsymlistingid") != ro.get("fsymlistingid")
        ok = same_entity and distinct_security and distinct_listing
        if not ok:
            status = "FAIL"
        outcomes.append(
            {
                "pair": [left_ticker, right_ticker],
                "same_entity": same_entity,
                "distinct_security": distinct_security,
                "distinct_listing": distinct_listing,
            }
        )
    return CheckResult(
        name="share_classes_distinguishable",
        status=status,
        detail={"pairs": outcomes},
    )


def _check_inactive_probes(
    spec: BatterySpec, inactive: CurrentResolution
) -> CheckResult:
    """U-7 probe: are delisted/inactive ids still resolvable via the
    CURRENT endpoint? Measured, never assumed (§5.3)."""
    per_id: dict[str, str] = {}
    resolved = 0
    for ticker in spec.inactive_ticker_regions:
        identifier = TypedIdentifier(IdentifierScheme.TICKER_REGION, ticker)
        fsym = _fsym_security(inactive, identifier)
        category = inactive.accounting.category_of(account_key(identifier))
        per_id[ticker] = f"{category.value}; fsym={'yes' if fsym else 'no'}"
        if fsym is not None:
            resolved += 1
    return CheckResult(
        name="inactive_delisted_resolution_probe",
        status="PASS" if resolved > 0 else "UNRESOLVED",
        detail={
            "requested": len(spec.inactive_ticker_regions),
            "resolved_with_fsym_security": resolved,
            "per_id": per_id,
            "note": (
                "U-7 evidence: current-endpoint resolvability of dead ids;"
                " UNRESOLVED (not FAIL) when none resolve — dead-universe"
                " seeding then requires fsym-bearing surfaces (§5.2)"
            ),
        },
    )


def _check_join_consistency(
    spec: BatterySpec,
    active: CurrentResolution,
    scheme_results: Mapping[str, CurrentResolution],
) -> CheckResult:
    """Cross-scheme join consistency: every typed road to one security
    reaches the same fsymSecurityId. Entitlement refusals downgrade to
    UNRESOLVED (FS-VQ-02 evidence), never silently pass."""
    outcomes: list[dict[str, object]] = []
    status = "PASS"
    for expectation in spec.join_expectations:
        left_res = scheme_results.get(expectation.left.scheme.value)
        row: dict[str, object] = {
            "left": account_key(expectation.left),
            "right": account_key(expectation.right),
        }
        if left_res is None:
            status = "UNRESOLVED"
            row["outcome"] = "left scheme not exercised"
            outcomes.append(row)
            continue
        left_key = account_key(expectation.left)
        left_category = left_res.accounting.category_of(left_key)
        if left_category is AccountingCategory.NOT_ENTITLED:
            if status == "PASS":
                status = "UNRESOLVED"
            row["outcome"] = "not_entitled (FS-VQ-02 evidence)"
            outcomes.append(row)
            continue
        left_fsym = _fsym_security(left_res, expectation.left)
        right_fsym = _fsym_security(active, expectation.right)
        if left_fsym is None or right_fsym is None:
            status = "FAIL"
            row["outcome"] = (
                f"unjoined: left={'null' if left_fsym is None else 'ok'},"
                f" right={'null' if right_fsym is None else 'ok'}"
            )
        elif left_fsym == right_fsym:
            row["outcome"] = "consistent"
        else:
            status = "FAIL"
            row["outcome"] = "MISMATCH: two roads reached different fsyms"
        outcomes.append(row)
    return CheckResult(
        name="cross_scheme_join_consistency",
        status=status,
        detail={"expectations": outcomes},
    )


def _check_identity_map(
    identity_map: IdentityMap, hydration_accounting: IdAccounting
) -> CheckResult:
    hydration_summary = hydration_accounting.summary()
    historical_not_entitled = hydration_summary[AccountingCategory.NOT_ENTITLED.value]
    open_ended = sum(1 for i in identity_map.intervals if i.end_date_raw is None)
    return CheckResult(
        name="no_silent_duplicate_identities",
        # Current fsym seeds were still checked for duplicate ownership, but
        # an endpoint-level historical entitlement refusal leaves the dated
        # outward claims unobserved. That is an evidence gap, not a content
        # mismatch and therefore cannot honestly be called either PASS or
        # FAIL (F-010 follow-up live evidence, 2026-08-18).
        status="UNRESOLVED" if historical_not_entitled else "PASS",
        detail={
            "securities_seeded": len(identity_map.seeds),
            "identifier_intervals": len(identity_map.intervals),
            "open_ended_intervals_verbatim": open_ended,
            "historical_hydration_accounting": hydration_summary,
            "note": (
                "map build raises DuplicateIdentityError on overlapping"
                " claims; open endDate stored verbatim (U-7c, no closure"
                " convention guessed); endpoint-level not_entitled leaves"
                " the historical duplicate check UNRESOLVED"
            ),
        },
    )


def _run_ticker_change_probe(
    adapter: SymbologyAdapter,
    active: CurrentResolution,
    identity_map: IdentityMap,
    probe: TickerChangeProbe,
    *,
    force_refresh: bool = False,
) -> tuple[CheckResult, list[IdAccounting]]:
    """Historical tickers resolve correctly (WP2): the fsym behind the
    current ticker must carry the OLD ticker in full history and resolve
    to old/new at asOf dates straddling the change."""
    current = TypedIdentifier(
        IdentifierScheme.TICKER_REGION, probe.current_ticker_region
    )
    fsym_value = _fsym_security(active, current)
    if fsym_value is None:
        return (
            CheckResult(
                name=f"historical_ticker_change_{probe.current_ticker_region}",
                status="UNRESOLVED",
                detail={"reason": "current ticker did not resolve to a fsym"},
            ),
            [],
        )
    fsym = TypedIdentifier(IdentifierScheme.FSYM_SECURITY, fsym_value)

    # Full-history evidence from the hydrated map (zero extra requests).
    try:
        security_id = identity_map.security_id_for(fsym_value)
        history_values = {
            i.id_value
            for i in identity_map.intervals_for(security_id)
            if i.id_scheme == "ticker"
        }
    except FactSetIdentityError:
        history_values = set()

    accountings: list[IdAccounting] = []
    as_of_values: dict[str, list[str]] = {}
    as_of_categories: dict[str, str] = {}
    for as_of in (probe.as_of_old, probe.as_of_new):
        result = adapter.resolve_historical(
            [fsym],
            output_symbol_types=("tickerRegion",),
            as_of_date=as_of,
            force_refresh=force_refresh,
        )
        accountings.append(result.accounting)
        category = result.accounting.category_of(account_key(fsym))
        as_of_categories[as_of.isoformat()] = category.value
        as_of_values[as_of.isoformat()] = [
            r.value for r in result.intervals_for(fsym) if r.value is not None
        ]

    if AccountingCategory.NOT_ENTITLED.value in as_of_categories.values():
        return (
            CheckResult(
                name=f"historical_ticker_change_{probe.current_ticker_region}",
                status="UNRESOLVED",
                detail={
                    "reason": (
                        "historical endpoint not entitled; ticker-change"
                        " content was not assessed"
                    ),
                    "as_of_accounting": as_of_categories,
                    "content_assessed": False,
                },
            ),
            accountings,
        )

    old_in_history = probe.old_ticker_region in history_values
    new_in_history = probe.current_ticker_region in history_values
    old_at_old = probe.old_ticker_region in as_of_values[probe.as_of_old.isoformat()]
    new_at_new = (
        probe.current_ticker_region in as_of_values[probe.as_of_new.isoformat()]
    )
    ok = old_in_history and new_in_history and old_at_old and new_at_new
    return (
        CheckResult(
            name=f"historical_ticker_change_{probe.current_ticker_region}",
            status="PASS" if ok else "FAIL",
            detail={
                "old_ticker_in_full_history": old_in_history,
                "new_ticker_in_full_history": new_in_history,
                f"as_of_{probe.as_of_old.isoformat()}_shows_old": old_at_old,
                f"as_of_{probe.as_of_new.isoformat()}_shows_new": new_at_new,
                "full_history_ticker_count": len(history_values),
            },
        ),
        accountings,
    )


# ── CLI (reproducible invocation; prints the VALUE-FREE summary only) ────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "FS011 WP2 identity battery (cache-first; <=60 live requests;"
            " all output value-free)"
        )
    )
    parser.add_argument("--trial-config", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument(
        "--credentials-file",
        type=Path,
        default=None,
        help=(
            "optional local credential file parsed IN-PROCESS (values are"
            " never printed/logged/persisted)"
        ),
    )
    parser.add_argument("--run-id", default="fs011-identity-battery")
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help=(
            "re-attempt past cached entitlement evidence AFTER entitlements"
            " are fixed (also bypasses success caches; re-spends budget)"
        ),
    )
    parser.add_argument(
        "--replay-cache-root",
        type=Path,
        default=None,
        help="replay mode against an existing capture root (no live calls)",
    )
    args = parser.parse_args(argv)

    environ: dict[str, str] = dict(os.environ)
    if args.credentials_file is not None:
        environ.update(load_credentials_file(args.credentials_file))

    code_revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=args.repo_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    report = run_identity_battery(
        config_path=args.trial_config,
        environ=environ,
        repo_root=args.repo_root,
        code_revision=code_revision,
        now=datetime.now(UTC),
        run_id=args.run_id,
        cache_root=args.replay_cache_root,
        force_refresh=args.force_refresh,
    )
    print(json.dumps(report, sort_keys=True, indent=1, ensure_ascii=True))
    return 0 if report["overall"] != "FAIL" else 1


if __name__ == "__main__":  # pragma: no cover - thin CLI shim
    raise SystemExit(main())
