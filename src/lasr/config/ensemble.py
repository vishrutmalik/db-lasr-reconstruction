"""Ensemble component and combination configs (CR-002/003/005/027).

# arch: config_system.md §3 + training_and_artifacts.md §3. The component
discriminator values are pinned one-to-one to the canonical
``SampleSelectorSpec`` union in ``lasr.data.schemas.ensemble`` (G017:
``ExpertSpec`` is canonical; the architecture's ``HedgeSelector``
``type: "hedge"`` literal is superseded by the schemas layer's
``hedge_backcast`` — doc drift noted in the G043 report). The binding is
asserted by ``tests/unit/test_config_bindings.py``.

The component roster length is a version fact enforced by the spec guards
(CR-002: 3 components for nlasr_2012, 4 for 2013+; a hedge component in
the P1-era spec must fail to build).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from lasr.config.provenance import ConfigModel, Param

__all__ = [
    "ComponentConfig",
    "EnsembleConfig",
    "HedgeBackcastComponent",
    "PreviousPeriodComponent",
    "SeasonalSameMonthComponent",
    "TrailingWindowComponent",
]


class TrailingWindowComponent(ConfigModel):
    """Trailing window of realized periods (P1-19; P3-18; E-P4-10).

    ``require_full_window`` (A-G025-04 strict arm; YAML leaf promoted at
    G029 per the G025 handoff): ``true`` refuses a fit whose realized
    history is shorter than ``periods``; the default (absent/``false``)
    uses all available with a warning.
    """

    type: Literal["trailing_window"] = "trailing_window"
    periods: Param[int]
    require_full_window: Param[bool] | None = None  # A-G025-04


class SeasonalSameMonthComponent(ConfigModel):
    """Same-calendar-month/week seasonal pool (P1-20; E-P4-10).

    ``lag_years`` default 0 per CR-027 (the P3 footnote's 1-year lag is an
    erratum; the value exists only for the documented sensitivity run).
    ``anchor`` resolves the OQ-P4-14 month-anchor ambiguity (A-G011-60);
    the seasonal grain follows the component's expert grain (G017 NB-3).
    """

    type: Literal["seasonal_same_month"] = "seasonal_same_month"
    years: Param[int]  # lookback depth (P1-20; A-G011-42 for HF)
    lag_years: Param[int]  # CR-027
    min_history: Param[str]  # OQ-P1-16; A-G011-14
    anchor: Param[str] | None = None  # OQ-P4-14; A-G011-60


class PreviousPeriodComponent(ConfigModel):
    """Most recent realized period(s) (P1-21; P3-18).

    ``require_full_window`` as on :class:`TrailingWindowComponent`
    (A-G025-04; leaf promoted at G029).
    """

    type: Literal["previous_period"] = "previous_period"
    periods: Param[int]
    require_full_window: Param[bool] | None = None  # A-G025-04


class HedgeBackcastComponent(ConfigModel):
    """Adverse-environment component via point-in-time backcast (CR-003).

    ``selection_metric`` carries CR-003's three per-generation rules;
    the spec guards pin the legal metric per version.
    """

    type: Literal["hedge_backcast"] = "hedge_backcast"
    selection_metric: Param[
        Literal[
            "backcast_ic_threshold",  # nlasr2_2013 (E-P2-19/20)
            "bottom_half_model_ic",  # lasr_2014 family (P3-17/18)
            "bottom_half_aggregate_pnl",  # nlasr_2020 (E-P4-11)
        ]
    ]
    threshold: Param[float] | None = None  # 0.075 for the IC rule (E-P2-20)
    lookback_periods: Param[int]  # 144m / 120m / 156w / 520w (CR-003)
    grain: Param[Literal["month", "week"]]
    backcast_object: Param[str]  # P2 Q8; A-G011-28/61
    backcast_excludes_hedge: Param[bool] | None = None  # P2 Q9; A-G011-29
    pnl_basis: Param[Literal["gross", "net"]] | None = None  # A-G011-61
    #: A-G025-01 odd-count rule for the bottom-half metrics (YAML leaf
    #: promoted at G029; default "floor" when absent).
    bottom_half_rule: Param[Literal["floor", "ceil"]] | None = None


ComponentConfig = Annotated[
    TrailingWindowComponent
    | SeasonalSameMonthComponent
    | PreviousPeriodComponent
    | HedgeBackcastComponent,
    Field(discriminator="type"),
]


class EnsembleConfig(ConfigModel):
    """Component roster + combination rules (CR-002/005).

    The roster is version-guarded; combination knobs carry the CR-005
    weighting resolutions and the OQ-P1-04/06/17 ambiguities as tagged
    leaves (# arch: config_system.md §3).
    """

    components: tuple[ComponentConfig, ...] = Field(min_length=1)  # CR-002
    pooling_weights: Param[str]  # OQ-P1-04; A-G011-13
    weighting: Param[Literal["equal", "seasonal_rank_ic"]]  # CR-005
    ic_window: Param[Literal["expanding", "trailing_k"]] | None = None  # OQ-P1-06
    #: Window depth for ``ic_window='trailing_k'`` (A-G025-07; YAML leaf
    #: promoted at G029 — the trailing arm still refuses without an
    #: EXPLICIT k, never a hidden default).
    trailing_k: Param[int] | None = None
    #: A-G025-02 fallback threshold: components with fewer realized
    #: same-key IC observations force equal weights (default 1; YAML
    #: leaf promoted at G029).
    min_observations: Param[int] | None = None
    negative_ic_floor: Param[float] | None = None  # OQ-P1-06; A-G011-16
    first_year_weighting: Param[Literal["equal"]] | None = None  # P1-25
    hedge_weight_rule: (
        Param[Literal["equal", "mean_of_others_then_normalize"]] | None
    ) = None  # CR-005; F-P2-8 (always exactly 1/4)
    component_zscore: Param[
        Literal["per_date_cross_sectional", "none"]
    ]  # P1-23; A-G011-35
    zscore_universe: Param[Literal["scoring", "training"]]  # OQ-P1-17
    component_target_scope: Param[Literal["uniform", "baseline_only"]] | None = (
        None  # lasr_hc P3 Q3; A-G011-40
    )
    composite_normalization: Param[Literal["none", "zscore"]] | None = (
        None  # nlasr_2020 extraction §29; A-G011-62
    )
    blend_weights: Param[str] | None = None  # lasr_hf sub-model blend, P3 Q7;
    # A-G011-46 — the structural two-sub-model roster is bound at the model
    # layer via EnsembleRosterSpec (G017 N-1)
