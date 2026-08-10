"""Temporal experts, sample selectors, aggregation rules (G025).

# arch: training_and_artifacts.md §3. Selectors pick realized training
periods (CI-011), :func:`train_ensemble` trains every roster component
under the spec's ONE shared hyperparameter set (E-P4-14; epsilon/rounds
inheritance stays config-visible, CR-010/CR-011), and the combination
layer applies the version's evidenced rules (CR-005; CI-007/CI-022).
"""

from lasr.models.ensembles.combine import (
    ComponentICRecord,
    apply_hedge_weight_rule,
    combine_component_scores,
    ensemble_weights,
    equal_weights,
    seasonal_rank_ic_weights,
    zscore_with_universe,
)
from lasr.models.ensembles.experts import (
    PeriodBlock,
    TrainedEnsemble,
    TrainedExpert,
    TrainingHistory,
    build_training_components,
    pool_training_matrix,
    train_ensemble,
)
from lasr.models.ensembles.scoring import (
    ScoringPanel,
    blend_sub_models,
    score_ensemble,
    score_experts,
)
from lasr.models.ensembles.selectors import (
    EnsembleError,
    HedgeBackcastSelector,
    PeriodHistory,
    PreviousPeriodSelector,
    SampleSelector,
    SeasonalSameMonthSelector,
    TrailingWindowSelector,
    TrainingPeriod,
    build_selector,
    component_expert_name,
)

__all__ = [
    "ComponentICRecord",
    "EnsembleError",
    "HedgeBackcastSelector",
    "PeriodBlock",
    "PeriodHistory",
    "PreviousPeriodSelector",
    "SampleSelector",
    "ScoringPanel",
    "SeasonalSameMonthSelector",
    "TrailingWindowSelector",
    "TrainedEnsemble",
    "TrainedExpert",
    "TrainingHistory",
    "TrainingPeriod",
    "apply_hedge_weight_rule",
    "blend_sub_models",
    "build_selector",
    "build_training_components",
    "combine_component_scores",
    "component_expert_name",
    "ensemble_weights",
    "equal_weights",
    "pool_training_matrix",
    "score_ensemble",
    "score_experts",
    "seasonal_rank_ic_weights",
    "train_ensemble",
    "zscore_with_universe",
]
