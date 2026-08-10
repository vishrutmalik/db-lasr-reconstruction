"""Per-date cross-sectional transforms: rank/(0,1], z-score, winsorize.

Every function here consumes exactly ONE date's cross-section (a mapping
``security_id → raw value``) and nothing else — per-date locality (CI-020)
and as-of-statistics discipline (CI-004(a)) hold *by construction*; the
metamorphic tests assert them anyway. Stored feature values are
pre-rank/pre-neutralization (D-007); these transforms run downstream,
selected by version-keyed config (``PreprocessingConfig``).

Policies, each cited:

- **Rank normalization** (P1-07/08; F-P2-1): score = rank / N ∈ (0, 1]
  where N counts stocks WITH COVERAGE for that factor on that date (P1
  extraction item 8 — the per-factor coverage divisor is INFERRED from
  "coverage varies between factors"); rank 1 = highest raw value (P2
  Figure 10, p.16). Missing values are excluded from the rank and stay
  missing (CI-021: never imputed).
- **Outlier policy**: ranking IS the outlier treatment (P1-09, P4 item 9);
  no winsorizing "out of habit". :func:`winsorize` /
  :class:`FittedWinsorizer` exist as *declared alternatives* only — a
  registry entry must cite a reason to use them.
- **Ties**: papers are silent (OQ-P1-01) — the documented deterministic
  default breaks ties by ascending ``security_id`` (stable, CI-043);
  ``"average"`` (shared average rank) is the declared alternative.
- **Within-cell ranking** (F-P2-3 machinery): rank within the caller's
  cell partition; a security without a cell assignment is excluded
  (missing group ⇒ missing score, documented).
- **z-score** (P1-23 family): per-date mean/std of the given cross-section
  only (CI-022 locality); population std (ddof=0); a degenerate
  cross-section (std = 0) scores 0.0 everywhere (documented, deterministic).
- **FittedWinsorizer**: fit/apply split — bounds are fitted once and frozen
  (the CI-023 fit-time/predict-time discipline at this layer: applying to a
  new cross-section never refits).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

import numpy as np

from lasr.core.errors import LasrError

__all__ = [
    "FittedWinsorizer",
    "RankDirection",
    "TieRule",
    "TransformError",
    "rank_normalize",
    "rank_normalize_by_cell",
    "winsorize",
    "zscore",
]

#: ``highest_first``: rank 1 = highest raw value (P2 Figure 10; OQ-P1-02).
RankDirection = Literal["highest_first", "lowest_first"]

#: Deterministic tie handling (OQ-P1-01 → ASSUMED config; CI-043).
TieRule = Literal["security_id", "average"]


class TransformError(LasrError):
    """Invalid cross-sectional transform input (empty fit, bad bounds)."""


def _covered(values: Mapping[str, float | None]) -> list[tuple[str, float]]:
    """Coverage rule (CI-021): a value is covered iff present and finite;
    everything else is excluded — never imputed."""
    return [
        (security_id, float(value))
        for security_id, value in values.items()
        if value is not None and math.isfinite(value)
    ]


def rank_normalize(
    values: Mapping[str, float | None],
    *,
    rank_direction: RankDirection = "highest_first",
    tie_rule: TieRule = "security_id",
) -> dict[str, float]:
    """Rank-normalize one date's cross-section to (0, 1] (F-P2-1, P1-07/08).

    score = rank / N with N = covered count (per-factor coverage divisor,
    CI-021); rank 1 = highest raw value under ``highest_first``. Missing
    securities are absent from the result. Deterministic under input-order
    permutation (CI-043): ordering depends only on (value, security_id).
    """
    covered = _covered(values)
    n = len(covered)
    if n == 0:
        return {}
    sign = -1.0 if rank_direction == "highest_first" else 1.0
    ordered = sorted(covered, key=lambda item: (sign * item[1], item[0]))
    if tie_rule == "security_id":
        return {
            security_id: (position + 1) / n
            for position, (security_id, _) in enumerate(ordered)
        }
    # tie_rule == "average": tied raw values share the average of their
    # positional ranks (declared alternative; scores may repeat).
    scores: dict[str, float] = {}
    start = 0
    while start < n:
        end = start
        while end + 1 < n and ordered[end + 1][1] == ordered[start][1]:
            end += 1
        shared = ((start + 1) + (end + 1)) / 2 / n
        for position in range(start, end + 1):
            scores[ordered[position][0]] = shared
        start = end + 1
    return scores


def rank_normalize_by_cell(
    values: Mapping[str, float | None],
    cells: Mapping[str, str],
    *,
    rank_direction: RankDirection = "highest_first",
    tie_rule: TieRule = "security_id",
) -> dict[str, float]:
    """Within-cell rank normalization (F-P2-3 machinery; CI-020 per-cell).

    Each security is ranked ONLY against its own cell's covered members;
    the coverage divisor is the cell's covered count. A covered security
    without a cell assignment is excluded (missing group ⇒ missing score,
    documented — cell metadata must itself be as-of, CI-026).
    """
    by_cell: dict[str, dict[str, float]] = {}
    for security_id, value in _covered(values):
        cell = cells.get(security_id)
        if cell is None:
            continue
        by_cell.setdefault(cell, {})[security_id] = value
    scores: dict[str, float] = {}
    for cell in sorted(by_cell):  # deterministic assembly order
        scores.update(
            rank_normalize(
                by_cell[cell], rank_direction=rank_direction, tie_rule=tie_rule
            )
        )
    return scores


def zscore(values: Mapping[str, float | None]) -> dict[str, float]:
    """Cross-sectional z-score of ONE date's values (CI-022 locality).

    Mean and population std (ddof=0) come from the given cross-section
    only. Degenerate cross-section: every covered score is 0.0
    (documented deterministic choice). Missing values excluded (CI-021).

    Degeneracy detection (G025 fix of the G022 round-2 queued defect;
    A-G025-05): an all-identical cross-section of LARGE values can leave
    ``std`` at a few ulps instead of exactly 0.0 (the computed mean
    rounds off), which used to emit constant ±1 scores. Any spread at or
    below the round-off floor ``max|x| * n * eps`` is numerically
    indistinguishable from a constant cross-section, so it is treated as
    degenerate (tolerance cap): float64 carries ~2.2e-16 relative
    precision, and a real cross-sectional dispersion sits many orders of
    magnitude above ``n * eps`` relative. Exact zeros (including the
    all-zero cross-section, ``max|x| = 0``) still hit the ``<=`` branch.
    """
    covered = _covered(values)
    if not covered:
        return {}
    data = np.array([value for _, value in covered], dtype=np.float64)
    mean = float(np.mean(data))
    std = float(np.std(data))  # ddof=0: population std, documented
    tolerance = float(np.max(np.abs(data))) * data.size * np.finfo(np.float64).eps
    if std <= tolerance:
        return {security_id: 0.0 for security_id, _ in covered}
    return {security_id: (value - mean) / std for security_id, value in covered}


@dataclass(frozen=True)
class FittedWinsorizer:
    """Winsorization bounds fitted once, frozen thereafter (CI-023 style).

    ``fit`` estimates quantile clip bounds on a training cross-section;
    ``apply`` clips any later cross-section with the STORED bounds — it
    never refits, so the artifact is bit-identical across applications.
    """

    lower_bound: float
    upper_bound: float
    lower_quantile: float
    upper_quantile: float

    @classmethod
    def fit(
        cls,
        values: Mapping[str, float | None],
        *,
        lower_quantile: float,
        upper_quantile: float,
    ) -> FittedWinsorizer:
        if not 0.0 <= lower_quantile < upper_quantile <= 1.0:
            raise TransformError(
                f"quantiles must satisfy 0 <= lower < upper <= 1, got "
                f"({lower_quantile}, {upper_quantile})"
            )
        covered = _covered(values)
        if not covered:
            raise TransformError(
                "cannot fit winsorization bounds on an empty cross-section "
                "(silent no-op bounds forbidden)"
            )
        data = np.array([value for _, value in covered], dtype=np.float64)
        # numpy default 'linear' interpolation: deterministic, documented.
        lower = float(np.quantile(data, lower_quantile))
        upper = float(np.quantile(data, upper_quantile))
        return cls(
            lower_bound=lower,
            upper_bound=upper,
            lower_quantile=lower_quantile,
            upper_quantile=upper_quantile,
        )

    def apply(self, values: Mapping[str, float | None]) -> dict[str, float]:
        """Clip a cross-section to the frozen bounds (no refit — CI-023)."""
        return {
            security_id: min(max(value, self.lower_bound), self.upper_bound)
            for security_id, value in _covered(values)
        }


def winsorize(
    values: Mapping[str, float | None],
    *,
    lower_quantile: float,
    upper_quantile: float,
) -> dict[str, float]:
    """One-shot within-date winsorization (fit + apply on the same date).

    Declared ALTERNATIVE policy only: the papers rank instead (P1-09) — a
    registry entry adopting this must cite its reason.
    """
    if not _covered(values):
        return {}
    return FittedWinsorizer.fit(
        values, lower_quantile=lower_quantile, upper_quantile=upper_quantile
    ).apply(values)
