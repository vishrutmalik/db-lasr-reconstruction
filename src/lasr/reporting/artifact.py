"""The assembled report artifact: one typed, banner-carrying container.

Structural A-003 enforcement (assumptions_register.md A-003): the
artifact cannot be constructed without a :class:`SyntheticProvenance`
block, whose own validator forces the banner verbatim when
``synthetic_inputs`` is True and forbids it otherwise. The banner is
therefore machine-readable (``provenance.synthetic_inputs``,
``provenance.banner``) and human-visible (:func:`render_text` prints it
as the FIRST line; ``to_json`` serializes it) on every artifact —
config-driven, never inferred here.

Determinism (CI-042): the artifact is a frozen pydantic tree of frozen
results; ``to_json`` is a pure function of the model, so double runs
over identical inputs produce byte-identical output (seeded bootstrap
included). A unit test pins the double-run byte identity.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from lasr.reporting.coverage import CoverageAccounting, OOSCoverage
from lasr.reporting.portfolio_metrics import (
    ExposureSummary,
    PortfolioSummary,
    TailLosses,
    TurnoverSummary,
)
from lasr.reporting.signal import (
    FactorSelectionStability,
    FeatureFamilyExposure,
    ICSummary,
    PredictionDecay,
    QuantileMetrics,
    SignalAutocorrelation,
    SubmodelContribution,
)
from lasr.reporting.types import NotAvailable, ReportModel, SyntheticProvenance
from lasr.reporting.validity import (
    BootstrapResult,
    ConfigurationsTested,
    Degradation,
    MultipleTestingDiagnostics,
    SensitivityReport,
)

__all__ = ["ReportArtifact", "render_text"]


class ReportArtifact(ReportModel):
    """One run's full reporting output (signal + portfolio + validity).

    Sections are optional (a signal-only run has no ledger) but every
    PRESENT metric is a typed result — a section that could not be
    computed for a structural reason is a :class:`NotAvailable`, never
    an omitted-and-forgotten field. ``provenance`` is mandatory.
    """

    config_hash: str = Field(min_length=1)
    generated_for: datetime  # the run's data_end / build_as_of instant
    provenance: SyntheticProvenance

    # signal section
    ic_pearson: ICSummary | NotAvailable | None = None
    ic_spearman: ICSummary | NotAvailable | None = None
    quantiles: QuantileMetrics | NotAvailable | None = None
    autocorrelation: SignalAutocorrelation | NotAvailable | None = None
    decay: PredictionDecay | NotAvailable | None = None
    factor_stability: FactorSelectionStability | NotAvailable | None = None
    family_exposure: FeatureFamilyExposure | NotAvailable | None = None
    submodel: SubmodelContribution | NotAvailable | None = None

    # portfolio section
    portfolio: PortfolioSummary | NotAvailable | None = None
    turnover: TurnoverSummary | NotAvailable | None = None
    exposures: ExposureSummary | NotAvailable | None = None
    tails: TailLosses | NotAvailable | None = None
    beta: float | NotAvailable | None = None

    # coverage / validity section
    oos_coverage: OOSCoverage | NotAvailable | None = None
    coverage: CoverageAccounting | NotAvailable | None = None
    configurations: ConfigurationsTested | NotAvailable | None = None
    degradation: tuple[Degradation, ...] = ()
    sensitivities: tuple[SensitivityReport, ...] = ()
    bootstrap: tuple[BootstrapResult, ...] = ()
    multiple_testing: MultipleTestingDiagnostics | NotAvailable | None = None

    def to_json(self) -> str:
        """Deterministic JSON serialization (CI-042 byte identity)."""
        return self.model_dump_json()


def render_text(artifact: ReportArtifact) -> str:
    """Human-visible rendering; the A-003 banner is ALWAYS line one
    when inputs are synthetic (never buried)."""
    lines: list[str] = []
    if artifact.provenance.synthetic_inputs:
        assert artifact.provenance.banner is not None  # validator-enforced
        lines.append(f"*** {artifact.provenance.banner} ***")
    lines.append(f"report for config_hash={artifact.config_hash}")
    lines.append(f"generated for data through {artifact.generated_for.isoformat()}")
    for name in (
        "ic_pearson",
        "ic_spearman",
        "quantiles",
        "autocorrelation",
        "decay",
        "factor_stability",
        "family_exposure",
        "submodel",
        "portfolio",
        "turnover",
        "exposures",
        "tails",
        "beta",
        "oos_coverage",
        "coverage",
        "configurations",
        "multiple_testing",
    ):
        value = getattr(artifact, name)
        if value is None:
            continue
        if isinstance(value, NotAvailable):
            lines.append(
                f"{name}: NOT_AVAILABLE (missing producer: {value.missing_producer})"
            )
        elif isinstance(value, float):
            lines.append(f"{name}: {value!r}")
        else:
            lines.append(f"{name}: {value.model_dump_json()}")
    for label, seq in (
        ("degradation", artifact.degradation),
        ("sensitivity", artifact.sensitivities),
        ("bootstrap", artifact.bootstrap),
    ):
        for item in seq:
            lines.append(f"{label}: {item.model_dump_json()}")
    return "\n".join(lines) + "\n"
