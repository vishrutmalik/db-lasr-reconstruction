"""Report-artifact and A-003 banner tests (G028).

Queued obligation (assumptions_register.md A-003, routed to G028 via
the integration queue): every report artifact carries a
machine-readable AND human-visible SYNTHETIC banner when inputs are
synthetic — structural (the artifact cannot be built without the
provenance block), config-driven (the flag comes from the caller's
input provenance), and tested here:

- synthetic without the banner (or with a paraphrased banner) is a
  typed refusal; non-synthetic with a banner is equally refused;
- the banner constant is byte-identical to the synthetic sidecar's
  ``A003_BANNER`` (restated in reporting because the import-rule table
  keeps reporting off ``lasr.data.synthetic``);
- ``render_text`` puts the banner on LINE ONE; ``to_json`` carries the
  machine-readable flag + text;
- CI-042: double-building the artifact from identical inputs (seeded
  bootstrap included) yields byte-identical JSON;
- NOT_AVAILABLE sections render naming their missing producer.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from lasr.data.synthetic.sidecar import A003_BANNER as SIDECAR_BANNER
from lasr.reporting.artifact import ReportArtifact, render_text
from lasr.reporting.errors import MetricInputError
from lasr.reporting.types import A003_BANNER, NotAvailable, SyntheticProvenance
from lasr.reporting.validity import (
    block_bootstrap_mean,
    configurations_tested,
    multiple_testing_diagnostics,
    sensitivity_report,
    validation_to_test_degradation,
)

pytestmark = pytest.mark.unit

NOW = datetime(2021, 6, 30, 21, 0, tzinfo=UTC)
SEED = 1729


def _artifact(*, synthetic: bool) -> ReportArtifact:
    return ReportArtifact(
        config_hash="cfg",
        generated_for=NOW,
        provenance=SyntheticProvenance.from_flag(synthetic),
        configurations=configurations_tested(["cfg"]),
        degradation=(
            validation_to_test_degradation(
                metric="ic_mean", validation_value=0.08, test_value=0.05
            ),
        ),
        sensitivities=(
            sensitivity_report(
                axis="costs",
                metric="sharpe",
                base_value=2.0,
                scenario_values={"5bps": 2.2, "30bps": 1.2},
            ),
        ),
        bootstrap=(
            block_bootstrap_mean(
                [0.04, -0.01, 0.03, 0.02],
                n_resamples=99,
                block_length=2,
                seed=SEED,
            ),
        ),
        multiple_testing=multiple_testing_diagnostics(
            raw_p_value=0.01, n_configurations=7
        ),
        submodel=NotAvailable(
            metric="submodel_contribution",
            missing_producer="G025 temporal ensembles",
        ),
    )


class TestA003BannerStructural:
    def test_banner_matches_the_sidecar_byte_for_byte(self) -> None:
        """The restated constant can never drift from the generator's."""
        assert A003_BANNER == SIDECAR_BANNER
        assert A003_BANNER.encode() == SIDECAR_BANNER.encode()

    def test_synthetic_without_banner_refused(self) -> None:
        with pytest.raises((MetricInputError, ValidationError)):
            SyntheticProvenance(synthetic_inputs=True, banner=None)

    def test_paraphrased_banner_refused(self) -> None:
        with pytest.raises((MetricInputError, ValidationError)):
            SyntheticProvenance(
                synthetic_inputs=True, banner="synthetic data, be careful"
            )

    def test_fake_banner_on_real_inputs_refused(self) -> None:
        with pytest.raises((MetricInputError, ValidationError)):
            SyntheticProvenance(synthetic_inputs=False, banner=A003_BANNER)

    def test_from_flag_builds_both_shapes(self) -> None:
        synthetic = SyntheticProvenance.from_flag(True)
        assert synthetic.synthetic_inputs is True
        assert synthetic.banner == A003_BANNER
        real = SyntheticProvenance.from_flag(False)
        assert real.synthetic_inputs is False
        assert real.banner is None

    def test_artifact_requires_provenance(self) -> None:
        with pytest.raises(ValidationError):
            ReportArtifact(config_hash="cfg", generated_for=NOW)  # type: ignore[call-arg]


class TestRendering:
    def test_banner_is_line_one_when_synthetic(self) -> None:
        text = render_text(_artifact(synthetic=True))
        first_line = text.splitlines()[0]
        assert A003_BANNER in first_line
        assert first_line.startswith("***")

    def test_no_banner_when_real(self) -> None:
        text = render_text(_artifact(synthetic=False))
        assert "SYNTHETIC" not in text

    def test_machine_readable_flag_in_json(self) -> None:
        payload = _artifact(synthetic=True).to_json()
        assert '"synthetic_inputs":true' in payload
        assert "SYNTHETIC DATA (A-003)" in payload

    def test_not_available_sections_name_the_producer(self) -> None:
        text = render_text(_artifact(synthetic=True))
        assert "NOT_AVAILABLE (missing producer: G025 temporal ensembles)" in text


class TestDeterminismCI042:
    def test_double_build_is_byte_identical(self) -> None:
        """Identical inputs (seeded bootstrap included) -> identical
        JSON bytes and identical rendered text."""
        a = _artifact(synthetic=True)
        b = _artifact(synthetic=True)
        assert a.to_json().encode() == b.to_json().encode()
        assert render_text(a) == render_text(b)

    def test_artifacts_are_frozen(self) -> None:
        artifact = _artifact(synthetic=True)
        with pytest.raises(ValidationError):
            artifact.config_hash = "tampered"  # type: ignore[misc]
