"""Feature registry (MP §18): FeatureSpec-keyed registration + named lists.

# arch: system_design.md §2 L-FEAT / canonical_schemas.md §9. The registry
is the single authority mapping ``(feature_id, version)`` to a
:class:`~lasr.data.schemas.features.FeatureSpec` (every MP §18 field, one
attribute each — see the enforcement inventory in
``tests/unit/test_features_registry.py``) plus its computation kernel.

Enforcement at registration time (never later, never silently):

- duplicate ``(feature_id, version)`` refused;
- every ``required_fields`` entry validated against the
  :class:`~lasr.features.source_fields.SourceFieldCatalog` — undeclared
  tables/columns/metric ids refused;
- empty ``required_fields`` / blank ``units`` refused (a feature computed
  from nothing, or with undeclared units, is unauditable).

Named feature lists (CR-016 machinery): a list may only reference
registered features, so every registered list is resolvable by
construction. The historical per-version lists (P1 Fig 11 US-70, Fig 106
global-61, P3 Fig 2 70, P4 114 …) are FUTURE registry content owned by the
version goals (G030..G033); G022 ships the resolution machinery plus the
audited library's own list (``lasr.features.library``).

``registry_hash`` is the lineage identity of registry content (specs +
lists), built on the repo's canonical JSON serialization — identical
content gives identical hashes regardless of registration order.

MP §18 fields with a split home (documented, asserted by the enforcement
inventory test):

- *Ranking method*: ranking IS the declared outlier treatment
  (``outlier_policy="none_rank_handles"``, P1-09); the rank mechanism
  (direction, tie rule, coverage divisor) is version-keyed config
  (``PreprocessingConfig``) executed by ``lasr.features.transforms``.
- *Neutralization method*: the per-feature flag is ``neutralize``
  (CI-028 technical exemption); the mechanism is version-keyed
  (``NeutralizationConfig``, CR-004) and runs downstream of the stored
  pre-neutralization values (D-007).
- *Eligibility requirements*: ``min_coverage`` (the engine's coverage gate).
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import timedelta

from lasr.artifacts.serialization import canonical_json
from lasr.core.errors import LasrError
from lasr.data.schemas.features import FeatureSpec
from lasr.features.computation import FeatureComputeFn
from lasr.features.source_fields import SourceFieldCatalog

__all__ = [
    "FeatureKey",
    "FeatureRegistry",
    "FeatureRegistryError",
    "RegisteredFeature",
]

#: ``(feature_id, version)`` — the registry key (MP §18 name + version).
FeatureKey = tuple[str, int]

#: Version tag of the hash payload layout (bump on layout change).
_HASH_LAYOUT = "g022.registry.v1"


class FeatureRegistryError(LasrError):
    """Invalid registration or resolution (duplicates, undeclared fields,
    unknown features/lists)."""


@dataclass(frozen=True)
class RegisteredFeature:
    """One registry entry: the MP §18 record plus its computation kernel."""

    spec: FeatureSpec
    compute: FeatureComputeFn


def _spec_payload(spec: FeatureSpec) -> dict[str, object]:
    """FeatureSpec as a canonically serializable mapping (timedelta →
    seconds; tuples serialize as lists via ``canonical_json``)."""
    payload = asdict(spec)
    lag = payload["publication_lag"]
    assert isinstance(lag, timedelta)
    payload["publication_lag"] = lag.total_seconds()
    return payload


class FeatureRegistry:
    """MP §18 registry: specs, kernels, named lists, lineage hash."""

    def __init__(self, catalog: SourceFieldCatalog | None = None) -> None:
        self._catalog = catalog if catalog is not None else SourceFieldCatalog()
        self._features: dict[FeatureKey, RegisteredFeature] = {}
        self._lists: dict[str, tuple[FeatureKey, ...]] = {}

    @property
    def catalog(self) -> SourceFieldCatalog:
        return self._catalog

    # -- registration ------------------------------------------------------------

    def register(self, spec: FeatureSpec, compute: FeatureComputeFn) -> None:
        """Register one feature; every refusal is a typed error.

        ``FeatureSpec.__post_init__`` already enforces non-empty
        formula/evidence, ``version >= 1``, ``min_coverage`` in [0, 1] and a
        non-negative lag; this adds the registry-level rules (duplicates,
        declared source fields, units).
        """
        key: FeatureKey = (spec.feature_id, spec.version)
        if key in self._features:
            raise FeatureRegistryError(
                f"feature {spec.feature_id!r} v{spec.version} is already "
                "registered (duplicate registration refused; a changed "
                "formula is a NEW version, MP §18)"
            )
        if not spec.required_fields:
            raise FeatureRegistryError(
                f"feature {spec.feature_id!r} v{spec.version} declares no "
                "required source fields (a feature computed from nothing is "
                "unauditable, MP §18)"
            )
        for source_field in spec.required_fields:
            self._catalog.validate_field(source_field)
        if not spec.units.strip():
            raise FeatureRegistryError(
                f"feature {spec.feature_id!r} v{spec.version} declares blank "
                "units (MP §18)"
            )
        self._features[key] = RegisteredFeature(spec=spec, compute=compute)

    # -- resolution --------------------------------------------------------------

    def get(self, feature_id: str, version: int) -> RegisteredFeature:
        try:
            return self._features[(feature_id, version)]
        except KeyError:
            known = sorted(f"{fid} v{v}" for fid, v in self._features)
            raise FeatureRegistryError(
                f"unknown feature {feature_id!r} v{version}; registered: "
                f"{known} (silent empties forbidden)"
            ) from None

    def spec(self, feature_id: str, version: int) -> FeatureSpec:
        return self.get(feature_id, version).spec

    def specs(self) -> tuple[FeatureSpec, ...]:
        """All registered specs, sorted by ``(feature_id, version)``
        (deterministic, registration-order independent)."""
        return tuple(self._features[key].spec for key in sorted(self._features))

    def keys(self) -> tuple[FeatureKey, ...]:
        return tuple(sorted(self._features))

    # -- named feature lists (CR-016 machinery) -----------------------------------

    def define_list(self, list_id: str, members: Sequence[FeatureKey]) -> None:
        """Define a named, ordered feature list.

        Members must already be registered — every defined list is
        resolvable by construction; the version-spec lists whose features
        are later goals' data cannot be defined until those features exist.
        """
        if not list_id.strip():
            raise FeatureRegistryError("feature list_id must be non-empty")
        if list_id in self._lists:
            raise FeatureRegistryError(
                f"feature list {list_id!r} is already defined "
                "(lists are immutable; a changed roster is a new list_id)"
            )
        if not members:
            raise FeatureRegistryError(f"feature list {list_id!r} is empty")
        seen: set[FeatureKey] = set()
        for member in members:
            if member in seen:
                raise FeatureRegistryError(
                    f"feature list {list_id!r} repeats member {member!r}"
                )
            seen.add(member)
            if member not in self._features:
                raise FeatureRegistryError(
                    f"feature list {list_id!r} references unregistered "
                    f"feature {member!r}; register it first (CR-016 lists "
                    "must be resolvable by construction)"
                )
        self._lists[list_id] = tuple(members)

    def resolve_list(self, list_id: str) -> tuple[FeatureSpec, ...]:
        """Specs of a named list, in declared order (CR-016 resolution)."""
        try:
            members = self._lists[list_id]
        except KeyError:
            raise FeatureRegistryError(
                f"unknown feature list {list_id!r}; defined: "
                f"{sorted(self._lists)} (silent empties forbidden)"
            ) from None
        return tuple(self._features[key].spec for key in members)

    def list_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._lists))

    def list_members(self, list_id: str) -> tuple[FeatureKey, ...]:
        self.resolve_list(list_id)  # typed unknown-list error
        return self._lists[list_id]

    # -- lineage -----------------------------------------------------------------

    def registry_hash(self) -> str:
        """SHA-256 over the canonical serialization of all specs + lists.

        Registration-order independent (specs and lists are sorted);
        sensitive to any spec field, member, or list change — the lineage
        identity feature datasets record (system_design.md §5).
        """
        payload = {
            "layout": _HASH_LAYOUT,
            "specs": [_spec_payload(spec) for spec in self.specs()],
            "lists": {
                list_id: [list(member) for member in members]
                for list_id, members in sorted(self._lists.items())
            },
        }
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
