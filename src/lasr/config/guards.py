"""Spec guards: per-version structural constraints, applied at load.

# arch: config_system.md §4 — "a frozen guard registry ... each guard citing
its CR. Guards are what make 'config keeps them separately selectable'
enforceable." Guards run on the RESOLVED spec (after ``inherits`` merging,
config_system.md §8): an inherited value that violates a child guard is a
load error.

Beyond the §4 table this registry pins:

- ``selection.type == "min_z"`` for the ``lasr_2014`` family (G015
  verification finding N-9: CR-008 assigns argmin-Z there too);
- per-version target horizons (CR-006: "per-version constants, never
  shared defaults");
- hedge selection metric/grain per generation (CR-003's three rules);
- ``inherits`` legality (config_system.md §8 pairs only);
- execution modes where version-defining (CR-018: lasr_hf next_open,
  nlasr_2020 t+2 MOC).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from types import MappingProxyType

from lasr.config.ensemble import HedgeBackcastComponent, TrailingWindowComponent
from lasr.config.errors import GuardViolation, SpecGuardError
from lasr.config.version_spec import VersionSpec
from lasr.core.timing import ExecutionMode

__all__ = [
    "SPEC_GUARDS",
    "enforce_guards",
    "run_guards",
]

Guard = Callable[[VersionSpec], tuple[GuardViolation, ...]]

#: CI-013 target families: the only legal horizon/grid pairs.
_LEGAL_HORIZON_GRID: frozenset[tuple[str, str]] = frozenset(
    {("1M", "month_end"), ("3M", "month_end"), ("1W", "weekly"), ("4W", "weekly")}
)

#: config_system.md §8: the only legal inheritance edges.
_LEGAL_INHERITS: Mapping[str, str | None] = MappingProxyType(
    {
        "nlasr_2012": None,
        "nlasr2_2013": None,
        "lasr_2014": None,
        "lasr_hc_2014": "lasr_2014",
        "lasr_hf_2014": "lasr_2014",
        "nlasr_2020": None,
        "modernized": "nlasr_2020",
    }
)


def _violation(
    spec: VersionSpec, rule: str, basis: str, message: str
) -> GuardViolation:
    return GuardViolation(
        version_id=spec.version_id, rule=rule, basis=basis, message=message
    )


def _guard_fractions_sum(spec: VersionSpec) -> tuple[GuardViolation, ...]:
    """Label fractions partition the cross-section (CI-016)."""
    f = spec.labels.fractions.value
    total = f.top + f.middle + f.bottom
    if abs(total - 1.0) > 1e-9:
        return (
            _violation(
                spec,
                "labels_fractions_sum",
                "CI-016",
                f"label fractions must sum to 1.0, got {total!r}",
            ),
        )
    return ()


def _guard_horizon_grid(spec: VersionSpec) -> tuple[GuardViolation, ...]:
    """Horizon/grid pair must be a legal CI-013 target family."""
    pair = (spec.target.horizon.value, spec.target.grid.value)
    if pair not in _LEGAL_HORIZON_GRID:
        return (
            _violation(
                spec,
                "horizon_grid_pair",
                "CI-013",
                f"illegal horizon/grid pair {pair!r}; legal families: "
                f"{sorted(_LEGAL_HORIZON_GRID)}",
            ),
        )
    return ()


def _guard_inherits(spec: VersionSpec) -> tuple[GuardViolation, ...]:
    """Inheritance edges mirror the spec docs (config_system.md §8)."""
    expected = _LEGAL_INHERITS[spec.version_id]
    if spec.inherits != expected:
        return (
            _violation(
                spec,
                "inherits_legality",
                "config_system.md §8",
                f"version {spec.version_id!r} must declare inherits={expected!r}, "
                f"got {spec.inherits!r}",
            ),
        )
    return ()


def _hedges(spec: VersionSpec) -> tuple[HedgeBackcastComponent, ...]:
    return tuple(
        c for c in spec.ensemble.components if isinstance(c, HedgeBackcastComponent)
    )


def _guard_horizon(horizon: str, basis: str) -> Guard:
    def guard(spec: VersionSpec) -> tuple[GuardViolation, ...]:
        if spec.target.horizon.value != horizon:
            return (
                _violation(
                    spec,
                    "target_horizon",
                    basis,
                    f"target.horizon must be {horizon!r} for "
                    f"{spec.version_id!r}, got {spec.target.horizon.value!r}",
                ),
            )
        return ()

    return guard


def _guard_kernel(kernel_type: str, basis: str) -> Guard:
    def guard(spec: VersionSpec) -> tuple[GuardViolation, ...]:
        if spec.kernel.type != kernel_type:
            return (
                _violation(
                    spec,
                    "kernel_type",
                    basis,
                    f"kernel.type must be {kernel_type!r} for "
                    f"{spec.version_id!r}, got {spec.kernel.type!r}",
                ),
            )
        return ()

    return guard


def _guard_selection(allowed: frozenset[str], basis: str) -> Guard:
    def guard(spec: VersionSpec) -> tuple[GuardViolation, ...]:
        if spec.selection.type not in allowed:
            return (
                _violation(
                    spec,
                    "selection_type",
                    basis,
                    f"selection.type must be in {sorted(allowed)} for "
                    f"{spec.version_id!r}, got {spec.selection.type!r}",
                ),
            )
        return ()

    return guard


def _guard_execution_mode(mode: ExecutionMode, basis: str) -> Guard:
    def guard(spec: VersionSpec) -> tuple[GuardViolation, ...]:
        if spec.execution.mode.value is not mode:
            return (
                _violation(
                    spec,
                    "execution_mode",
                    basis,
                    f"execution.mode must be {mode.value!r} for "
                    f"{spec.version_id!r}, got {spec.execution.mode.value.value!r}",
                ),
            )
        return ()

    return guard


def _guard_p1_roster(spec: VersionSpec) -> tuple[GuardViolation, ...]:
    """nlasr_2012: exactly 3 components; a hedge selector fails the build
    (CR-002: "never import the hedge component into the P1-era spec")."""
    violations: list[GuardViolation] = []
    if _hedges(spec):
        violations.append(
            _violation(
                spec,
                "no_hedge_component",
                "CR-002",
                "nlasr_2012 must fail to build if a hedge selector is supplied",
            )
        )
    if len(spec.ensemble.components) != 3:
        violations.append(
            _violation(
                spec,
                "component_count",
                "CR-002",
                f"nlasr_2012 has exactly 3 components (P1-19/20/21), got "
                f"{len(spec.ensemble.components)}",
            )
        )
    return tuple(violations)


def _guard_four_with_hedge(metric: str, grain: str, basis: str) -> Guard:
    """4 components including exactly one hedge with the version's CR-003
    selection rule and grain."""

    def guard(spec: VersionSpec) -> tuple[GuardViolation, ...]:
        violations: list[GuardViolation] = []
        if len(spec.ensemble.components) != 4:
            violations.append(
                _violation(
                    spec,
                    "component_count",
                    basis,
                    f"{spec.version_id!r} has exactly 4 components (CR-002), "
                    f"got {len(spec.ensemble.components)}",
                )
            )
        hedges = _hedges(spec)
        if len(hedges) != 1:
            violations.append(
                _violation(
                    spec,
                    "hedge_component_required",
                    basis,
                    f"{spec.version_id!r} requires exactly one hedge component, "
                    f"got {len(hedges)}",
                )
            )
        else:
            hedge = hedges[0]
            if hedge.selection_metric.value != metric:
                violations.append(
                    _violation(
                        spec,
                        "hedge_selection_metric",
                        basis,
                        f"hedge selection_metric must be {metric!r}, got "
                        f"{hedge.selection_metric.value!r}",
                    )
                )
            if hedge.grain.value != grain:
                violations.append(
                    _violation(
                        spec,
                        "hedge_grain",
                        basis,
                        f"hedge grain must be {grain!r}, got {hedge.grain.value!r}",
                    )
                )
        return tuple(violations)

    return guard


def _guard_p4_roster(spec: VersionSpec) -> tuple[GuardViolation, ...]:
    """nlasr_2020 family roster: 5y + 1y trailing, seasonal-10y, hedge-pnl
    (config_system.md §4 row; E-P4-10/11)."""
    violations: list[GuardViolation] = []
    counts = {
        "trailing_window": 0,
        "seasonal_same_month": 0,
        "previous_period": 0,
        "hedge_backcast": 0,
    }
    for c in spec.ensemble.components:
        counts[c.type] += 1
    expected = {
        "trailing_window": 2,
        "seasonal_same_month": 1,
        "previous_period": 0,
        "hedge_backcast": 1,
    }
    if counts != expected:
        violations.append(
            _violation(
                spec,
                "p4_component_structure",
                "CR-002 / E-P4-10",
                f"components must be two trailing windows (5y/1y), one "
                f"seasonal and one hedge; got counts {counts}",
            )
        )
    trailing = [
        c for c in spec.ensemble.components if isinstance(c, TrailingWindowComponent)
    ]
    if len(trailing) == 2 and trailing[0].periods.value == trailing[1].periods.value:
        violations.append(
            _violation(
                spec,
                "p4_trailing_windows_distinct",
                "E-P4-10",
                "the long-term (5y) and short-term (1y) trailing windows must "
                "have distinct lengths",
            )
        )
    return tuple(violations)


def _guard_no_turnover_cap(spec: VersionSpec) -> tuple[GuardViolation, ...]:
    """nlasr_2020 family: no turnover constraint may be added (CR-014)."""
    limit = spec.portfolio.turnover_limit_one_way_monthly.value
    if limit is not None:
        return (
            _violation(
                spec,
                "no_turnover_cap",
                "CR-014",
                f"{spec.version_id!r} must NOT add a turnover cap "
                f"(observed turnover is an acceptance observable); got {limit!r}",
            ),
        )
    return ()


def _guard_neutralization_none(spec: VersionSpec) -> tuple[GuardViolation, ...]:
    """nlasr_2012: no signal-level neutralization exists (CR-004)."""
    if spec.neutralization.mechanism.value != "none":
        return (
            _violation(
                spec,
                "neutralization_none",
                "CR-004",
                "nlasr_2012 has no signal-level neutralization scheme; got "
                f"mechanism {spec.neutralization.mechanism.value!r}",
            ),
        )
    return ()


_UNIVERSAL_GUARDS: tuple[Guard, ...] = (
    _guard_fractions_sum,
    _guard_horizon_grid,
    _guard_inherits,
)

_MIN_Z_ONLY = frozenset({"min_z"})
_MAX_WCORR_ONLY = frozenset({"max_weighted_corr"})
#: modernized: both objectives available and benchmarked (M-07).
_MODERNIZED_SELECTION = frozenset({"max_weighted_corr", "min_z"})

#: The frozen per-version guard registry (config_system.md §4).
SPEC_GUARDS: Mapping[str, tuple[Guard, ...]] = MappingProxyType(
    {
        "nlasr_2012": (
            _guard_p1_roster,
            _guard_neutralization_none,
            _guard_kernel("piecewise_constant", "CR-007"),
            _guard_selection(_MIN_Z_ONLY, "CR-008"),
            _guard_horizon("1M", "CR-006 (P1-03)"),
        ),
        "nlasr2_2013": (
            _guard_four_with_hedge("backcast_ic_threshold", "month", "CR-002/CR-003"),
            _guard_kernel("piecewise_constant", "CR-007"),
            _guard_selection(_MIN_Z_ONLY, "CR-008"),
            _guard_horizon("1M", "CR-006 (E-P2-16)"),
        ),
        "lasr_2014": (
            _guard_four_with_hedge("bottom_half_model_ic", "month", "CR-002/CR-003"),
            _guard_kernel("piecewise_linear_interp", "CR-007"),
            _guard_selection(_MIN_Z_ONLY, "CR-008 (G015 N-9 pin)"),
            _guard_horizon("1M", "CR-006 (P3 pp.5-6)"),
        ),
        "lasr_hc_2014": (
            _guard_four_with_hedge("bottom_half_model_ic", "month", "CR-002/CR-003"),
            _guard_kernel("piecewise_linear_interp", "CR-007"),
            _guard_selection(_MIN_Z_ONLY, "CR-008 (G015 N-9 pin)"),
            _guard_horizon("3M", "CR-006 (P3-02)"),
        ),
        "lasr_hf_2014": (
            _guard_four_with_hedge("bottom_half_model_ic", "week", "CR-002/CR-003"),
            _guard_kernel("piecewise_linear_interp", "CR-007"),
            _guard_selection(_MIN_Z_ONLY, "CR-008 (G015 N-9 pin)"),
            _guard_horizon("1W", "CR-006 (P3-09/30)"),
            _guard_execution_mode(ExecutionMode.NEXT_OPEN, "CR-018 (P3-30)"),
        ),
        "nlasr_2020": (
            _guard_four_with_hedge(
                "bottom_half_aggregate_pnl", "week", "CR-002/CR-003"
            ),
            _guard_p4_roster,
            _guard_kernel("linear_fit_nonneg", "CR-007"),
            _guard_selection(_MAX_WCORR_ONLY, "CR-008"),
            _guard_no_turnover_cap,
            _guard_horizon("4W", "CR-006 (E-P4-07)"),
            _guard_execution_mode(ExecutionMode.T_PLUS_K_MOC, "CR-018 (E-P4-26)"),
        ),
        "modernized": (
            _guard_four_with_hedge(
                "bottom_half_aggregate_pnl", "week", "CR-002/CR-003"
            ),
            _guard_p4_roster,
            _guard_kernel("linear_fit_nonneg", "CR-007"),
            _guard_selection(_MODERNIZED_SELECTION, "CR-008 (M-07)"),
            _guard_no_turnover_cap,
            _guard_horizon("4W", "CR-006 (modernized §6: inherited unchanged)"),
            _guard_execution_mode(ExecutionMode.T_PLUS_K_MOC, "CR-018 (modernized §6)"),
        ),
    }
)


def run_guards(spec: VersionSpec) -> tuple[GuardViolation, ...]:
    """Evaluate all universal + per-version guards on a resolved spec."""
    violations: list[GuardViolation] = []
    for guard in _UNIVERSAL_GUARDS + SPEC_GUARDS[spec.version_id]:
        violations.extend(guard(spec))
    return tuple(violations)


def enforce_guards(spec: VersionSpec) -> VersionSpec:
    """Raise :class:`SpecGuardError` if any guard is violated; else return
    the spec unchanged (loader entry point, config_system.md §4)."""
    violations = run_guards(spec)
    if violations:
        raise SpecGuardError(spec.version_id, violations)
    return spec
