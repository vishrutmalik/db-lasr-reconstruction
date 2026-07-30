"""Feature registry tests (G022): MP §18 enforcement + list machinery.

Covers: the MP §18 field-by-field enforcement inventory, duplicate and
undeclared-field registration refusal, named-list resolution (CR-016
machinery), the lineage hash, and the audited library's composition
(CI-028 flag plumbing; evidence traceability).
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from typing import ClassVar

import pytest

from lasr.config.sections import NeutralizationConfig, PreprocessingConfig
from lasr.data.schemas.features import FeatureSpec
from lasr.features.computation import FeatureContext, RawObservation
from lasr.features.library import (
    AUDITED_LIBRARY_LIST_ID,
    build_default_registry,
    library_feature_keys,
)
from lasr.features.registry import FeatureRegistry, FeatureRegistryError
from lasr.features.source_fields import SourceFieldCatalog, SourceFieldError

pytestmark = pytest.mark.unit


def toy_spec(**overrides: object) -> FeatureSpec:
    """A fully-populated valid spec; tests override single fields."""
    base: dict[str, object] = {
        "feature_id": "toy_close",
        "version": 1,
        "category": "technical",
        "direction": "learned",
        "required_fields": ("prices_daily.close",),
        "formula": "last knowable close (toy)",
        "units": "currency",
        "frequency": "daily",
        "min_coverage": 0.5,
        "publication_lag": timedelta(0),
        "missing_policy": "exclude",
        "outlier_policy": "none_rank_handles",
        "neutralize": True,
        "monotonicity": "unknown",
        "evidence_source": "test fixture (no paper claim)",
        "availability": "derived",
        "provenance": "ASSUMED",
    }
    base.update(overrides)
    return FeatureSpec(**base)  # type: ignore[arg-type]


def _noop_kernel(
    ctx: FeatureContext, securities: frozenset[str]
) -> dict[str, RawObservation]:
    return {}


class TestMp18Enforcement:
    """MP §18: 'Every feature must specify' — one attribute per bullet."""

    #: MP §18 bullet -> FeatureSpec attribute. Split-home bullets
    #: (documented in lasr/features/registry.py):
    #: - ranking method: rank IS the outlier policy (P1-09); the mechanism
    #:   (rank_method/tie_rule/direction) is version-keyed
    #:   PreprocessingConfig, executed by lasr.features.transforms;
    #: - neutralization method: per-feature `neutralize` flag (CI-028);
    #:   mechanism is version-keyed NeutralizationConfig (CR-004);
    #: - eligibility: min_coverage is the engine's coverage gate.
    MP18_FIELD_MAP: ClassVar[dict[str, str]] = {
        "name": "feature_id",
        "version": "version",
        "economic category": "category",
        "direction or orientation": "direction",
        "required source fields": "required_fields",
        "formula": "formula",
        "units": "units",
        "frequency": "frequency",
        "minimum coverage": "min_coverage",
        "publication lag": "publication_lag",
        "missing-value policy": "missing_policy",
        "outlier policy": "outlier_policy",
        "ranking method": "outlier_policy",
        "neutralization method": "neutralize",
        "eligibility requirements": "min_coverage",
        "expected monotonicity": "monotonicity",
        "evidence source": "evidence_source",
        "availability classification": "availability",
    }

    def test_every_mp18_bullet_maps_to_a_spec_field(self):
        declared = {f.name for f in dataclasses.fields(FeatureSpec)}
        for bullet, attribute in self.MP18_FIELD_MAP.items():
            assert attribute in declared, f"MP §18 {bullet!r} has no home"

    def test_every_spec_field_is_mandatory(self):
        """No MP §18 field can be silently defaulted: FeatureSpec declares
        no default for any field."""
        for spec_field in dataclasses.fields(FeatureSpec):
            assert spec_field.default is dataclasses.MISSING
            assert spec_field.default_factory is dataclasses.MISSING

    def test_split_home_mechanisms_exist_in_version_config(self):
        """The version-keyed halves of 'ranking method' and 'neutralization
        method' are named config fields (CI-044: no hidden defaults)."""
        preprocessing = set(PreprocessingConfig.model_fields)
        assert {"rank_method", "rank_direction", "tie_rule"} <= preprocessing
        assert "mechanism" in set(NeutralizationConfig.model_fields)

    def test_spec_refuses_blank_formula_and_evidence(self):
        with pytest.raises(ValueError, match="formula"):
            toy_spec(formula="")
        with pytest.raises(ValueError, match="evidence"):
            toy_spec(evidence_source="")

    def test_spec_refuses_bad_coverage_lag_version(self):
        with pytest.raises(ValueError, match="min_coverage"):
            toy_spec(min_coverage=1.5)
        with pytest.raises(ValueError, match="publication_lag"):
            toy_spec(publication_lag=timedelta(days=-1))
        with pytest.raises(ValueError, match="version"):
            toy_spec(version=0)


