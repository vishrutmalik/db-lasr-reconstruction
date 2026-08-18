"""FS026/D-021 reviewed access-plan model and request matching."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from lasr.data.providers.factset.capabilities import (
    AccessDisposition,
    FactSetAccessPlan,
    FactSetAccessPolicyConflictError,
    FactSetCapabilityExcludedError,
    access_plan_hash,
    access_plan_snapshot,
)
from lasr.data.providers.factset.config import load_trial_config
from lasr.data.providers.factset.discovery_requests import (
    build_benchmark_constituents_probe_request,
    build_index_snapshot_probe_request,
)
from lasr.data.providers.factset.errors import FactSetAuthError, FactSetTransportError
from lasr.data.providers.factset.request_norm import NormalizedRequest
from lasr.data.providers.factset.symbology_models import (
    build_historical_resolution_request,
    build_identifier_resolution_request,
)

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
TRIAL_YAML = REPO_ROOT / "configs" / "factset" / "trial.yaml"
_D0 = date(2024, 6, 14)


def _plan() -> FactSetAccessPlan:
    return load_trial_config(TRIAL_YAML).access_plan


def _historical() -> NormalizedRequest:
    return build_historical_resolution_request(
        ids=["AAPL-US"],
        input_symbol_type="tickerRegion",
        output_symbol_types=["CUSIP"],
    )


class TestCommittedOverlay:
    def test_initial_overlay_is_exactly_six_reviewed_exclusions(self) -> None:
        plan = _plan()
        assert plan.version == "d021-fs026-1"
        assert len(plan.entries) == 6
        assert {
            entry.disposition for entry in plan.entries
        } == {AccessDisposition.ASSUMED_NOT_PROVISIONED}
        assert all("D-021" in entry.evidence_refs for entry in plan.entries)

    def test_historical_is_excluded_for_every_parameter_variant(self) -> None:
        with pytest.raises(FactSetCapabilityExcludedError, match="D-021") as caught:
            _plan().preflight(_historical())
        assert isinstance(caught.value, FactSetTransportError)

    @pytest.mark.parametrize("market_id", ["CUSIP", "ISIN", "SEDOL"])
    def test_current_market_id_direction_is_input_safe_output_blocked(
        self, market_id: str
    ) -> None:
        plan = _plan()
        input_to_fsym = build_identifier_resolution_request(
            ids=["037833100"],
            input_symbol_type=market_id,
            output_symbol_types=["fsymSecurityId"],
        )
        assert plan.disposition_for(input_to_fsym) is AccessDisposition.UNASSESSED
        plan.preflight(input_to_fsym)

        outward = build_identifier_resolution_request(
            ids=["AAPL-US"], output_symbol_types=[market_id]
        )
        with pytest.raises(FactSetCapabilityExcludedError):
            plan.preflight(outward)

    def test_bundled_output_order_and_duplicates_cannot_bypass(self) -> None:
        request = NormalizedRequest(
            api_family="symbology",
            api_version="v3",
            endpoint="/identifier-resolution",
            verb="POST",
            params={
                "ids": ["AAPL-US"],
                "inputSymbolType": "tickerRegion",
                "outputSymbolTypes": ["fsymSecurityId", "SEDOL", "CUSIP", "SEDOL"],
            },
        )
        with pytest.raises(FactSetCapabilityExcludedError) as caught:
            _plan().preflight(request)
        assert len(caught.value.identities) == 2

    def test_benchmark_exclusions_have_exact_variant_boundaries(self) -> None:
        plan = _plan()
        constituents = build_benchmark_constituents_probe_request(
            benchmark_id="SP50", as_of=_D0
        )
        snapshot = build_index_snapshot_probe_request(ids=["SP50"], as_of=_D0)
        with pytest.raises(FactSetCapabilityExcludedError):
            plan.preflight(constituents)
        with pytest.raises(FactSetCapabilityExcludedError):
            plan.preflight(snapshot)

        for changed in (
            NormalizedRequest(
                **{
                    **constituents.__dict__,
                    "params": {**constituents.params, "ids": ["SP100"]},
                }
            ),
            NormalizedRequest(
                **{
                    **constituents.__dict__,
                    "params": {**constituents.params, "date": "2024-06-17"},
                }
            ),
            NormalizedRequest(
                **{
                    **constituents.__dict__,
                    "params": {**constituents.params, "extra": "not-generalized"},
                }
            ),
        ):
            assert plan.disposition_for(changed) is AccessDisposition.UNASSESSED
            plan.preflight(changed)


class TestEvidencePolicySeparation:
    def test_403_is_inert_and_does_not_mutate_plan(self) -> None:
        plan = _plan()
        before_snapshot = access_plan_snapshot(plan)
        before_hash = access_plan_hash(plan)
        plan.reconcile_observed_status(_historical(), 403)
        assert access_plan_snapshot(plan) == before_snapshot
        assert access_plan_hash(plan) == before_hash

    def test_401_aborts_account_level_reconciliation(self) -> None:
        with pytest.raises(FactSetAuthError, match="account-level"):
            _plan().reconcile_observed_status(_historical(), 401)

    def test_later_success_is_a_loud_review_conflict(self) -> None:
        with pytest.raises(FactSetAccessPolicyConflictError, match="D-021"):
            _plan().reconcile_observed_status(_historical(), 200)

    def test_unassessed_success_does_not_promote_policy(self) -> None:
        plan = _plan()
        request = build_identifier_resolution_request(
            ids=["AAPL-US"], output_symbol_types=["fsymSecurityId"]
        )
        before = access_plan_hash(plan)
        plan.reconcile_observed_status(request, 200)
        assert plan.disposition_for(request) is AccessDisposition.UNASSESSED
        assert access_plan_hash(plan) == before

    def test_plan_is_deeply_immutable(self) -> None:
        plan = _plan()
        with pytest.raises(ValidationError):
            plan.entries[0].key.request_variant.parameters[0].name = "changed"  # type: ignore[misc]


class TestValidation:
    @pytest.mark.parametrize(
        ("field", "value"),
        [("family", "Symbology"), ("verb", "post"), ("path", "/bad/")],
    )
    def test_key_axes_are_normalized(self, field: str, value: str) -> None:
        entry = access_plan_snapshot(_plan())["entries"][0]
        assert isinstance(entry, dict)
        key = entry["key"]
        assert isinstance(key, dict)
        key[field] = value
        with pytest.raises(ValidationError):
            FactSetAccessPlan.model_validate(
                {
                    "version": "bad",
                    "entries": [entry],
                }
            )

    def test_duplicate_capability_identity_is_rejected(self) -> None:
        entry = access_plan_snapshot(_plan())["entries"][0]
        with pytest.raises(ValidationError, match="duplicate capability"):
            FactSetAccessPlan.model_validate(
                {"version": "bad", "entries": [entry, entry]}
            )
