"""N-LASR 2012 hard-bin piecewise-constant kernel (P1; CR-007 generation 1).

Numeric source of truth: ``docs/evidence/p1_nlasr_2012/formulas.md``.

- §1 weighted class masses ``W+_j / W-_j`` per equal-count quantile bin of
  the coverage-normalized rank (Q=5 production, P1-11; scheme ASSUMED per
  OQ-P1-01 / A-G011-06, ``equal_width`` implemented as the declared
  alternative);
- §2 bin value ``h(x) = 1/2 * ln((W+_j + eps) / (W-_j + eps))`` with
  ``eps = 1/N`` in BOTH numerator and denominator, natural log, the 1/2
  prefactor — all three pinned by the Figure-9 reproduction (§5, CI-035);
- §4 prediction maps new ranks into the STORED bin edges (CI-023 — bins
  are frozen at fit time, never refitted at predict time);
- N for ``eps`` (and the loop's initial weights) = labeled observations in
  the pooled training window (``n_definition="labeled_pooled"``,
  OQ-P1-15 / A-G011-10) — INCLUDING rows whose rank is missing for this
  particular factor (they are excluded from bins per CI-021, not from N).

Missing-feature policy (OQ-P1-05 / A-G011-07): at predict time a missing
rank contributes ``h = 0`` under the default ``h_zero``; the declared
alternative ``propagate_nan`` keeps the score missing so consumers can
handle coverage explicitly (CI-021 requires an implemented alternative).
NOTE (RT-G024-2): the policy also binds INSIDE the training loop — the
selected factor's ``h`` on its own training column feeds the weight
update, so under ``propagate_nan`` a model cannot train through a
SELECTED factor's partial coverage: any missing rank on the selected
factor's training column makes ``h`` NaN and the boosting loop refuses
loudly, naming the factor, the missing-rank count and this policy
(candidates that are never selected do not trigger the refusal — G024
verification precision note). Only ``h_zero`` trains through partial
coverage.

Determinism (CI-042/CI-043): bin edges derive from the sorted covered
values; masses are computed with sort-before-sum reductions; the fit is a
pure function of ``(ranks, labels, weights)`` as multisets + order only
through nothing — row permutations yield bit-identical fits.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
import numpy.typing as npt

from lasr.config.kernel import PiecewiseConstantKernel as PiecewiseConstantKernelConfig
from lasr.config.selection import MinZSelection
from lasr.config.version_spec import VersionSpec
from lasr.core.errors import LasrError
from lasr.models.boosting import BinMasses, KernelExit, Labels, Ranks, Weights
from lasr.models.boosting import stable_sum as _stable_sum

__all__ = [
    "PIECEWISE_CONSTANT_KIND",
    "FittedPiecewiseConstant",
    "KernelFitError",
    "MissingPolicy",
    "PiecewiseConstantBinKernel",
    "bin_log_ratio",
    "build_nlasr_2012_components",
    "decode_piecewise_constant",
    "equal_count_edges",
    "equal_width_edges",
]

logger = logging.getLogger(__name__)

#: Payload discriminator for round serialization (boosting round_decoders).
PIECEWISE_CONSTANT_KIND = "piecewise_constant"

#: OQ-P1-05 / A-G011-07: default ``h_zero``; ``propagate_nan`` is the
#: implemented alternative CI-021 requires.
MissingPolicy = Literal["h_zero", "propagate_nan"]

BinScheme = Literal["equal_count", "equal_width"]


class KernelFitError(LasrError):
    """Invalid kernel input (shape, domain, coverage, config)."""


def bin_log_ratio(
    w_pos: npt.NDArray[np.float64],
    w_neg: npt.NDArray[np.float64],
    epsilon: float,
) -> npt.NDArray[np.float64]:
    """``h_j = 1/2 * ln((W+_j + eps) / (W-_j + eps))`` (P1 formulas §2).

    Golden pins (Fig 9, p.17; CI-035): with ``eps = 1/18``, masses
    (0.3378, 0.2297) -> +0.1607 and (0.1622, 0.2703) -> -0.2016. The
    falsification controls (no eps / no 1/2 / log10) do NOT reproduce
    those numbers (P1 formulas §5).
    """
    if not (math.isfinite(epsilon) and epsilon > 0.0):
        raise KernelFitError(
            f"epsilon must be finite and positive (P1-13: eps = 1/N), got {epsilon}"
        )
    pos = np.asarray(w_pos, dtype=np.float64) + epsilon
    neg = np.asarray(w_neg, dtype=np.float64) + epsilon
    result: npt.NDArray[np.float64] = 0.5 * np.log(pos / neg)
    return result


def equal_count_edges(
    values: npt.NDArray[np.float64], n_bins: int
) -> npt.NDArray[np.float64]:
    """Internal edges of Q equal-count bins (OQ-P1-01 default scheme).

    ``edge_j = v_sorted[ceil(j*n/Q) - 1]`` for ``j = 1..Q-1`` (inverted-CDF
    quantile). Assignment is by VALUE — ``bin(x) = #{edges < x}`` via
    ``searchsorted(edges, x, side="left")`` — so bin 1 is
    ``x <= edge_1``, bin j is ``edge_{j-1} < x <= edge_j``, bin Q is
    ``x > edge_{Q-1}``. With distinct values the counts split
    equal-to-within-one (earlier bins take the remainder under ceil);
    tied values always share a bin, which keeps assignment deterministic
    and input-order invariant (CI-043).
    """
    if n_bins < 2:
        raise KernelFitError(f"n_bins must be >= 2, got {n_bins}")
    data = np.sort(np.asarray(values, dtype=np.float64), kind="stable")
    if data.size == 0:
        raise KernelFitError("cannot fit bin edges on an empty cross-section")
    n = data.size
    indices = [-(-(j * n) // n_bins) - 1 for j in range(1, n_bins)]
    edges: npt.NDArray[np.float64] = data[np.asarray(indices, dtype=np.int64)]
    return edges


def equal_width_edges(n_bins: int) -> npt.NDArray[np.float64]:
    """Internal edges ``j/Q`` on the (0, 1] rank domain (declared
    alternative scheme, OQ-P1-01)."""
    if n_bins < 2:
        raise KernelFitError(f"n_bins must be >= 2, got {n_bins}")
    return np.arange(1, n_bins, dtype=np.float64) / float(n_bins)


def _validate_rank_domain(ranks: npt.NDArray[np.float64], where: str) -> None:
    finite = ranks[np.isfinite(ranks)]
    if finite.size and (float(np.min(finite)) <= 0.0 or float(np.max(finite)) > 1.0):
        raise KernelFitError(
            f"{where}: finite rank values must lie in (0, 1] "
            "(coverage-normalized rank, P1-08); NaN marks missing"
        )


@dataclass(frozen=True, eq=False)
class FittedPiecewiseConstant:
    """One frozen weak learner: stored edges + bin values (CI-023).

    Arrays are read-only; :meth:`predict` performs a pure lookup into the
    STORED training-time bins (P1 formulas §4, pp.17-18) — predicting any
    number of times mutates nothing (asserted by the CI-023 test).
    """

    factor_id: str
    edges: npt.NDArray[np.float64]  # internal edges, length Q-1
    bin_values: npt.NDArray[np.float64]  # h_j, length Q
    w_pos: npt.NDArray[np.float64]  # raw masses, length Q
    w_neg: npt.NDArray[np.float64]
    epsilon: float
    missing_policy: MissingPolicy

    def __post_init__(self) -> None:
        edges = np.asarray(self.edges, dtype=np.float64)
        values = np.asarray(self.bin_values, dtype=np.float64)
        w_pos = np.asarray(self.w_pos, dtype=np.float64)
        w_neg = np.asarray(self.w_neg, dtype=np.float64)
        if edges.ndim != 1 or values.ndim != 1 or values.size != edges.size + 1:
            raise KernelFitError(
                f"need Q-1 edges for Q bin values, got {edges.size} edges "
                f"and {values.size} values"
            )
        if w_pos.shape != values.shape or w_neg.shape != values.shape:
            raise KernelFitError("masses must be one value per bin")
        if float(np.min(np.diff(edges), initial=0.0)) < 0.0:
            raise KernelFitError("bin edges must be non-decreasing")
        if not self.factor_id:
            raise KernelFitError("factor_id must be non-empty")
        for array in (edges, values, w_pos, w_neg):
            array.setflags(write=False)
        object.__setattr__(self, "edges", edges)
        object.__setattr__(self, "bin_values", values)
        object.__setattr__(self, "w_pos", w_pos)
        object.__setattr__(self, "w_neg", w_neg)

    def predict(self, ranks: Ranks) -> npt.NDArray[np.float64]:
        """``h(x)`` via stored-bin lookup; missing per ``missing_policy``."""
        data = np.asarray(ranks, dtype=np.float64)
        _validate_rank_domain(data, f"predict[{self.factor_id}]")
        fill = 0.0 if self.missing_policy == "h_zero" else np.nan
        out = np.full(data.shape, fill, dtype=np.float64)
        covered = np.isfinite(data)
        bins = np.searchsorted(self.edges, data[covered], side="left")
        out[covered] = self.bin_values[bins]
        return out

    def masses(self) -> BinMasses:
        return BinMasses(
            w_pos=self.w_pos.copy(), w_neg=self.w_neg.copy(), epsilon=self.epsilon
        )

    def to_payload(self) -> dict[str, object]:
        """JSON-able payload (floats round-trip exactly via repr)."""
        return {
            "kind": PIECEWISE_CONSTANT_KIND,
            "factor_id": self.factor_id,
            "edges": [float(v) for v in self.edges],
            "bin_values": [float(v) for v in self.bin_values],
            "w_pos": [float(v) for v in self.w_pos],
            "w_neg": [float(v) for v in self.w_neg],
            "epsilon": float(self.epsilon),
            "missing_policy": self.missing_policy,
        }


def decode_piecewise_constant(payload: object) -> FittedPiecewiseConstant:
    """Inverse of :meth:`FittedPiecewiseConstant.to_payload` (round-trip
    identity is a G024 test; register under ``PIECEWISE_CONSTANT_KIND``
    in ``deserialize_fitted_model``'s decoder mapping)."""
    if not isinstance(payload, dict):
        raise KernelFitError(f"payload must be a dict, got {type(payload).__name__}")
    if payload.get("kind") != PIECEWISE_CONSTANT_KIND:
        raise KernelFitError(f"unexpected payload kind {payload.get('kind')!r}")
    missing_policy = payload["missing_policy"]
    if missing_policy not in ("h_zero", "propagate_nan"):
        raise KernelFitError(f"unknown missing_policy {missing_policy!r}")
    return FittedPiecewiseConstant(
        factor_id=str(payload["factor_id"]),
        edges=np.asarray(payload["edges"], dtype=np.float64),
        bin_values=np.asarray(payload["bin_values"], dtype=np.float64),
        w_pos=np.asarray(payload["w_pos"], dtype=np.float64),
        w_neg=np.asarray(payload["w_neg"], dtype=np.float64),
        epsilon=float(payload["epsilon"]),
        missing_policy=missing_policy,
    )


@dataclass(frozen=True)
class PiecewiseConstantBinKernel:
    """The P1/P2 hard-bin kernel (Kernel protocol implementation).

    Every parameter is config-driven (CI-044); see
    :meth:`from_config` / :func:`build_nlasr_2012_components`. This
    kernel NEVER returns :class:`~lasr.models.boosting.KernelExit` — the
    2012 loop runs all L rounds (CI-041); the exit type exists in the
    signature for protocol parity with the P4 kernel (CR-030).
    """

    n_bins: int
    bin_scheme: BinScheme = "equal_count"
    epsilon_mode: Literal["one_over_n", "fixed"] = "one_over_n"
    epsilon_fixed: float | None = None
    n_definition: Literal["labeled_pooled"] = "labeled_pooled"
    missing_policy: MissingPolicy = "h_zero"

    def __post_init__(self) -> None:
        if self.n_bins < 2:
            raise KernelFitError(f"n_bins must be >= 2, got {self.n_bins}")
        if self.epsilon_mode == "fixed":
            if self.epsilon_fixed is None or not (
                math.isfinite(self.epsilon_fixed) and self.epsilon_fixed > 0.0
            ):
                raise KernelFitError(
                    "epsilon_mode='fixed' requires a finite positive "
                    f"epsilon_fixed, got {self.epsilon_fixed}"
                )
        elif self.epsilon_fixed is not None:
            raise KernelFitError(
                "epsilon_fixed is only meaningful under epsilon_mode='fixed'"
            )

    def _epsilon(self, n_labeled: int) -> float:
        if self.epsilon_mode == "fixed":
            assert self.epsilon_fixed is not None  # __post_init__ guarantee
            return self.epsilon_fixed
        # P1-13 / OQ-P1-15: eps = 1/N, N = labeled observations in the
        # pooled window (labels array length — includes rows missing THIS
        # factor's rank; those leave the bins, not N).
        return 1.0 / float(n_labeled)

    def fit_factor(
        self, ranks: Ranks, labels: Labels, weights: Weights, *, factor_id: str
    ) -> FittedPiecewiseConstant | KernelExit:
        """Fit one factor for one round (P1 formulas §§1-2)."""
        if not factor_id:
            raise KernelFitError("factor_id must be non-empty")
        x = np.asarray(ranks, dtype=np.float64)
        y = np.asarray(labels)
        w = np.asarray(weights, dtype=np.float64)
        if not (x.ndim == y.ndim == w.ndim == 1 and x.size == y.size == w.size):
            raise KernelFitError(
                f"ranks/labels/weights must be equal-length 1-D arrays, got "
                f"{x.shape}/{y.shape}/{w.shape}"
            )
        if x.size == 0:
            raise KernelFitError("cannot fit on an empty training set")
        if not np.all(np.isin(y, (-1, 1))):
            raise KernelFitError(
                "labels must be +1/-1 only (CI-016: middle band absent)"
            )
        if not np.all(np.isfinite(w)) or float(np.min(w)) <= 0.0:
            raise KernelFitError("weights must be finite and strictly positive")
        _validate_rank_domain(x, f"fit[{factor_id}]")

        covered = np.isfinite(x)
        n_covered = int(covered.sum())
        if n_covered == 0:
            # An all-missing candidate would otherwise score Z = 0 and win
            # selection spuriously; the papers never discuss the case, so
            # it is a hard error, not a silent skip (assumption candidate).
            raise KernelFitError(
                f"factor {factor_id!r} has zero covered observations - the "
                "feature layer must not deliver empty factors (CI-021)"
            )
        epsilon = self._epsilon(n_labeled=int(y.size))
        if self.bin_scheme == "equal_count":
            edges = equal_count_edges(x[covered], self.n_bins)
        else:
            edges = equal_width_edges(self.n_bins)

        bins = np.searchsorted(edges, x[covered], side="left")
        y_covered = y[covered]
        w_covered = w[covered]
        w_pos = np.zeros(self.n_bins, dtype=np.float64)
        w_neg = np.zeros(self.n_bins, dtype=np.float64)
        for j in range(self.n_bins):  # fixed bin order; sorted sums (CI-043)
            in_bin = bins == j
            w_pos[j] = _stable_sum(w_covered[in_bin & (y_covered == 1)])
            w_neg[j] = _stable_sum(w_covered[in_bin & (y_covered == -1)])

        if n_covered < x.size:
            logger.debug(
                "fit[%s]: %d/%d observations covered (missing excluded, CI-021)",
                factor_id,
                n_covered,
                x.size,
            )
        return FittedPiecewiseConstant(
            factor_id=factor_id,
            edges=edges,
            bin_values=bin_log_ratio(w_pos, w_neg, epsilon),
            w_pos=w_pos,
            w_neg=w_neg,
            epsilon=epsilon,
            missing_policy=self.missing_policy,
        )

    @classmethod
    def from_config(
        cls,
        config: PiecewiseConstantKernelConfig,
        *,
        missing_policy: MissingPolicy,
        region: str | None = None,
    ) -> PiecewiseConstantBinKernel:
        """Build from the evidence-tagged kernel config (CI-044).

        ``region`` selects a CR-012 per-region bin-count override when
        present. ``epsilon_mode='fixed'`` is rejected here because the
        config schema carries no fixed value field — a fixed pseudocount
        is only constructible explicitly in code (documented limitation).
        """
        if config.epsilon_mode.value == "fixed":
            raise KernelFitError(
                "epsilon_mode='fixed' has no value field in the config "
                "schema (CR-011: the evidenced mode is one_over_n); "
                "construct the kernel directly to experiment with fixed eps"
            )
        n_bins = config.n_bins.value
        if region is not None and region in config.n_bins_region_override:
            n_bins = config.n_bins_region_override[region].value
        return cls(
            n_bins=int(n_bins),
            bin_scheme=config.bin_scheme.value,
            epsilon_mode=config.epsilon_mode.value,
            n_definition=config.n_definition.value,
            missing_policy=missing_policy,
        )


def build_nlasr_2012_components(
    spec: VersionSpec, *, region: str | None = None
) -> tuple[PiecewiseConstantBinKernel, MinZSelection]:
    """Resolve one VersionSpec into (kernel, selection config) with the
    OQ-P1-03 cross-check.

    The OQ-P1-03 open question surfaces in TWO tagged leaves —
    ``kernel.epsilon_scope`` and ``selection.smooth_z`` — which must
    agree (``h_only`` <-> ``smooth_z=false``); a spec that smooths Z in
    one place and not the other is a config error, not a silent pick.
    Returns the selection CONFIG (build the objective via
    ``lasr.models.selection.build_objective``) to keep this module free
    of a selection-module import cycle.
    """
    kernel_config = spec.kernel
    if not isinstance(kernel_config, PiecewiseConstantKernelConfig):
        raise KernelFitError(
            f"version {spec.version_id!r} declares kernel type "
            f"{getattr(kernel_config, 'type', '?')!r}; the nlasr_2012 kernel "
            "is piecewise_constant (CR-007: never conflate generations)"
        )
    selection_config = spec.selection
    if not isinstance(selection_config, MinZSelection):
        raise KernelFitError(
            f"version {spec.version_id!r} declares selection type "
            f"{getattr(selection_config, 'type', '?')!r}; nlasr_2012 selects "
            "by min_z (CR-008)"
        )
    smooth_z = bool(selection_config.smooth_z.value)
    scope = kernel_config.epsilon_scope.value
    if smooth_z != (scope == "h_and_z"):
        raise KernelFitError(
            f"OQ-P1-03 inconsistency: kernel.epsilon_scope={scope!r} but "
            f"selection.smooth_z={smooth_z} - the two leaves answer the "
            "same open question and must agree"
        )
    policy = spec.preprocessing.missing_at_predict.value
    if policy == "h_zero":
        missing_policy: MissingPolicy = "h_zero"
    elif policy == "propagate_nan":
        missing_policy = "propagate_nan"
    else:
        raise KernelFitError(
            f"unsupported missing_at_predict {policy!r} (OQ-P1-05 policies: "
            "h_zero, propagate_nan)"
        )
    kernel = PiecewiseConstantBinKernel.from_config(
        kernel_config, missing_policy=missing_policy, region=region
    )
    logger.info(
        "nlasr_2012 components: Q=%d scheme=%s smooth_z=%s missing=%s",
        kernel.n_bins,
        kernel.bin_scheme,
        smooth_z,
        missing_policy,
    )
    return kernel, selection_config
