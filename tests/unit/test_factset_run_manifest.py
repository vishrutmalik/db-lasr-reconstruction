"""FS010 — trial run manifests: config snapshot, metrics, sanitization."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from lasr.data.providers.factset.capabilities import (
    access_plan_hash,
    access_plan_snapshot,
)
from lasr.data.providers.factset.config import (
    FactSetTrialConfig,
    trial_config_hash,
)
from lasr.data.providers.factset.errors import FactSetConfigError
from lasr.data.providers.factset.run_manifest import (
    build_run_manifest,
    write_run_manifest,
)
from lasr.data.providers.factset.sanitize import (
    ENV_API_KEY,
    ENV_USERNAME,
    Sanitizer,
)
from lasr.data.providers.factset.transport import TransportStats

pytestmark = pytest.mark.unit

_T0 = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
_T1 = datetime(2026, 1, 5, 10, 5, tzinfo=UTC)
_CANARY_KEY = "CANARY-KEY-abcdefghij"


def _config() -> FactSetTrialConfig:
    data: dict[str, Any] = {
        "config_id": "manifest-test",
        "seed": 1729,
        "transport": {"live": False, "max_live_calls_per_day": 5},
        "retries": {},
        "batch_poll": {},
        "storage": {
            "max_total_bytes": 1000,
            "free_disk_reserve_bytes": 0,
            "retention_register": [
                {
                    "artifact": "raw captures",
                    "location": "$FACTSET_TRIAL_DATA_ROOT/raw",
                    "contains_vendor_data": True,
                    "retention": "trial duration",
                    "disposal_owner": "user",
                }
            ],
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
        "samples": {
            "smoke": {"ids": ["AAPL-US"], "notes": "test block"},
        },
    }
    return FactSetTrialConfig.model_validate(data)


def _stats() -> TransportStats:
    stats = TransportStats()
    stats.cache_hits = 2
    stats.live_calls = 1
    stats.retries = 1
    stats.errors = 0
    stats.bytes_stored = 123
    stats.entitlement_results["symbology:/identifier-resolution"] = "ENTITLED"
    stats.capture_ids.append("a" * 64)
    return stats


class TestBuildRunManifest:
    def test_records_config_hash_metrics_and_lineage(self) -> None:
        config = _config()
        manifest = build_run_manifest(
            run_id="run-001",
            config=config,
            code_revision="deadbeef",
            stats=_stats(),
            environ={ENV_USERNAME: "u", ENV_API_KEY: _CANARY_KEY},
            started=_T0,
            finished=_T1,
        )
        assert manifest["config_hash"] == trial_config_hash(config)
        assert manifest["access_plan_hash"] == access_plan_hash(config.access_plan)
        assert manifest["access_plan"] == access_plan_snapshot(config.access_plan)
        assert manifest["config"]["access_plan"] == manifest["access_plan"]
        assert manifest["code_revision"] == "deadbeef"
        assert manifest["endpoints_enabled"] == {
            "symbology": ["/identifier-resolution"]
        }
        metrics = manifest["metrics"]
        assert isinstance(metrics, dict)
        assert metrics["live_calls"] == 1 and metrics["cache_hits"] == 2
        assert manifest["raw_capture_sha256"] == ["a" * 64]
        assert manifest["entitlement_results"] == {
            "symbology:/identifier-resolution": "ENTITLED"
        }
        register = manifest["retention_register"]
        assert isinstance(register, list) and register[0]["disposal_owner"] == "user"

    def test_credential_presence_booleans_never_values(self) -> None:
        manifest = build_run_manifest(
            run_id="run-002",
            config=_config(),
            code_revision="deadbeef",
            stats=_stats(),
            environ={ENV_API_KEY: _CANARY_KEY},
            started=_T0,
            finished=_T1,
        )
        presence = manifest["credential_presence"]
        assert isinstance(presence, dict)
        assert presence[ENV_API_KEY] is True
        assert presence[ENV_USERNAME] is False
        assert _CANARY_KEY not in json.dumps(manifest)

    def test_missing_code_revision_refused(self) -> None:
        with pytest.raises(FactSetConfigError, match="code_revision"):
            build_run_manifest(
                run_id="run-003",
                config=_config(),
                code_revision="  ",
                stats=_stats(),
                environ={},
                started=_T0,
                finished=_T1,
            )


class TestWriteRunManifest:
    def test_written_manifest_is_sanitized(self, tmp_path: Path) -> None:
        manifest = build_run_manifest(
            run_id="run-004",
            config=_config(),
            code_revision="deadbeef",
            stats=_stats(),
            environ={},
            started=_T0,
            finished=_T1,
            notes=f"debug: key={_CANARY_KEY}",  # worst case: a leaked note
        )
        path = write_run_manifest(
            manifest,
            runs_root=tmp_path / "runs",
            sanitizer=Sanitizer((_CANARY_KEY,)),
        )
        assert path == tmp_path / "runs" / "run-004" / "manifest.json"
        text = path.read_text(encoding="utf-8")
        assert _CANARY_KEY not in text
        assert "***REDACTED***" in text
        parsed = json.loads(text)
        assert parsed["run_id"] == "run-004"

    def test_run_id_required(self, tmp_path: Path) -> None:
        with pytest.raises(FactSetConfigError, match="run_id"):
            write_run_manifest(
                {"run_id": ""}, runs_root=tmp_path, sanitizer=Sanitizer(())
            )

    @pytest.mark.parametrize("tamper", ["snapshot", "hash", "config"])
    def test_forged_access_plan_binding_is_refused(
        self, tmp_path: Path, tamper: str
    ) -> None:
        manifest = build_run_manifest(
            run_id=f"run-tamper-{tamper}",
            config=_config(),
            code_revision="deadbeef",
            stats=_stats(),
            environ={},
            started=_T0,
            finished=_T1,
        )
        forged = deepcopy(manifest)
        if tamper == "snapshot":
            forged["access_plan"]["version"] = "forged"
        elif tamper == "hash":
            forged["access_plan_hash"] = "0" * 64
        else:
            forged["config"]["access_plan"]["version"] = "forged"
        with pytest.raises(FactSetConfigError, match="access-plan"):
            write_run_manifest(
                forged,
                runs_root=tmp_path / "runs",
                sanitizer=Sanitizer(()),
            )