class TestRegistrationEnforcement:
    def test_duplicate_registration_refused(self):
        registry = FeatureRegistry()
        registry.register(toy_spec(), _noop_kernel)
        with pytest.raises(FeatureRegistryError, match="already registered"):
            registry.register(toy_spec(), _noop_kernel)

    def test_same_id_new_version_is_a_distinct_key(self):
        registry = FeatureRegistry()
        registry.register(toy_spec(version=1), _noop_kernel)
        registry.register(toy_spec(version=2), _noop_kernel)
        assert registry.spec("toy_close", 2).version == 2

    def test_undeclared_table_refused(self):
        registry = FeatureRegistry()
        with pytest.raises(SourceFieldError, match="unknown canonical table"):
            registry.register(
                toy_spec(required_fields=("no_such_table.close",)), _noop_kernel
            )

    def test_undeclared_column_refused(self):
        registry = FeatureRegistry()
        with pytest.raises(SourceFieldError, match="undeclared column"):
            registry.register(
                toy_spec(required_fields=("prices_daily.adjusted_close",)),
                _noop_kernel,
            )

    def test_undeclared_metric_refused(self):
        registry = FeatureRegistry()
        with pytest.raises(SourceFieldError, match="undeclared metric"):
            registry.register(
                toy_spec(required_fields=("fundamentals.NO_SUCH_METRIC",)),
                _noop_kernel,
            )

    def test_malformed_field_refused(self):
        registry = FeatureRegistry()
        with pytest.raises(SourceFieldError, match="malformed"):
            registry.register(toy_spec(required_fields=("prices_daily",)), _noop_kernel)

    def test_empty_required_fields_refused(self):
        registry = FeatureRegistry()
        with pytest.raises(FeatureRegistryError, match="no required source"):
            registry.register(toy_spec(required_fields=()), _noop_kernel)

    def test_blank_units_refused(self):
        registry = FeatureRegistry()
        with pytest.raises(FeatureRegistryError, match="blank units"):
            registry.register(toy_spec(units="  "), _noop_kernel)

    def test_unknown_feature_lookup_is_typed_error(self):
        registry = FeatureRegistry()
        with pytest.raises(FeatureRegistryError, match="unknown feature"):
            registry.get("ghost", 1)

    def test_catalog_extension_declares_new_metrics(self):
        catalog = SourceFieldCatalog().with_metrics("fundamentals", {"OCF"})
        registry = FeatureRegistry(catalog)
        registry.register(toy_spec(required_fields=("fundamentals.OCF",)), _noop_kernel)
        assert registry.keys() == (("toy_close", 1),)

    def test_catalog_refuses_unknown_metric_table(self):
        with pytest.raises(SourceFieldError, match="unknown canonical table"):
            SourceFieldCatalog(metric_ids={"no_such_table": frozenset({"X"})})


class TestFeatureLists:
    def _registry(self) -> FeatureRegistry:
        registry = FeatureRegistry()
        registry.register(toy_spec(feature_id="f_a"), _noop_kernel)
        registry.register(toy_spec(feature_id="f_b"), _noop_kernel)
        return registry

    def test_resolution_preserves_declared_order(self):
        registry = self._registry()
        registry.define_list("l1", [("f_b", 1), ("f_a", 1)])
        assert [s.feature_id for s in registry.resolve_list("l1")] == ["f_b", "f_a"]
        assert registry.list_members("l1") == (("f_b", 1), ("f_a", 1))

    def test_unknown_list_is_typed_error(self):
        registry = self._registry()
        with pytest.raises(FeatureRegistryError, match="unknown feature list"):
            registry.resolve_list("p1_fig11_us70")  # future registry content

    def test_unregistered_member_refused_at_definition(self):
        registry = self._registry()
        with pytest.raises(FeatureRegistryError, match="unregistered"):
            registry.define_list("l1", [("f_a", 1), ("ghost", 1)])

    def test_duplicate_list_id_refused(self):
        registry = self._registry()
        registry.define_list("l1", [("f_a", 1)])
        with pytest.raises(FeatureRegistryError, match="already defined"):
            registry.define_list("l1", [("f_b", 1)])

    def test_duplicate_member_refused(self):
        registry = self._registry()
        with pytest.raises(FeatureRegistryError, match="repeats member"):
            registry.define_list("l1", [("f_a", 1), ("f_a", 1)])

    def test_empty_list_refused(self):
        registry = self._registry()
        with pytest.raises(FeatureRegistryError, match="empty"):
            registry.define_list("l1", [])


