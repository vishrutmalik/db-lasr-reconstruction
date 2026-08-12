"""Formula-level unit tests for the G029 pipeline stages."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time
from pathlib import Path

import pytest

from lasr.config.experiment import DateRange as ConfigDateRange
from lasr.config.experiment import (
    ExperimentConfig,
    Override,
    PipelineRunSettings,
    ProviderConfig,
    WalkForwardSettings,
)
from lasr.config.provenance import Provenance
from lasr.pipeline.data_stage import (
    _merge_interval_vintages,
    _vintage_waves,
    scenario_from_experiment,
)
from lasr.pipeline.errors import PipelineConfigError, PipelineError
from lasr.pipeline.experiment import (
    _apply_overrides,
    acceptance_verdict,
    verify_run,
)
from lasr.pipeline.feature_stage import build_pipeline_registry
from lasr.pipeline.model_stage import _rank_ic

pytestmark = pytest.mark.unit

KT = datetime(2005, 1, 31, tzinfo=UTC)
KT2 = datetime(2005, 6, 30, tzinfo=UTC)


def _settings(**overrides: object) -> PipelineRunSettings:
    fields: dict[str, object] = {
        "walkforward": WalkForwardSettings(train_steps=8),
        "session_open_utc": time(14, 30),
        "session_close_utc": time(21, 0),
        "initial_nav": 1000.0,
        "leak_flag_ic_threshold": 0.3,
        "quality_split_jump_rel_tol": 0.35,
    }
    fields.update(overrides)
    return PipelineRunSettings(**fields)  # type: ignore[arg-type]


def _experiment(**overrides: object) -> ExperimentConfig:
    fields: dict[str, object] = {
        "experiment_id": "unit",
        "version_spec": "configs/models/nlasr_2012.yaml",
        "provider": ProviderConfig(
            name="synthetic_generator",
            scenario="baseline",
            params={"n_securities": 8, "n_years": 2},
        ),
        "universe_instance": "SYNIDX01",
        "dates": ConfigDateRange(start=date(2005, 6, 1), end=date(2006, 12, 31)),
        "seed": 1729,
        "artifacts_root": Path("unused"),
        "pipeline": _settings(),
    }
    fields.update(overrides)
    return ExperimentConfig(**fields)  # type: ignore[arg-type]


class TestVintageWaves:
    def test_two_vintages_split_into_two_pk_unique_waves(self) -> None:
        records = [
            {
                "ticker": "A",
                "exchange": "X",
                "delisting_date": None,
                "knowledge_time": KT,
            },
            {
                "ticker": "A",
                "exchange": "X",
                "delisting_date": date(2005, 6, 30),
                "knowledge_time": KT2,
            },
            {
                "ticker": "B",
                "exchange": "X",
                "delisting_date": None,
                "knowledge_time": KT,
            },
        ]
        waves = _vintage_waves(records, ("ticker", "exchange"), ("ticker", "exchange"))
        assert [len(w) for w in waves] == [2, 1]
        assert waves[0][0]["ticker"] == "A" and waves[0][1]["ticker"] == "B"
        assert waves[1][0]["delisting_date"] == date(2005, 6, 30)

    def test_waves_are_input_order_invariant(self) -> None:
        records = [{"ticker": t, "exchange": "X", "knowledge_time": KT} for t in "CAB"]
        forward = _vintage_waves(
            records, ("ticker", "exchange"), ("ticker", "exchange")
        )
        backward = _vintage_waves(
            list(reversed(records)), ("ticker", "exchange"), ("ticker", "exchange")
        )
        assert forward == backward
        assert [r["ticker"] for r in forward[0]] == ["A", "B", "C"]


class TestIntervalVintageMerge:
    def test_open_plus_closure_merge_keeps_the_open_stamp(self) -> None:
        merged = _merge_interval_vintages(
            (
                {
                    "ticker": "A",
                    "exchange": "X",
                    "listing_date": date(2005, 1, 31),
                    "delisting_date": None,
                    "knowledge_time": KT,
                },
                {
                    "ticker": "A",
                    "exchange": "X",
                    "listing_date": date(2005, 1, 31),
                    "delisting_date": date(2005, 6, 30),
                    "knowledge_time": KT2,
                },
            ),
            ("ticker", "exchange", "listing_date"),
            closure_field="delisting_date",
            what="test interval",
        )
        assert len(merged) == 1
        assert merged[0]["delisting_date"] == date(2005, 6, 30)
        assert merged[0]["knowledge_time"] == KT  # open stamp survives

    def test_delayed_closure_publication_is_refused(self) -> None:
        """LT-016/CT-16 shape: a closure published AFTER the interval end
        must not be merged into a row visible before it was knowable."""
        with pytest.raises(PipelineError, match="knowable"):
            _merge_interval_vintages(
                (
                    {
                        "ticker": "A",
                        "exchange": "X",
                        "listing_date": date(2005, 1, 31),
                        "delisting_date": None,
                        "knowledge_time": KT,
                    },
                    {
                        "ticker": "A",
                        "exchange": "X",
                        "listing_date": date(2005, 1, 31),
                        "delisting_date": date(2005, 6, 30),
                        # published 3 months after the exit
                        "knowledge_time": datetime(2005, 9, 30, tzinfo=UTC),
                    },
                ),
                ("ticker", "exchange", "listing_date"),
                closure_field="delisting_date",
                what="test interval",
            )


class TestScenarioResolution:
    def test_experiment_seed_drives_the_world(self) -> None:
        scenario = scenario_from_experiment(_experiment())
        assert scenario.seed == 1729
        assert scenario.n_securities == 8
        assert scenario.scenario_id == "baseline"

    def test_non_synthetic_provider_is_refused(self) -> None:
        experiment = _experiment(
            provider=ProviderConfig(name="local_file", scenario=None)
        )
        with pytest.raises(PipelineConfigError, match="synthetic"):
            scenario_from_experiment(experiment)

    def test_missing_scenario_is_refused(self) -> None:
        experiment = _experiment(
            provider=ProviderConfig(name="synthetic_generator", scenario=None)
        )
        with pytest.raises(PipelineConfigError, match="scenario"):
            scenario_from_experiment(experiment)


class TestOverrides:
    def test_override_lands_as_a_tagged_leaf(self) -> None:
        data = {"features": {"list_id": {"value": "x", "prov": "EXPLICIT", "src": "p"}}}
        out = _apply_overrides(
            data,
            [
                Override(
                    path="features.list_id",
                    value="y",
                    prov=Provenance.ASSUMED,
                    src="test",
                    rationale="unit",
                )
            ],
        )
        leaf = out["features"]["list_id"]
        assert leaf["value"] == "y" and leaf["prov"] == "ASSUMED"

    def test_override_can_create_a_missing_leaf(self) -> None:
        out = _apply_overrides(
            {},
            [
                Override(
                    path="portfolio.gross_exposure",
                    value=2.0,
                    prov=Provenance.ASSUMED,
                    src="test",
                    rationale="unit",
                )
            ],
        )
        assert out["portfolio"]["gross_exposure"]["value"] == 2.0


class TestRankIc:
    def test_hand_value_perfect_and_inverse(self) -> None:
        assert _rank_ic([1.0, 2.0, 3.0], [10.0, 20.0, 30.0]) == pytest.approx(1.0)
        assert _rank_ic([1.0, 2.0, 3.0], [3.0, 2.0, 1.0]) == pytest.approx(-1.0)

    def test_hand_value_partial(self) -> None:
        """ranks x=(0,1,2,3), y=(0,1,3,2): Spearman = 1 - 6*2/(4*15) = 0.8."""
        ic = _rank_ic([1.0, 2.0, 3.0, 4.0], [1.0, 2.0, 9.0, 5.0])
        assert ic == pytest.approx(0.8)

    def test_degenerate_sides_are_none(self) -> None:
        assert _rank_ic([1.0, 1.0, 1.0], [1.0, 2.0, 3.0]) is None


class TestAcceptanceVerdict:
    def test_all_bands_within_and_no_leaks_passes(self) -> None:
        rows = [
            {"status": "evaluated", "within_band": True},
            {"status": "not_evaluated_at_g029"},
        ]
        assert acceptance_verdict(rows, []) is True

    def test_out_of_band_fails(self) -> None:
        rows = [{"status": "evaluated", "within_band": False}]
        assert acceptance_verdict(rows, []) is False

    def test_suspected_leak_blocks_passed_even_when_in_band(self) -> None:
        """LT-004 home: the acceptance gate refuses to mark the run
        passed while a suspected_leak flag is unresolved."""
        rows = [{"status": "evaluated", "within_band": True}]
        assert acceptance_verdict(rows, ["FLEAK"]) is False

    def test_nothing_evaluated_is_never_a_pass(self) -> None:
        assert acceptance_verdict([{"status": "not_evaluated_at_g029"}], []) is False


class TestVerifyRun:
    def test_missing_manifest_is_a_problem(self, tmp_path: Path) -> None:
        assert verify_run(tmp_path) != ()

    def test_hash_mismatch_and_identity_breaks_are_named(self, tmp_path: Path) -> None:
        ledger = {
            "periods": [
                {
                    "index": 0,
                    "nav_start": 1000.0,
                    "nav_end": 1010.0,
                    "gross_pnl": 10.0,
                    "cost": 0.0,
                    "borrow": 0.0,
                    "net_pnl": 10.0,
                    "portfolio_return": 0.01,
                    "check_return": 0.02,  # CI-045 identity broken by hand
                }
            ],
            "final_nav": 1010.0,
        }
        (tmp_path / "ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
        (tmp_path / "manifest.json").write_text(
            json.dumps({"artifacts": {"ledger.json": "0" * 64}}), encoding="utf-8"
        )
        problems = verify_run(tmp_path)
        assert any("hash mismatch" in p for p in problems)
        assert any("CI-045" in p for p in problems)


class TestPipelineRegistry:
    def test_price_list_resolves_and_is_deterministic(self) -> None:
        registry_a = build_pipeline_registry()
        registry_b = build_pipeline_registry()
        specs_a = registry_a.resolve_list("g029_price_features_v1")
        specs_b = registry_b.resolve_list("g029_price_features_v1")
        assert [s.feature_id for s in specs_a] == [
            "g029_mom_12_1_monthly",
            "g029_rev_1m_monthly",
            "size_neg_log_mcap",
        ]
        assert [s.feature_id for s in specs_a] == [s.feature_id for s in specs_b]

    def test_audited_library_list_still_resolves(self) -> None:
        registry = build_pipeline_registry()
        assert len(registry.resolve_list("g022_audited_v1")) == 9


class TestN8FeatureStampBinding:
    """integration_queue N8 (G022 remediation -> G029 persistence
    binding): feature stamps are BATCH properties; the feature-value key
    excludes knowledge_time."""

    def test_feature_values_pk_excludes_knowledge_time(self) -> None:
        from lasr.data.schemas.features import FEATURE_VALUES

        assert "knowledge_time" not in FEATURE_VALUES.primary_key
        assert FEATURE_VALUES.primary_key == (
            "feature_id",
            "feature_version",
            "security_id",
            "observation_time",
        )

    def test_batches_key_one_stamp_beside_unstamped_rows(self) -> None:
        from lasr.pipeline.feature_stage import FeatureBatch

        batch = FeatureBatch(
            feature_id="f",
            feature_version=1,
            as_of=KT2,
            knowledge_time=KT2,
            coverage=1.0,
            values={"S1": (KT, 1.0), "S2": (KT, 2.0)},
        )
        # the stamp is a property of the BATCH: rows carry (observation
        # time, value) only — no per-row knowledge field exists to diverge
        assert batch.knowledge_time == KT2
        for _sid, (observation_time, value) in batch.values.items():
            assert isinstance(observation_time, datetime)
            assert isinstance(value, float)
