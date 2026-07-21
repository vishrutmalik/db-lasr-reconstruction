"""The frozen TimingRecord: all eight MP §23 backtest timestamps.

MP §23 requires the engine to distinguish: feature, knowledge, model-fit,
signal-generation, order-decision, execution, **holding period**, and
**target period**. The first six map to one field each; the two periods map
to explicit intervals — ``[execution_time, holding_end]`` for the holding
period and ``[target_start, target_end]`` for the target period. The
explicit ``holding_end`` (distinct from target horizon) resolves G015
verification finding N-4: for ``nlasr_2020`` the two differ (1-week hold,
4-week target), so neither may be derived from the other.

# arch: training_and_artifacts.md §4.1; canonical_schemas.md §10 (the
training-example schema carries these fields per CI-018).
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime, timedelta
from enum import StrEnum

from lasr.core.errors import TimeSemanticsError
from lasr.core.time_semantics import ensure_utc

__all__ = ["ExecutionMode", "TimingRecord"]


class ExecutionMode(StrEnum):
    """Execution timing convention (CR-018).

    # arch: training_and_artifacts.md §4.1. The P1 baseline's acknowledged
    look-ahead is encoded as ``SAME_CLOSE``, never as falsified knowledge
    times (# arch: system_design.md §1).
    """

    SAME_CLOSE = "same_close"  # P1 baseline (acknowledged look-ahead)
    ONE_DAY_LAG = "one_day_lag"  # P1 variant
    NEXT_OPEN = "next_open"  # lasr_hf (P3-30)
    T_PLUS_K_MOC = "t_plus_k_moc"  # nlasr_2020, k=2 default (E-P4-26)


@dataclass(frozen=True)
class TimingRecord:
    """Frozen per-grid-point timing, stamped into every training example and
    trade (CI-018).

    Validated invariants (raise :class:`TimeSemanticsError`):

    - CI-012 chain: ``feature_observation_time <= knowledge_cutoff <=
      decision_time <= execution_time == target_start < target_end``;
    - ``model_fit_time <= signal_time <= decision_time`` (a signal cannot
      precede the fit that produced it; refit may be sparser than rebalance,
      CR-006, so ``model_fit_time`` may precede ``knowledge_cutoff``);
    - ``execution_time < holding_end`` (positive holding period, N-4);
    - all timestamps tz-aware, normalized to UTC (system_design.md §1).

    ``target_end - target_start`` versus the configured horizon on the
    trading calendar is CI-013's behavioral check (G023); this record only
    guarantees the structural ordering.
    """

    feature_observation_time: datetime  # MP §23: feature timestamp
    knowledge_cutoff: datetime  # MP §23: knowledge timestamp
    model_fit_time: datetime  # MP §23: model-fit timestamp
    signal_time: datetime  # MP §23: signal-generation timestamp
    decision_time: datetime  # MP §23: order-decision timestamp
    execution_time: datetime  # MP §23: execution timestamp (= target_start)
    target_start: datetime  # MP §23: target period start (CI-012)
    target_end: datetime  # MP §23: target period end (CI-013)
    holding_end: datetime  # MP §23: holding period end (N-4)

    def __post_init__(self) -> None:
        for field in fields(self):
            object.__setattr__(self, field.name, ensure_utc(getattr(self, field.name)))
        chain: tuple[tuple[str, str], ...] = (
            ("feature_observation_time", "knowledge_cutoff"),
            ("knowledge_cutoff", "decision_time"),
            ("model_fit_time", "signal_time"),
            ("signal_time", "decision_time"),
            ("decision_time", "execution_time"),
        )
        for earlier, later in chain:
            if getattr(self, earlier) > getattr(self, later):
                raise TimeSemanticsError(
                    f"CI-012 timing chain violated: {earlier} > {later} "
                    f"({getattr(self, earlier).isoformat()} > "
                    f"{getattr(self, later).isoformat()})"
                )
        if self.execution_time != self.target_start:
            raise TimeSemanticsError(
                "CI-012 requires execution_time == target_start; got "
                f"{self.execution_time.isoformat()} != "
                f"{self.target_start.isoformat()}"
            )
        if not self.target_start < self.target_end:
            raise TimeSemanticsError(
                "CI-012 requires target_start < target_end; got "
                f"{self.target_start.isoformat()} >= "
                f"{self.target_end.isoformat()}"
            )
        if not self.execution_time < self.holding_end:
            raise TimeSemanticsError(
                "holding period must be positive (N-4): holding_end "
                f"{self.holding_end.isoformat()} <= execution_time "
                f"{self.execution_time.isoformat()}"
            )

    @property
    def holding_period(self) -> timedelta:
        """Explicit holding period, distinct from the target horizon (N-4)."""
        return self.holding_end - self.execution_time

    @property
    def target_horizon(self) -> timedelta:
        """Target period length (CI-013 checks it against the config)."""
        return self.target_end - self.target_start
