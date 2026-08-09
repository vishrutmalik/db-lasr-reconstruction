"""Generic risk-model interface + transparent shrinkage SUBSTITUTE (A-004).

The papers use a proprietary DB/Axioma-style risk model that is
unavailable by design (assumptions_register.md A-004). This module
defines the generic interface (:class:`RiskModel`) the Level-3 optimizer
consumes, plus one transparent substitute implementation
(:class:`ShrinkageRiskModel`). The substitute is labelled STRUCTURALLY,
three ways, so no report can present it as a replication:

- interface flag: ``is_substitute`` is ``True`` on every substitute;
- output marker: every :class:`RiskModelManifest` carries ``substitute``
  and the assumption id (``A-004``), and the optimizer copies the
  manifest onto its result object;
- config acknowledgment: the ``risk_model:`` block requires
  ``substitute: true`` (see :mod:`lasr.portfolio.level3_config`).

Estimator conventions (register candidates, federated per D-005):

- **A-G035-01 (shrinkage estimator + intensity convention):** no paper
  discloses the risk model, so the substitute is pinned as: sample
  covariance ``S`` of aligned per-period return histories with the
  ``N-1`` (unbiased) denominator, linearly shrunk toward its own
  diagonal: ``sigma(delta) = (1 - delta) * S + delta * diag(S)`` with
  ``delta`` a FIXED config parameter in ``[0, 1]`` (``0`` = sample,
  ``1`` = diagonal / zero-correlation). Variances are preserved exactly
  for every ``delta``; only co-movements shrink. This is a Ledoit-Wolf
  STYLE target with a configured (not estimated) intensity — chosen for
  transparency and hand-computability over adaptiveness. PSD for every
  ``delta`` in ``[0, 1]`` by convexity of the PSD cone.
- **A-G035-02 (annualization):** annualized volatility uses iid
  sqrt-time scaling, ``vol_ann = sqrt(annualization_periods * w' sigma
  w)``, with ``annualization_periods`` a config parameter (12 monthly /
  52 weekly).

Factor exposures are EXPLICIT inputs (provided, never estimated here):
each factor's loading vector must cover every security in the model —
a missing loading is a typed refusal, never an imputed zero
(:class:`~lasr.portfolio.level3_errors.RiskModelInputError`).

Determinism (CI-042): pure numpy on ascending-id-ordered panels; no RNG,
no wall clock; double builds/queries are bit-identical.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite
from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray

from lasr.portfolio.level3_errors import RiskModelInputError

__all__ = [
    "SUBSTITUTE_ASSUMPTION_ID",
    "FloatArray",
    "RiskModel",
    "RiskModelManifest",
    "ShrinkageRiskModel",
]

logger = logging.getLogger(__name__)

FloatArray = NDArray[np.float64]

#: The assumptions-register id every substitute manifest must carry.
SUBSTITUTE_ASSUMPTION_ID = "A-004"


@dataclass(frozen=True)
class RiskModelManifest:
    """Output marker describing the risk model that produced a number.

    ``substitute=True`` + ``assumption_id="A-004"`` is the structural
    label MP §24 requires ("mark it as an assumption rather than an
    exact replication"); reporting layers must surface it verbatim.
    """

    name: str
    substitute: bool
    assumption_id: str | None
    estimator: str
    shrinkage_intensity: float | None
    n_observations: int | None
    n_securities: int
    factor_names: tuple[str, ...]
    annualization_periods: int

    def __post_init__(self) -> None:
        if self.substitute and self.assumption_id != SUBSTITUTE_ASSUMPTION_ID:
            raise RiskModelInputError(
                "a substitute risk model must carry assumption_id="
                f"{SUBSTITUTE_ASSUMPTION_ID!r}, got {self.assumption_id!r} "
                "(A-004 labelling is structural, never optional)"
            )


@runtime_checkable
class RiskModel(Protocol):
    """What the Level-3 optimizer may depend on (MP §24 generic interface)."""

    @property
    def is_substitute(self) -> bool:
        """``True`` when this model is an A-004 substitute, not the
        papers' proprietary model. Structural — consumers must propagate."""
        ...

    @property
    def manifest(self) -> RiskModelManifest: ...

    @property
    def annualization_periods(self) -> int: ...

    def security_ids(self) -> tuple[str, ...]:
        """Covered security ids, ascending."""
        ...

    def covariance(self, ids: Sequence[str]) -> FloatArray:
        """Per-period covariance submatrix in the requested id order."""
        ...

    def factor_loadings(self, factor: str, ids: Sequence[str]) -> FloatArray:
        """Explicit loading vector for ``factor`` in the requested order."""
        ...


def _validate_ids(
    ids: Sequence[str], known: Mapping[str, int], *, what: str
) -> list[int]:
    if len(ids) == 0:
        raise RiskModelInputError(f"{what}: empty id list")
    if len(set(ids)) != len(ids):
        dupes = sorted({sec for sec in ids if list(ids).count(sec) > 1})
        raise RiskModelInputError(f"{what}: duplicate ids {dupes}")
    unknown = sorted(set(ids) - set(known))
    if unknown:
        raise RiskModelInputError(
            f"{what}: ids not covered by the risk model: {unknown} — "
            "imputing a default risk is refused"
        )
    return [known[sec] for sec in ids]


class ShrinkageRiskModel:
    """The transparent A-004 SUBSTITUTE: shrinkage covariance + explicit
    factor exposures. NOT a replication of the papers' risk model.

    Built from aligned per-period return histories (one equal-length
    sequence per security, same period grid, oldest first) plus explicit
    factor loading vectors. See the module docstring for the pinned
    estimator (A-G035-01) and annualization (A-G035-02) conventions.
    """

    def __init__(
        self,
        returns: Mapping[str, Sequence[float]],
        *,
        shrinkage_intensity: float,
        annualization_periods: int,
        factor_exposures: Mapping[str, Mapping[str, float]] | None = None,
    ) -> None:
        if not returns:
            raise RiskModelInputError("returns panel is empty")
        if not isfinite(shrinkage_intensity) or not (0.0 <= shrinkage_intensity <= 1.0):
            raise RiskModelInputError(
                "shrinkage_intensity must be in [0, 1] (A-G035-01: 0 = "
                f"sample, 1 = diagonal), got {shrinkage_intensity!r}"
            )
        if annualization_periods < 1:
            raise RiskModelInputError(
                "annualization_periods must be >= 1 (A-G035-02), got "
                f"{annualization_periods}"
            )
        ids = tuple(sorted(returns))
        lengths = {sec: len(returns[sec]) for sec in ids}
        n_obs = lengths[ids[0]]
        misaligned = sorted(sec for sec in ids if lengths[sec] != n_obs)
        if misaligned:
            raise RiskModelInputError(
                "return histories must be aligned (equal length, same "
                f"period grid); offending ids: {misaligned} "
                f"(expected {n_obs} observations)"
            )
        if n_obs < 2:
            raise RiskModelInputError(
                f"need >= 2 aligned observations for a sample covariance "
                f"(N-1 denominator, A-G035-01); got {n_obs}"
            )
        panel = np.asarray(
            [returns[sec] for sec in ids], dtype=np.float64
        )  # shape (n, T), ascending-id rows: order-invariant by construction
        if not np.all(np.isfinite(panel)):
            bad = [ids[i] for i in sorted(set(np.argwhere(~np.isfinite(panel))[:, 0]))]
            raise RiskModelInputError(f"non-finite returns for securities: {bad}")

        sample = np.cov(panel, ddof=1)  # N-1 denominator (A-G035-01)
        sample = np.atleast_2d(np.asarray(sample, dtype=np.float64))
        diagonal = np.diag(np.diag(sample))
        shrunk = (1.0 - shrinkage_intensity) * sample + shrinkage_intensity * diagonal

        exposures = dict(factor_exposures or {})
        factor_matrix: dict[str, FloatArray] = {}
        for factor in sorted(exposures):
            loadings = exposures[factor]
            missing = sorted(set(ids) - set(loadings))
            if missing:
                raise RiskModelInputError(
                    f"factor {factor!r}: loadings missing for {missing} — "
                    "a missing loading is never an imputed zero"
                )
            unknown = sorted(set(loadings) - set(ids))
            if unknown:
                raise RiskModelInputError(
                    f"factor {factor!r}: loadings for ids outside the "
                    f"model universe: {unknown}"
                )
            vector = np.asarray([loadings[sec] for sec in ids], dtype=np.float64)
            if not np.all(np.isfinite(vector)):
                bad = [ids[i] for i in np.argwhere(~np.isfinite(vector))[:, 0]]
                raise RiskModelInputError(
                    f"factor {factor!r}: non-finite loadings for {bad}"
                )
            factor_matrix[factor] = vector

        self._ids = ids
        self._index = {sec: i for i, sec in enumerate(ids)}
        self._covariance = shrunk
        self._factors = factor_matrix
        self._manifest = RiskModelManifest(
            name="shrinkage_substitute",
            substitute=True,
            assumption_id=SUBSTITUTE_ASSUMPTION_ID,
            estimator=(
                "sample covariance (N-1) linearly shrunk toward its "
                "diagonal: (1-delta)*S + delta*diag(S) (A-G035-01)"
            ),
            shrinkage_intensity=shrinkage_intensity,
            n_observations=n_obs,
            n_securities=len(ids),
            factor_names=tuple(sorted(factor_matrix)),
            annualization_periods=annualization_periods,
        )
        logger.info(
            "built %s risk model: %d securities, %d observations, "
            "delta=%.4f, factors=%s [A-004 SUBSTITUTE, not a replication]",
            self._manifest.name,
            len(ids),
            n_obs,
            shrinkage_intensity,
            list(self._manifest.factor_names),
        )

    @property
    def is_substitute(self) -> bool:
        """Always ``True``: this model is the A-004 substitute."""
        return True

    @property
    def manifest(self) -> RiskModelManifest:
        return self._manifest

    @property
    def annualization_periods(self) -> int:
        return self._manifest.annualization_periods

    def security_ids(self) -> tuple[str, ...]:
        return self._ids

    def covariance(self, ids: Sequence[str]) -> FloatArray:
        """Shrunk per-period covariance submatrix in the requested order."""
        rows = _validate_ids(ids, self._index, what="covariance")
        return self._covariance[np.ix_(rows, rows)].copy()

    def factor_loadings(self, factor: str, ids: Sequence[str]) -> FloatArray:
        if factor not in self._factors:
            raise RiskModelInputError(
                f"unknown factor {factor!r}; model factors: {sorted(self._factors)}"
            )
        rows = _validate_ids(ids, self._index, what=f"factor {factor!r}")
        return self._factors[factor][rows].copy()

    def annualized_volatility(self, weights: Mapping[str, float]) -> float:
        """``sqrt(annualization_periods * w' sigma w)`` (A-G035-02)."""
        ids = tuple(sorted(weights))
        vector = np.asarray([weights[sec] for sec in ids], dtype=np.float64)
        if not np.all(np.isfinite(vector)):
            bad = [ids[i] for i in np.argwhere(~np.isfinite(vector))[:, 0]]
            raise RiskModelInputError(f"non-finite weights for {bad}")
        variance = float(vector @ self.covariance(ids) @ vector)
        return float(np.sqrt(self._manifest.annualization_periods * variance))
