"""FS010 — trial configuration schema + the committed trial.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from lasr.data.providers.factset.config import (
    FactSetTrialConfig,
    load_trial_config,
    trial_config_hash,
)
from lasr.data.providers.factset.errors import FactSetConfigError

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
TRIAL_YAML = REPO_ROOT / "configs" / "factset" / "trial.yaml"


def minimal_config(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "config_id": "test-config",
        "seed": 1729,
        "transport": {
            "live": False,
            "max_live_calls_per_day": 5,
        },
        "retries": {},
        "batch_poll": {},
        "storage": {
            "max_total_bytes": 10_000_000,
            "free_disk_reserve_bytes": 0,
        },
        "families": {
            "symbology": {
                "api_version": "v3",
                "path_prefix": "/symbology/v3",
                "enabled": True,
                "limits": {
                    "requests_per_second": 10,
                    "concurrent_requests": 10,
                    "max_ids_per_request": 100,
                    "documented": True,
                    "evidence": "DOCUMENTED_OPENAPI",
                },
                "endpoints": [
                    {
                        "endpoint": "/identifier-resolution",
                        "verb": "POST",
                        "max_live_requests": 5,
                    }
                ],
            }
        },
    }
    for key, value in overrides.items():
        base[key] = value
    return base


class TestSchema:
    def test_minimal_config_validates(self) -> None:
        config = FactSetTrialConfig.model_validate(minimal_config())
        assert config.transport.live is False
        assert config.family("symbology").limits.requests_per_second == 10

    def test_unknown_keys_are_load_errors(self) -> None:
        data = minimal_config()
        data["surprise_knob"] = True
        with pytest.raises(ValidationError):
            FactSetTrialConfig.model_validate(data)

    def test_live_mode_requires_positive_budget(self) -> None:
        data = minimal_config()
        data["transport"] = {"live": True, "max_live_calls_per_day": 0}
        with pytest.raises(ValidationError, match="positive max_live_calls_per_day"):
            FactSetTrialConfig.model_validate(data)

    def test_enabled_family_requires_endpoints(self) -> None:
        data = minimal_config()
        data["families"]["symbology"]["endpoints"] = []
        with pytest.raises(ValidationError, match="declare its endpoints"):
            FactSetTrialConfig.model_validate(data)

    def test_live_enabled_endpoint_needs_nonzero_limit(self) -> None:
        data = minimal_config()
        data["transport"] = {"live": True, "max_live_calls_per_day": 5}
        data["families"]["symbology"]["endpoints"][0]["max_live_requests"] = 0
        with pytest.raises(ValidationError, match="zero request limit"):
            FactSetTrialConfig.model_validate(data)

    def test_endpoint_lookup_typed_errors(self) -> None:
        config = FactSetTrialConfig.model_validate(minimal_config())
        with pytest.raises(FactSetConfigError, match="not declared"):
            config.family("mystery")
        with pytest.raises(FactSetConfigError, match="not enabled"):
            config.endpoint_policy("symbology", "/nope")

    def test_config_hash_is_deterministic_and_content_sensitive(self) -> None:
        a = FactSetTrialConfig.model_validate(minimal_config())
        b = FactSetTrialConfig.model_validate(minimal_config())
        assert trial_config_hash(a) == trial_config_hash(b)
        c = FactSetTrialConfig.model_validate(minimal_config(seed=42))
        assert trial_config_hash(c) != trial_config_hash(a)

    def test_base_url_must_be_https(self) -> None:
        data = minimal_config()
        data["transport"]["base_url"] = "http://api.factset.com/content"
        with pytest.raises(ValidationError, match="https"):
            FactSetTrialConfig.model_validate(data)


class TestCommittedTrialYaml:
    """The committed configs/factset/trial.yaml is itself under test."""

    def test_loads_and_validates(self) -> None:
        config = load_trial_config(TRIAL_YAML)
        # config revision bumped by FS024 (family enables + probe budgets)
        assert config.config_id == "factset-trial-fs024-1"

    def test_replay_is_the_committed_default(self) -> None:
        # A committed config alone can never go live (FS002 §6.1) — and
        # ours does not even try.
        config = load_trial_config(TRIAL_YAML)
        assert config.transport.live is False
        assert config.transport.kill_switch is False

    def test_symbology_limits_match_fs003_manifest(self) -> None:
        config = load_trial_config(TRIAL_YAML)
        symbology = config.family("symbology")
        assert symbology.enabled is True
        assert symbology.limits.requests_per_second == 10  # DOCUMENTED
        assert symbology.limits.concurrent_requests == 10  # DOCUMENTED
        assert symbology.limits.max_ids_per_request == 100  # D-1 ceiling
        assert symbology.limits.documented is True

    def test_all_families_enabled_with_declared_endpoints(self) -> None:
        # FS009 verified the manifests; FS024 (exclusive owner of the
        # family enables) flipped all six on for the entitlement probes.
        # Every enabled family must declare bounded endpoint budgets.
        config = load_trial_config(TRIAL_YAML)
        enabled = [n for n, f in config.families.items() if f.enabled]
        assert sorted(enabled) == [
            "benchmarks",
            "estimates",
            "fundamentals",
            "global_prices",
            "rbics",
            "symbology",
        ]
        for family in config.families.values():
            assert family.endpoints, "enabled family without endpoint budgets"
            for ep in family.endpoints:
                assert ep.max_live_requests >= 1

    def test_smoke_budget_at_most_five_requests(self) -> None:
        # FS010 charter: API budget <= 5 live requests.
        config = load_trial_config(TRIAL_YAML)
        policy = config.endpoint_policy("symbology", "/identifier-resolution")
        assert 1 <= policy.max_live_requests <= 5
        smoke = config.samples["fs010_live_smoke"]
        assert 1 <= len(smoke.ids) <= 5

    def test_undocumented_families_flagged(self) -> None:
        # Families with UNRESOLVED vendor rate limits stay on the
        # conservative default and are telemetry-flagged even while
        # enabled for the FS024 probes (FS002 §6.4).
        config = load_trial_config(TRIAL_YAML)
        for name in ("global_prices", "rbics", "benchmarks"):
            family = config.family(name)
            assert family.limits.documented is False
            assert family.limits.evidence == "UNRESOLVED"
            assert family.limits.requests_per_second <= 5

    def test_retention_register_present(self) -> None:
        config = load_trial_config(TRIAL_YAML)
        register = config.storage.retention_register
        assert len(register) >= 3
        assert any(e.contains_vendor_data for e in register)
        assert all(e.disposal_owner for e in register)

    def test_no_credential_values_in_yaml(self) -> None:
        # Names may be documented; values never (fs_goals HARD RULES).
        text = TRIAL_YAML.read_text(encoding="utf-8")
        for name in ("FACTSET_USERNAME", "FACTSET_API_KEY"):
            for line in text.splitlines():
                if name in line:
                    assert "=" not in line.split(name, 1)[1][:2], line
