"""Cross-layer bindings: config discriminators == canonical schema enums.

The config layer may not import ``lasr.data.schemas`` (system_design.md §4:
config imports only core), so the binding between the ``KernelConfig``
union and ``ExpertSpec.learner`` (G017: ``ExpertSpec`` is canonical,
``ComponentSpec`` retired) is enforced HERE, where both layers are
importable. If either side renames a generation or selector, this module
fails.
"""

from __future__ import annotations

import typing

import pytest

from lasr.config import (
    ComponentConfig,
    ExecutionConfig,
    HedgeBackcastComponent,
    KernelConfig,
    LinearFitNonnegKernel,
    PiecewiseConstantKernel,
    PiecewiseLinearInterpKernel,
    SelectionConfig,
)
from lasr.core.timing import ExecutionMode
from lasr.data.schemas.ensemble import (
    HedgeBackcastSelectorSpec,
    KernelType,
    SampleSelectorSpec,
)

pytestmark = pytest.mark.unit


def _discriminator_values(union: object) -> set[str]:
    """The ``type`` Literal values of a discriminated union's variants."""
    inner = typing.get_args(union)[0]  # strip Annotated
    values: set[str] = set()
    for variant in typing.get_args(inner):
        literal = variant.model_fields["type"].annotation
        (value,) = typing.get_args(literal)
        values.add(value)
    return values


class TestKernelBinding:
    def test_kernel_union_binds_expert_spec_learner(self) -> None:
        # G017 binding: KernelConfig discriminators == KernelType values,
        # the generation key carried by ExpertSpec.learner (CR-007).
        assert _discriminator_values(KernelConfig) == {k.value for k in KernelType}

    def test_three_generations_exactly(self) -> None:
        inner = typing.get_args(KernelConfig)[0]
        assert set(typing.get_args(inner)) == {
            PiecewiseConstantKernel,
            PiecewiseLinearInterpKernel,
            LinearFitNonnegKernel,
        }


class TestComponentBinding:
    def test_component_union_binds_sample_selector_spec(self) -> None:
        # Config component discriminators == canonical SampleSelectorSpec
        # types (training_and_artifacts.md §3 table: the complete selector
        # set for the seven specs — no others).
        assert _discriminator_values(ComponentConfig) == _discriminator_values(
            SampleSelectorSpec
        )

    def test_hedge_metric_vocabulary_matches_canonical(self) -> None:
        # The config leaf is Param[Literal[...]]; unwrap to the Literal.
        metric_param = HedgeBackcastComponent.model_fields[
            "selection_metric"
        ].annotation
        assert metric_param is not None
        config_literal = metric_param.model_fields["value"].annotation
        canonical_literal = HedgeBackcastSelectorSpec.model_fields[
            "selection_metric"
        ].annotation
        assert set(typing.get_args(config_literal)) == set(
            typing.get_args(canonical_literal)
        )
        # CR-003's three rules, exactly.
        assert set(typing.get_args(config_literal)) == {
            "backcast_ic_threshold",
            "bottom_half_model_ic",
            "bottom_half_aggregate_pnl",
        }


class TestSelectionUnion:
    def test_two_objectives_exactly(self) -> None:
        # CR-008: min_z vs max_weighted_corr — never substituted.
        assert _discriminator_values(SelectionConfig) == {
            "min_z",
            "max_weighted_corr",
        }


class TestExecutionBinding:
    def test_execution_mode_is_the_shared_core_enum(self) -> None:
        # CI-014: training labels and evaluation share one timing enum.
        mode_param = ExecutionConfig.model_fields["mode"].annotation
        assert mode_param is not None
        value_ann = mode_param.model_fields["value"].annotation
        assert value_ann is ExecutionMode

    def test_mode_values_are_the_cr018_set(self) -> None:
        assert {m.value for m in ExecutionMode} == {
            "same_close",
            "one_day_lag",
            "next_open",
            "t_plus_k_moc",
        }
