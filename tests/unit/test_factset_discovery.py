"""FS024 — discovery runner: plan, classification, replay, live, budget.

Everything runs against fakes/tmp caches; the live-mode tests script a
FakeSender in exact plan order and prove budget + hygiene discipline.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from lasr.data.providers.factset.cache import ResponseCache
from lasr.data.providers.factset.config import load_trial_config
from lasr.data.providers.factset.discovery import (
    DEFERRED_OPERATIONS,
    FAMILY_OPERATION_TOTALS,
    EndpointClassification,
    build_probe_plan,
    render_entitlements_markdown,
    run_discovery,
)
from lasr.data.providers.factset.errors import FactSetConfigError
from lasr.data.providers.factset.http import HttpResponse
from lasr.data.providers.factset.request_norm import request_hash
from lasr.data.providers.factset.sanitize import (
    ENV_API_KEY,
    ENV_LIVE,
    ENV_TRIAL_DATA_ROOT,
    ENV_USERNAME,
)

pytestmark = pytest.mark.unit

_T0 = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
_CANARY_USER = "CANARY-USER-1234567"
_CANARY_KEY = "CANARY-KEY-abcdefghij"

REPO_ROOT = Path(__file__).resolve().parents[2]
TRIAL_YAML = REPO_ROOT / "configs" / "factset" / "trial.yaml"

#: Async-batch endpoints that must NEVER be live-enabled before FS012
#: fixes VF-FS010-3 (batch-poll budget bypass).
_BATCH_ENDPOINTS = {"/point-in-time", "/periods", "/batch-status", "/batch-result"}


def _data_body(n_rows: int) -> bytes:
    rows = [{"requestId": f"ROW{i:02d}", "value": float(i)} for i in range(n_rows)]
    return json.dumps({"data": rows}).encode()


def _fund_catalog_body(metrics: list[tuple[str, bool, bool]]) -> bytes:
    rows = [
        {
            "metric": metric,
            "name": f"Name {metric}",
            "category": "INCOME_STATEMENT",
            "subcategory": "SUPPLEMENTAL",
            "isPIT": is_pit,
            "isNonPIT": is_non_pit,
            "factor": 1,
            "dataType": "double",
        }
        for metric, is_pit, is_non_pit in metrics
    ]
    return json.dumps({"data": rows}).encode()


def _est_catalog_body(metrics: list[str]) -> bytes:
    rows = [
        {"metric": m, "name": m, "category": "FINANCIAL_STATEMENT", "factor": 1}
        for m in metrics
    ]
    return json.dumps({"data": rows}).encode()


def _error_body(message: str) -> bytes:
    return json.dumps({"status": "ERROR", "message": message}).encode()


#: Scripted live responses in EXACT probe-plan order (15 probes).
def _scripted_responses() -> list[HttpResponse]:
    ok = {"headers": {}}
    return [
        HttpResponse(status=200, body=_data_body(5), **ok),  # sym current
        HttpResponse(status=200, body=_data_body(5), **ok),  # sym gated types
        HttpResponse(status=200, body=_data_body(4), **ok),  # sym historical
        HttpResponse(  # fundamentals /metrics non-PIT: 3 metrics
            status=200,
            body=_fund_catalog_body(
                [
                    ("FF_SALES", True, True),
                    ("FF_ASSETS", False, True),
                    ("FF_STD_ONLY", False, True),
                ]
            ),
            **ok,
        ),
        HttpResponse(  # fundamentals /metrics PIT: 2 metrics, 1 shared
            status=200,
            body=_fund_catalog_body(
                [("FF_SALES", True, True), ("FF_PIT_ONLY", True, False)]
            ),
            **ok,
        ),
        HttpResponse(status=200, body=_data_body(2), **ok),  # /fundamentals
        HttpResponse(status=200, body=_data_body(2), **ok),  # /prices
        HttpResponse(status=200, body=_data_body(3), **ok),  # /corporate-actions
        HttpResponse(  # estimates /metrics: 2 metrics
            status=200, body=_est_catalog_body(["EPS", "SALES"]), **ok
        ),
        HttpResponse(status=200, body=_data_body(0), **ok),  # fixed-consensus EMPTY
        HttpResponse(status=200, body=_data_body(1), **ok),  # rbics /structure
        HttpResponse(  # rbics /entity-focus: entitlement refusal
            status=403, body=_error_body("User is not authorized"), **ok
        ),
        HttpResponse(status=200, body=_data_body(3), **ok),  # bm /id-list
        HttpResponse(  # bm /constituents: route/id not found
            status=404, body=_error_body("Not found"), **ok
        ),
        HttpResponse(  # bm /index-snapshot: ambiguous client error
            status=400, body=_error_body("Bad request: unclear reason"), **ok
        ),
    ]


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
        self.calls.append(
            {"method": method, "url": url, "params": params, "json_body": json_body}
        )
        if not self.script:
            raise AssertionError("FakeSender script exhausted — unplanned live call")
        return self.script.pop(0)


def _live_environ(tmp_path: Path) -> dict[str, str]:
    data_root = tmp_path / "trial_data"
    data_root.mkdir(exist_ok=True)
    return {
        ENV_USERNAME: _CANARY_USER,
        ENV_API_KEY: _CANARY_KEY,
        ENV_LIVE: "1",
        ENV_TRIAL_DATA_ROOT: str(data_root),
    }


class TestProbePlan:
    def test_plan_covers_all_six_families_deterministically(self) -> None:
        config = load_trial_config(TRIAL_YAML)
        plan_a = build_probe_plan(config)
        plan_b = build_probe_plan(config)
        assert len(plan_a) == 15
        families = {spec.family for spec in plan_a}
        assert families == set(FAMILY_OPERATION_TOTALS)
        # identical plans hash identically (deterministic replay identity)
        assert [request_hash(s.request) for s in plan_a] == [
            request_hash(s.request) for s in plan_b
        ]
        # every request identity is unique — no probe shadows another
        hashes = [request_hash(s.request) for s in plan_a]
        assert len(set(hashes)) == len(hashes)

    def test_smoke_probe_reuses_the_f005_request_identity(self) -> None:
        """The first symbology probe re-issues the FS010 smoke request
        verbatim so it replays from the existing capture (0 live)."""
        from lasr.data.providers.factset.symbology_models import (
            build_identifier_resolution_request,
        )

        config = load_trial_config(TRIAL_YAML)
        plan = build_probe_plan(config)
        smoke_ids = list(config.samples["fs010_live_smoke"].ids)
        expected = build_identifier_resolution_request(
            ids=smoke_ids,
            output_symbol_types=["fsymSecurityId", "fsymRegionalId", "tickerRegion"],
        )
        assert request_hash(plan[0].request) == request_hash(expected)

    def test_plan_is_config_driven_not_hardcoded(self) -> None:
        config = load_trial_config(TRIAL_YAML)
        anchor = date.fromisoformat(config.samples["fs024_discovery"].anchor_dates[0])
        plan = {spec.probe_id: spec for spec in build_probe_plan(config)}
        prices = plan["global-prices-prices"].request
        assert prices.params["startDate"] == anchor.isoformat()
        constituents = plan["benchmarks-constituents"].request
        assert constituents.params["ids"] == list(
            config.samples["fs024_benchmarks"].ids
        )

    def test_missing_sample_block_is_typed_refusal(self) -> None:
        config = load_trial_config(TRIAL_YAML)
        stripped = config.model_copy(
            update={
                "samples": {
                    k: v for k, v in config.samples.items() if k != "fs024_discovery"
                }
            }
        )
        with pytest.raises(FactSetConfigError, match="fs024_discovery"):
            build_probe_plan(stripped)


class TestTrialConfigBudgets:
    def test_all_families_enabled_with_bounded_budgets(self) -> None:
        config = load_trial_config(TRIAL_YAML)
        assert set(config.families) == set(FAMILY_OPERATION_TOTALS)
        endpoint_sum = 0
        for family in config.families.values():
            assert family.enabled
            for ep in family.endpoints:
                assert ep.max_live_requests >= 1
                endpoint_sum += ep.max_live_requests
        # FS024 charter: live budget <=150 requests, enforced two ways
        assert endpoint_sum <= 150
        assert config.transport.max_live_calls_per_day <= 150

    def test_async_batch_endpoints_are_never_live_enabled(self) -> None:
        """VF-FS010-3: batch live is prohibited until FS012 — the config
        must not enable any batch surface."""
        config = load_trial_config(TRIAL_YAML)
        for family in config.families.values():
            for ep in family.endpoints:
                assert ep.endpoint not in _BATCH_ENDPOINTS
        deferred = {(d.family, d.endpoint) for d in DEFERRED_OPERATIONS}
        assert ("fundamentals", "/point-in-time") in deferred
        assert ("global_prices", "/batch-result") in deferred


class TestReplayMode:
    def test_replay_without_root_is_typed_refusal(self, tmp_path: Path) -> None:
        with pytest.raises(FactSetConfigError, match="cache_root"):
            run_discovery(
                config_path=TRIAL_YAML,
                environ={},
                repo_root=REPO_ROOT,
                code_revision="deadbeef",
                now=_T0,
            )

    def test_empty_cache_classifies_not_captured_zero_live(
        self, tmp_path: Path
    ) -> None:
        report = run_discovery(
            config_path=TRIAL_YAML,
            environ={},
            repo_root=REPO_ROOT,
            code_revision="deadbeef",
            now=_T0,
            cache_root=tmp_path / "raw",
        )
        assert report.live_calls == 0
        assert all(
            r.classification is EndpointClassification.NOT_CAPTURED
            for r in report.probes
        )
        assert report.overlap is None
        markdown = render_entitlements_markdown(report)
        assert "Not captured" in markdown
        assert "Deferred operations" in markdown

    def test_seeded_captures_replay_as_working(self, tmp_path: Path) -> None:
        cache_root = tmp_path / "raw"
        cache = ResponseCache(cache_root)
        config = load_trial_config(TRIAL_YAML)
        plan = {spec.probe_id: spec for spec in build_probe_plan(config)}
        cache.store(
            plan["fundamentals-metrics-pit"].request,
            _fund_catalog_body(
                [("FF_SALES", True, True), ("FF_PIT_ONLY", True, False)]
            ),
            http_status=200,
            retrieval_time=_T0,
        )
        cache.store(
            plan["fundamentals-metrics-non-pit"].request,
            _fund_catalog_body(
                [
                    ("FF_SALES", True, True),
                    ("FF_ASSETS", False, True),
                    ("FF_STD_ONLY", False, True),
                ]
            ),
            http_status=200,
            retrieval_time=_T0,
        )
        cache.store(
            plan["estimates-metrics"].request,
            _est_catalog_body(["EPS", "SALES"]),
            http_status=200,
            retrieval_time=_T0,
        )
        report = run_discovery(
            config_path=TRIAL_YAML,
            environ={},
            repo_root=REPO_ROOT,
            code_revision="deadbeef",
            now=_T0,
            cache_root=cache_root,
            write_outputs=False,
        )
        by_id = {r.spec.probe_id: r for r in report.probes}
        assert (
            by_id["fundamentals-metrics-pit"].classification
            is EndpointClassification.WORKING
        )
        assert by_id["fundamentals-metrics-pit"].from_cache
        assert (
            by_id["global-prices-prices"].classification
            is EndpointClassification.NOT_CAPTURED
        )
        assert report.live_calls == 0
        # hand-computable overlap: pit={SALES,PIT_ONLY} non={SALES,ASSETS,STD_ONLY}
        assert report.overlap is not None
        assert report.overlap.intersection == 1
        assert report.overlap.pit_only == 1
        assert report.overlap.non_pit_only == 2
        assert report.fundamentals_pit_summary is not None
        assert report.fundamentals_pit_summary.total == 2
        assert report.estimates_summary is not None
        assert report.estimates_summary.total == 2


class TestLiveMode:
    def _run(self, tmp_path: Path) -> tuple[Any, FakeSender, dict[str, str]]:
        environ = _live_environ(tmp_path)
        sender = FakeSender(_scripted_responses())
        report = run_discovery(
            config_path=TRIAL_YAML,
            environ=environ,
            repo_root=REPO_ROOT,
            code_revision="deadbeef",
            now=_T0,
            live=True,
            sender=sender,
        )
        return report, sender, environ

    def test_classifications_follow_the_ea_vocabulary(self, tmp_path: Path) -> None:
        report, sender, _ = self._run(tmp_path)
        by_id = {r.spec.probe_id: r for r in report.probes}
        assert (
            by_id["symbology-identifier-resolution"].classification
            is EndpointClassification.WORKING
        )
        assert (
            by_id["estimates-fixed-consensus"].classification
            is EndpointClassification.PARTIALLY_WORKING
        )
        assert by_id["estimates-fixed-consensus"].row_count == 0
        assert (
            by_id["rbics-entity-focus"].classification
            is EndpointClassification.UNAUTHORIZED
        )
        assert by_id["rbics-entity-focus"].http_status == 403
        assert (
            by_id["benchmarks-constituents"].classification
            is EndpointClassification.UNAVAILABLE
        )
        assert by_id["benchmarks-constituents"].http_status == 404
        assert (
            by_id["benchmarks-index-snapshot"].classification
            is EndpointClassification.REQUIRES_CLARIFICATION
        )
        assert len(sender.calls) == 15  # one wire call per probe, none extra

    def test_budget_and_catalog_accounting(self, tmp_path: Path) -> None:
        report, _, environ = self._run(tmp_path)
        assert report.live_calls == 15  # <= charter budget by two orders
        assert report.overlap is not None
        assert report.overlap.pit_total == 2
        assert report.overlap.non_pit_total == 3
        assert report.overlap.intersection == 1
        assert report.overlap.union == 4
        data_root = Path(environ[ENV_TRIAL_DATA_ROOT])
        for name in (
            "fundamentals_metrics_pit",
            "fundamentals_metrics_non_pit",
            "estimates_metrics",
        ):
            payload = json.loads(
                (data_root / "catalogs" / "fs024" / f"{name}.json").read_text(
                    encoding="utf-8"
                )
            )
            assert payload["row_count"] >= 2
            assert len(payload["request_hash"]) == 64
        manifest = json.loads(
            (data_root / "runs" / "fs024-discovery" / "manifest.json").read_text(
                encoding="utf-8"
            )
        )
        assert manifest["code_revision"] == "deadbeef"
        assert manifest["entitlement_results"]["rbics:/entity-focus"] == "FORBIDDEN"

    def test_rerun_is_cache_first_minimal_new_quota(self, tmp_path: Path) -> None:
        """Cached SUCCESSES re-serve free; the cached 403 is blocked by
        the error-cache policy (fresh entitlement evidence); the cached
        404/400 CLIENT evidence never blocks (D-020(d): only auth/
        entitlement evidence blocks), so exactly those two re-attempt."""
        _report1, _, environ = self._run(tmp_path)
        sender = FakeSender(
            [
                HttpResponse(status=404, body=_error_body("Not found"), headers={}),
                HttpResponse(
                    status=400,
                    body=_error_body("Bad request: unclear reason"),
                    headers={},
                ),
            ]
        )
        report2 = run_discovery(
            config_path=TRIAL_YAML,
            environ=environ,
            repo_root=REPO_ROOT,
            code_revision="deadbeef",
            now=_T0,
            live=True,
            sender=sender,
        )
        assert len(sender.calls) == 2  # ONLY the client-error probes re-issue
        assert report2.live_calls == 2
        by_id = {r.spec.probe_id: r for r in report2.probes}
        assert (
            by_id["rbics-entity-focus"].classification
            is EndpointClassification.UNAUTHORIZED  # error-cache policy, 0 quota
        )
        assert (
            by_id["symbology-identifier-resolution"].classification
            is EndpointClassification.WORKING  # cache hit, 0 quota
        )
        assert by_id["symbology-identifier-resolution"].from_cache

    def test_no_credential_material_anywhere(self, tmp_path: Path) -> None:
        report, _, environ = self._run(tmp_path)
        markdown = render_entitlements_markdown(report)
        assert _CANARY_USER not in markdown and _CANARY_KEY not in markdown
        data_root = Path(environ[ENV_TRIAL_DATA_ROOT])
        for path in data_root.rglob("*.json"):
            text = path.read_text(encoding="utf-8")
            assert _CANARY_USER not in text, path
            assert _CANARY_KEY not in text, path


class TestMarkdownRendering:
    def test_matrix_and_catalog_tables_render(self, tmp_path: Path) -> None:
        environ = _live_environ(tmp_path)
        sender = FakeSender(_scripted_responses())
        report = run_discovery(
            config_path=TRIAL_YAML,
            environ=environ,
            repo_root=REPO_ROOT,
            code_revision="deadbeef",
            now=_T0,
            live=True,
            sender=sender,
        )
        markdown = render_entitlements_markdown(report)
        assert "# FactSet Trial — Entitlement Matrix" in markdown
        assert "| symbology |" in markdown
        assert "**Working**" in markdown
        assert "**Unauthorized**" in markdown
        assert "PIT vs NON-PIT dictionary overlap" in markdown
        assert "| PIT dictionary size | 2 |" in markdown
        assert "| NON-PIT dictionary size | 3 |" in markdown
        assert "VF-FS010-3" in markdown  # deferred reasons are explicit
        # full 64-hex lineage hashes, never truncated (D-020(d))
        for r in report.probes:
            assert len(r.request_hash) == 64


class TestReplayErrorEvidence:
    """F-009 offline shape: cached ERROR captures classify in replay —
    displayed as evidence, never replayed as success."""

    def test_cached_403_classifies_unauthorized_in_replay(self, tmp_path: Path) -> None:
        cache_root = tmp_path / "raw"
        cache = ResponseCache(cache_root)
        config = load_trial_config(TRIAL_YAML)
        plan = {spec.probe_id: spec for spec in build_probe_plan(config)}
        # F-009 shape: plain-text 403 body (undocumented THIRD envelope)
        cache.store(
            plan["symbology-historical-identifier-resolution"].request,
            b"User Authorization Failed",
            http_status=403,
            retrieval_time=_T0,
        )
        report = run_discovery(
            config_path=TRIAL_YAML,
            environ={},
            repo_root=REPO_ROOT,
            code_revision="deadbeef",
            now=_T0,
            cache_root=cache_root,
            write_outputs=False,
        )
        by_id = {r.spec.probe_id: r for r in report.probes}
        result = by_id["symbology-historical-identifier-resolution"]
        assert result.classification is EndpointClassification.UNAUTHORIZED
        assert result.http_status == 403
        assert result.from_cache
        assert result.capture_id is not None
        assert "never replayed as success" in result.detail
        assert report.live_calls == 0

    def test_cached_5xx_classifies_unavailable_in_replay(self, tmp_path: Path) -> None:
        cache_root = tmp_path / "raw"
        cache = ResponseCache(cache_root)
        config = load_trial_config(TRIAL_YAML)
        plan = {spec.probe_id: spec for spec in build_probe_plan(config)}
        cache.store(
            plan["rbics-structure"].request,
            _error_body("upstream broke"),
            http_status=503,
            retrieval_time=_T0,
        )
        report = run_discovery(
            config_path=TRIAL_YAML,
            environ={},
            repo_root=REPO_ROOT,
            code_revision="deadbeef",
            now=_T0,
            cache_root=cache_root,
            write_outputs=False,
        )
        by_id = {r.spec.probe_id: r for r in report.probes}
        assert (
            by_id["rbics-structure"].classification
            is EndpointClassification.UNAVAILABLE
        )

    def test_success_capture_beats_error_evidence(self, tmp_path: Path) -> None:
        """A SUCCESS capture replays as success even when older error
        evidence exists for the same request (latest_success wins)."""
        cache_root = tmp_path / "raw"
        cache = ResponseCache(cache_root)
        config = load_trial_config(TRIAL_YAML)
        plan = {spec.probe_id: spec for spec in build_probe_plan(config)}
        request = plan["benchmarks-id-list"].request
        cache.store(request, b"boom", http_status=500, retrieval_time=_T0)
        cache.store(request, _data_body(2), http_status=200, retrieval_time=_T0)
        report = run_discovery(
            config_path=TRIAL_YAML,
            environ={},
            repo_root=REPO_ROOT,
            code_revision="deadbeef",
            now=_T0,
            cache_root=cache_root,
            write_outputs=False,
        )
        by_id = {r.spec.probe_id: r for r in report.probes}
        assert (
            by_id["benchmarks-id-list"].classification is EndpointClassification.WORKING
        )


class TestForceRefreshRerun:
    def test_force_refresh_reissues_every_probe_live(self, tmp_path: Path) -> None:
        """The post-restoration single bounded re-run (F-009/VENDOR-1):
        force_refresh bypasses success cache AND the error-cache block,
        so all 15 probes go back to the wire exactly once."""
        environ = _live_environ(tmp_path)
        first = FakeSender(_scripted_responses())
        run_discovery(
            config_path=TRIAL_YAML,
            environ=environ,
            repo_root=REPO_ROOT,
            code_revision="deadbeef",
            now=_T0,
            live=True,
            sender=first,
        )
        # restoration: everything answers 200 now
        healthy: list[HttpResponse] = []
        for response in _scripted_responses():
            if response.status == 200:
                healthy.append(response)
            else:
                healthy.append(HttpResponse(status=200, body=_data_body(1), headers={}))
        second = FakeSender(healthy)
        report = run_discovery(
            config_path=TRIAL_YAML,
            environ=environ,
            repo_root=REPO_ROOT,
            code_revision="deadbeef",
            now=_T0,
            live=True,
            sender=second,
            force_refresh=True,
        )
        assert len(second.calls) == 15
        assert report.live_calls == 15
        assert all(
            r.classification
            in (
                EndpointClassification.WORKING,
                EndpointClassification.PARTIALLY_WORKING,
            )
            for r in report.probes
        )


class TestAccountBlockRendering:
    def test_account_block_overrides_family_status(self, tmp_path: Path) -> None:
        report = run_discovery(
            config_path=TRIAL_YAML,
            environ={},
            repo_root=REPO_ROOT,
            code_revision="deadbeef",
            now=_T0,
            cache_root=tmp_path / "raw",
        )
        markdown = render_entitlements_markdown(
            report,
            account_block=("F-009: authorization revoked between 12:45Z and 19:23Z."),
        )
        assert markdown.count("**BLOCKED_BY_ACCOUNT_AUTHORIZATION**") == len(
            FAMILY_OPERATION_TOTALS
        )
        assert "ACCOUNT AUTHORIZATION BLOCK" in markdown
        assert "F-009" in markdown
        assert "force_refresh=True" in markdown  # completion path documented

    def test_no_block_keeps_observed_verdicts(self, tmp_path: Path) -> None:
        report = run_discovery(
            config_path=TRIAL_YAML,
            environ={},
            repo_root=REPO_ROOT,
            code_revision="deadbeef",
            now=_T0,
            cache_root=tmp_path / "raw",
        )
        markdown = render_entitlements_markdown(report)
        assert "BLOCKED_BY_ACCOUNT_AUTHORIZATION" not in markdown
