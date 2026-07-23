"""Loader semantics: strict YAML loading, deep-merge inheritance,
canonical hashing, and the ExperimentConfig user kind (config_system.md
§1/§5/§8)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from lasr.config import (
    ConfigLoadError,
    DateRange,
    ExperimentConfig,
    Override,
    ProviderConfig,
    canonical_json,
    config_hash,
    deep_merge,
    load_version_spec,
    load_yaml_mapping,
)

pytestmark = pytest.mark.unit

FIXTURE = Path(__file__).resolve().parents[2] / (
    "tests/fixtures/config/nlasr_2012.yaml"
)


class TestLoadYamlMapping:
    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigLoadError, match="cannot read"):
            load_yaml_mapping(tmp_path / "absent.yaml")

    def test_invalid_yaml(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text("a: [unclosed\n", encoding="utf-8")
        with pytest.raises(ConfigLoadError, match="invalid YAML"):
            load_yaml_mapping(bad)

    def test_non_mapping_document(self, tmp_path: Path) -> None:
        doc = tmp_path / "list.yaml"
        doc.write_text("- 1\n- 2\n", encoding="utf-8")
        with pytest.raises(ConfigLoadError, match="must contain a mapping"):
            load_yaml_mapping(doc)


class TestStrictUnknownKeys:
    def test_top_level_unknown_key_is_load_error(self, tmp_path: Path) -> None:
        # MP §26 hidden-defaults rule: misspelled keys never silently ignored.
        text = FIXTURE.read_text(encoding="utf-8") + "\nunknown_section: {}\n"
        target = tmp_path / "nlasr_2012.yaml"
        target.write_text(text, encoding="utf-8")
        with pytest.raises(ValidationError, match="extra_forbidden"):
            load_version_spec(target)

    def test_nested_unknown_key_is_load_error(self, tmp_path: Path) -> None:
        text = FIXTURE.read_text(encoding="utf-8").replace(
            "n_rounds:", "n_round_count:", 1
        )
        target = tmp_path / "nlasr_2012.yaml"
        target.write_text(text, encoding="utf-8")
        with pytest.raises(ValidationError):
            load_version_spec(target)

    def test_unknown_kernel_discriminator_rejected(self, tmp_path: Path) -> None:
        # CR-007: only the three generation keys exist.
        text = FIXTURE.read_text(encoding="utf-8").replace(
            "type: piecewise_constant", "type: gradient_boosting", 1
        )
        target = tmp_path / "nlasr_2012.yaml"
        target.write_text(text, encoding="utf-8")
        with pytest.raises(ValidationError, match="union_tag_invalid"):
            load_version_spec(target)


class TestDeepMerge:
    def test_nested_mapping_merge(self) -> None:
        base = {"a": {"x": 1, "y": 2}, "b": 1}
        delta = {"a": {"y": 3}}
        assert deep_merge(base, delta) == {"a": {"x": 1, "y": 3}, "b": 1}

    def test_lists_replace_wholesale(self) -> None:
        base = {"components": [1, 2, 3]}
        delta = {"components": [4]}
        assert deep_merge(base, delta) == {"components": [4]}

    def test_inputs_not_mutated(self) -> None:
        base = {"a": {"x": 1}}
        delta = {"a": {"y": 2}}
        merged = deep_merge(base, delta)
        assert base == {"a": {"x": 1}} and delta == {"a": {"y": 2}}
        assert merged == {"a": {"x": 1, "y": 2}}


class TestCanonicalHash:
    def test_hash_is_sha256_hex(self) -> None:
        spec = load_version_spec(FIXTURE)
        digest = config_hash(spec)
        assert len(digest) == 64
        assert int(digest, 16) >= 0

    def test_canonical_json_sorted_and_compact(self) -> None:
        spec = load_version_spec(FIXTURE)
        text = canonical_json(spec)
        assert ": " not in text and ", " not in text
        top_keys = [k for k in ["acceptance", "boosting", "clocks"] if f'"{k}"' in text]
        assert top_keys == ["acceptance", "boosting", "clocks"]


class TestExperimentConfig:
    def _experiment(self, **kw: object) -> ExperimentConfig:
        base: dict[str, object] = {
            "experiment_id": "exp-001",
            "version_spec": "configs/models/nlasr_2012.yaml",
            "provider": {"name": "synthetic", "scenario": "baseline"},
            "universe_instance": "synthetic_us_1000",
            "dates": {"start": "1996-01-31", "end": "2011-12-30"},
            "seed": 1729,
            "artifacts_root": "artifacts",
        }
        base.update(kw)
        return ExperimentConfig.model_validate(base)

    def test_minimal_experiment(self) -> None:
        exp = self._experiment()
        assert exp.cost_scenario == "base"
        assert exp.portfolio_level == 1
        assert exp.faithful is True
        assert exp.provider == ProviderConfig(name="synthetic", scenario="baseline")

    def test_override_requires_modernized_or_assumed(self) -> None:
        # config_system.md §5: overrides never masquerade as paper evidence.
        with pytest.raises(ValidationError, match="MODERNIZED or ASSUMED"):
            Override.model_validate(
                {
                    "path": "boosting.n_rounds",
                    "value": 20,
                    "prov": "EXPLICIT",
                    "src": "user",
                    "rationale": "sensitivity",
                }
            )

    def test_override_requires_rationale(self) -> None:
        with pytest.raises(ValidationError):
            Override.model_validate(
                {
                    "path": "boosting.n_rounds",
                    "value": 20,
                    "prov": "ASSUMED",
                    "src": "user",
                    "rationale": "",
                }
            )

    def test_overrides_flip_faithful(self) -> None:
        exp = self._experiment(
            overrides=[
                {
                    "path": "boosting.n_rounds",
                    "value": 20,
                    "prov": "ASSUMED",
                    "src": "CR-010 sensitivity",
                    "rationale": "rounds sweep point",
                }
            ]
        )
        assert exp.faithful is False

    def test_portfolio_level_closed(self) -> None:
        with pytest.raises(ValidationError):
            self._experiment(portfolio_level=4)

    def test_inverted_date_range_rejected(self) -> None:
        with pytest.raises(ValidationError, match="before start"):
            DateRange.model_validate({"start": "2011-12-30", "end": "1996-01-31"})

    def test_unknown_key_rejected(self) -> None:
        with pytest.raises(ValidationError, match="extra_forbidden"):
            self._experiment(provder="typo")
