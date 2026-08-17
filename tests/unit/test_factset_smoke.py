"""FS010 — bounded live-smoke runner, exercised entirely against fakes.

Proves the charter budget discipline BEFORE any real credential exists:
one POST, <=5 ids, cache-first re-run at zero quota, manifest recorded,
typed refusals when credentials/gate/data-root are missing.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from lasr.data.providers.factset.errors import (
    FactSetAuthError,
    FactSetKillSwitchError,
)
from lasr.data.providers.factset.http import HttpResponse
from lasr.data.providers.factset.sanitize import (
    ENV_API_KEY,
    ENV_KILL_SWITCH,
    ENV_LIVE,
    ENV_TRIAL_DATA_ROOT,
    ENV_USERNAME,
)
from lasr.data.providers.factset.smoke import run_live_smoke

pytestmark = pytest.mark.unit

_T0 = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
_CANARY_USER = "CANARY-USER-1234567"
_CANARY_KEY = "CANARY-KEY-abcdefghij"

REPO_ROOT = Path(__file__).resolve().parents[2]
TRIAL_YAML = REPO_ROOT / "configs" / "factset" / "trial.yaml"


class FakeSender:
    def __init__(self, script: list[HttpResponse]) -> None:
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []

    def send(
        self,
        *,
        method: str,
        url: str,
        params: dict[str, str] | None,
        json_body: object | None,
        timeout_seconds: float,
    ) -> HttpResponse:
        self.calls.append({"method": method, "url": url, "json_body": json_body})
        return self.script.pop(0)


def _environ(tmp_path: Path) -> dict[str, str]:
    data_root = tmp_path / "trial_data"
    data_root.mkdir(exist_ok=True)
    return {
        ENV_USERNAME: _CANARY_USER,
        ENV_API_KEY: _CANARY_KEY,
        ENV_LIVE: "1",
        ENV_TRIAL_DATA_ROOT: str(data_root),
    }


def _success_body() -> bytes:
    rows = [
        {
            "requestId": rid,
            "inputSymbolType": "tickerRegion",
            "fsymsecurityid": f"FAKE{i:02d}-S",
        }
        for i, rid in enumerate(["AAPL-US", "FDS-US", "IBM-US", "MSFT-US", "NVDA-US"])
    ]
    return json.dumps({"data": rows}).encode()


class TestSmokeBudgetDiscipline:
    def test_one_post_five_ids_manifest_recorded(self, tmp_path: Path) -> None:
        environ = _environ(tmp_path)
        sender = FakeSender(
            [HttpResponse(status=200, body=_success_body(), headers={})]
        )
        summary = run_live_smoke(
            config_path=TRIAL_YAML,
            environ=environ,
            repo_root=REPO_ROOT,
            code_revision="deadbeef",
            now=_T0,
            sender=sender,
        )
        assert summary["entitlement"] == "ENTITLED"
        assert summary["live_calls"] == 1
        assert summary["resolved_rows"] == 5
        assert len(sender.calls) == 1  # charter: bounded, one POST
        body = sender.calls[0]["json_body"]
        assert isinstance(body, dict) and len(body["ids"]) == 5
        manifest_path = (
            Path(environ[ENV_TRIAL_DATA_ROOT])
            / "runs"
            / "fs010-live-smoke"
            / "manifest.json"
        )
        text = manifest_path.read_text(encoding="utf-8")
        assert _CANARY_KEY not in text and _CANARY_USER not in text
        manifest = json.loads(text)
        assert manifest["entitlement_results"] == {
            "symbology:/identifier-resolution": "ENTITLED"
        }
        assert manifest["code_revision"] == "deadbeef"

    def test_rerun_is_cache_first_zero_quota(self, tmp_path: Path) -> None:
        environ = _environ(tmp_path)
        sender = FakeSender(
            [HttpResponse(status=200, body=_success_body(), headers={})]
        )
        run_live_smoke(
            config_path=TRIAL_YAML,
            environ=environ,
            repo_root=REPO_ROOT,
            code_revision="deadbeef",
            now=_T0,
            sender=sender,
        )
        again = run_live_smoke(
            config_path=TRIAL_YAML,
            environ=environ,
            repo_root=REPO_ROOT,
            code_revision="deadbeef",
            now=_T0,
            sender=FakeSender([]),  # any send would raise IndexError
        )
        assert again["live_calls"] == 0
        assert again["cache_hits"] == 1

    def test_entitlement_refusal_reported_not_raised(self, tmp_path: Path) -> None:
        environ = _environ(tmp_path)
        sender = FakeSender(
            [HttpResponse(status=403, body=b'{"message": "forbidden"}', headers={})]
        )
        summary = run_live_smoke(
            config_path=TRIAL_YAML,
            environ=environ,
            repo_root=REPO_ROOT,
            code_revision="deadbeef",
            now=_T0,
            sender=sender,
        )
        assert summary["entitlement"] == "FORBIDDEN"
        assert summary["error"] is not None

    def test_absent_credentials_is_typed_refusal(self, tmp_path: Path) -> None:
        environ = _environ(tmp_path)
        del environ[ENV_API_KEY]
        with pytest.raises(FactSetAuthError, match="FACTSET_API_KEY"):
            run_live_smoke(
                config_path=TRIAL_YAML,
                environ=environ,
                repo_root=REPO_ROOT,
                code_revision="deadbeef",
                now=_T0,
                sender=FakeSender([]),
            )

    def test_kill_switch_blocks_smoke(self, tmp_path: Path) -> None:
        environ = _environ(tmp_path)
        environ[ENV_KILL_SWITCH] = "1"
        with pytest.raises(FactSetKillSwitchError):
            run_live_smoke(
                config_path=TRIAL_YAML,
                environ=environ,
                repo_root=REPO_ROOT,
                code_revision="deadbeef",
                now=_T0,
                sender=FakeSender([]),
            )