class TestRegistryHash:
    def test_identical_content_identical_hash(self):
        assert (
            build_default_registry().registry_hash()
            == build_default_registry().registry_hash()
        )

    def test_registration_order_does_not_change_hash(self):
        r1, r2 = FeatureRegistry(), FeatureRegistry()
        a, b = toy_spec(feature_id="f_a"), toy_spec(feature_id="f_b")
        r1.register(a, _noop_kernel)
        r1.register(b, _noop_kernel)
        r2.register(b, _noop_kernel)
        r2.register(a, _noop_kernel)
        assert r1.registry_hash() == r2.registry_hash()

    def test_spec_change_changes_hash(self):
        r1, r2 = FeatureRegistry(), FeatureRegistry()
        r1.register(toy_spec(), _noop_kernel)
        r2.register(toy_spec(formula="a DIFFERENT formula"), _noop_kernel)
        assert r1.registry_hash() != r2.registry_hash()

    def test_list_change_changes_hash(self):
        r1, r2 = FeatureRegistry(), FeatureRegistry()
        for r in (r1, r2):
            r.register(toy_spec(feature_id="f_a"), _noop_kernel)
        r2.define_list("l1", [("f_a", 1)])
        assert r1.registry_hash() != r2.registry_hash()


class TestAuditedLibraryComposition:
    """The small audited library (MP §18: 'begin with a small audited
    feature library'), feature-by-feature registry checks."""

    EXPECTED_IDS = (
        "momentum_12_1",
        "reversal_1m",
        "size_neg_log_mcap",
        "book_to_price",
        "earnings_yield",
        "eps_revision_3m",
        "volatility_60d",
        "adv_dollar_20d",
        "asset_growth_1y",
    )

    def test_library_is_small_and_complete(self):
        registry = build_default_registry()
        assert library_feature_keys() == tuple((f, 1) for f in self.EXPECTED_IDS)
        assert len(registry.keys()) == 9  # MP §18: small, not dozens
        resolved = registry.resolve_list(AUDITED_LIBRARY_LIST_ID)
        assert tuple(s.feature_id for s in resolved) == self.EXPECTED_IDS

    def test_ci028_neutralize_flag_plumbing(self):
        """CI-028: every feature carries an explicit neutralize flag; the
        technical family (momentum / volatility / market cap, E-P4-06)
        is exempt, everything else is neutralizable."""
        registry = build_default_registry()
        exempt = {"momentum_12_1", "volatility_60d", "size_neg_log_mcap"}
        for spec in registry.resolve_list(AUDITED_LIBRARY_LIST_ID):
            assert isinstance(spec.neutralize, bool)
            assert spec.neutralize is (spec.feature_id not in exempt)

    def test_every_feature_traces_to_field_mapping(self):
        registry = build_default_registry()
        for spec in registry.resolve_list(AUDITED_LIBRARY_LIST_ID):
            assert "field_mapping" in spec.evidence_source, spec.feature_id
            assert spec.formula, spec.feature_id
            assert spec.provenance in {"INFERRED", "ASSUMED"}, spec.feature_id

    def test_category_coverage(self):
        registry = build_default_registry()
        categories = {
            s.category for s in registry.resolve_list(AUDITED_LIBRARY_LIST_ID)
        }
        assert categories == {
            "momentum",
            "reversal",
            "technical",
            "value",
            "revisions",
            "volatility",
            "liquidity",
            "growth",
        }

    def test_estimates_feature_flagged_synthetic_only(self):
        """eps_revision_3m: estimate history does not exist on the real
        provider surface (gap §4) — availability must say so."""
        spec = build_default_registry().spec("eps_revision_3m", 1)
        assert spec.availability == "unavailable_pending_data"

    def test_fundamental_features_carry_publication_lag(self):
        """CI-005 plumbing: statement-based features declare the 90d lag;
        price-only features declare none."""
        registry = build_default_registry()
        lags = {
            s.feature_id: s.publication_lag
            for s in registry.resolve_list(AUDITED_LIBRARY_LIST_ID)
        }
        for lagged in ("book_to_price", "earnings_yield", "asset_growth_1y"):
            assert lags[lagged] == timedelta(days=90)
        for unlagged in ("momentum_12_1", "reversal_1m", "volatility_60d"):
            assert lags[unlagged] == timedelta(0)

    def test_policies_are_the_cited_paper_policies(self):
        """P1-09: rank is the outlier treatment; CI-021: exclude, never
        impute — uniform across the audited library."""
        registry = build_default_registry()
        for spec in registry.resolve_list(AUDITED_LIBRARY_LIST_ID):
            assert spec.missing_policy == "exclude"
            assert spec.outlier_policy == "none_rank_handles"
            assert spec.min_coverage == 0.5


class TestSpecTimeOrdering:
    def test_feature_value_row_rejects_inverted_times(self):
        """CI-005 ordering on the stored row (schema-level, exercised here
        because the engine constructs these rows)."""
        from lasr.data.schemas.features import FeatureValueRow

        with pytest.raises(ValueError, match="precedes observation_time"):
            FeatureValueRow(
                feature_id="toy",
                feature_version=1,
                security_id="SEC-A",
                observation_time=datetime(2021, 6, 2, tzinfo=UTC),
                knowledge_time=datetime(2021, 6, 1, tzinfo=UTC),
                value=1.0,
            )
