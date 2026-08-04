"""Feature computation interface: as-of-bounded PIT access (CI-001/CI-005).

# arch: system_design.md §2 L-FEAT — feature values are "produced only from
PIT queries"; §4 import rules make ``lasr.features`` unable to import
``data.canonical``. This module adds the *behavioral* half of that
structural guarantee: a compute function never touches a
:class:`~lasr.data.point_in_time.PitStore` directly — it receives a
:class:`FeatureContext` that

- pins every query to ``knowledge_time <= as_of`` (CI-001; a trailing
  ``as_of`` earlier than the context's is allowed — CI-004(b) trailing
  windows — a later one is a typed error);
- applies the registry's ``publication_lag`` to every query against a
  **vintaged** table (fundamentals, estimates: statement-like families per
  CI-005 "every non-price data family"; price bars carry no reporting
  delay). The PIT layer's own configured lags remain floors underneath
  (RT-G020-N1);
- refuses reads from tables that host none of the spec's declared
  ``required_fields``, refuses undeclared metric ids on metric-namespaced
  tables (the outgoing metric filter is REWRITTEN to the validated string
  ids, so a key object with divergent ``__str__``/``__eq__`` cannot smuggle
  undeclared rows — RT-G022-N1), and drops undeclared columns from returned
  frames of EVERY shape (column tables keep declared fields + plumbing;
  metric tables keep ``value`` + event/plumbing columns — post-``as_of``
  bookkeeping like ``ingestion_time`` is never visible, RT-G022-N2);
- records the maximum *effective* knowledge time over every returned row:
  ``knowledge_time`` + the lag the PIT store ACTUALLY applied —
  ``max(configured PitQueryConfig floor, registry lag)`` per table
  (RT-G022-B1) — from which the engine stamps the stored
  :class:`~lasr.data.schemas.features.FeatureValueRow.knowledge_time`.
  Invariant (tested): querying any input table at the stored stamp under
  the same store/config serves the rows the computation used. The stamp is
  the cross-sectional maximum over all rows the computation *saw* —
  conservative (never earlier than the truth; A-G022 candidate) and a
  property of the computation BATCH, not per-security truth: the same
  logical row computed over two different universes may carry different
  (both honest) stamps — persistence must key stamps per batch
  (RT-G022-N8, G023/G029 note).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

import pandas as pd

from lasr.core.errors import LasrError, TimeSemanticsError
from lasr.core.time_semantics import ensure_utc
from lasr.data.point_in_time import KeyFilter, PitStore
from lasr.data.schemas.features import FeatureSpec
from lasr.data.schemas.registry import get_schema
from lasr.features.source_fields import SourceFieldCatalog, parse_source_field

__all__ = [
    "FeatureComputationError",
    "FeatureComputeFn",
    "FeatureContext",
    "RawObservation",
    "require_utc_datetime",
]

logger = logging.getLogger(__name__)

#: Metric-table columns beyond primary-key/sort/knowledge plumbing that
#: kernels may consume (statement event-time legs). Everything else —
#: ``ingestion_time`` (a post-as_of wall-clock stamp), ``report_date``,
#: ``knowledge_basis``, ``unit``, ``currency``, ``consolidation_basis``,
#: ``n_contributors`` — is dropped from served frames (RT-G022-N2); a
#: future feature needing one extends this declaration, never bypasses it.
_METRIC_TABLE_EVENT_COLUMNS: Mapping[str, tuple[str, ...]] = {
    "fundamentals": ("period_end",),
    "estimates_consensus": (),
}


def require_utc_datetime(value: object, where: str) -> datetime:
    """Typed guard for ``as_of`` arguments (RT-G022-N6).

    A plain ``date`` (or anything else that is not a ``datetime``) raises
    :class:`TimeSemanticsError` instead of an untyped ``AttributeError``
    deeper down; naive datetimes are rejected by :func:`ensure_utc`.
    Note ``datetime`` subclasses ``date``, so the check must be on
    ``datetime`` membership, not ``date`` membership.
    """
    if not isinstance(value, datetime):
        raise TimeSemanticsError(
            f"{where} must be a tz-aware datetime, got "
            f"{type(value).__name__}: {value!r} (a bare date has no "
            "knowledge-time semantics)"
        )
    return ensure_utc(value)


class FeatureComputationError(LasrError):
    """Invalid feature computation (undeclared source read, future as_of,
    fabricated security, value with no observed inputs)."""


@dataclass(frozen=True)
class RawObservation:
    """One security's raw (pre-rank, pre-neutralization — D-007) value.

    ``observation_time`` is the event time of the underlying inputs (e.g.
    midnight UTC of the last price bar's ``event_date``, or of a
    fundamental's ``period_end``) — it feeds
    ``FeatureValueRow.observation_time`` and must never exceed the input's
    knowledge time (CI-005 ordering, enforced by the row model).
    """

    value: float
    observation_time: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "observation_time", ensure_utc(self.observation_time))


class FeatureComputeFn(Protocol):
    """A registered feature's computation kernel.

    Receives the as-of-bounded :class:`FeatureContext` and the requested
    security ids; returns raw observations for the securities it can cover.
    Missing securities are simply absent (missing policy ``exclude``,
    CI-021: never imputed).
    """

    def __call__(
        self, ctx: FeatureContext, securities: frozenset[str]
    ) -> Mapping[str, RawObservation]: ...


class FeatureContext:
    """As-of-bounded, declaration-bounded input access for one feature.

    Constructed by the engine per ``(feature, as_of)`` computation; compute
    functions receive no other data access path.
    """

    def __init__(
        self,
        pit: PitStore,
        spec: FeatureSpec,
        as_of: datetime,
        *,
        catalog: SourceFieldCatalog,
    ) -> None:
        self._pit = pit
        self._spec = spec
        self._as_of = require_utc_datetime(as_of, "as_of")
        self._metric_tables = catalog.metric_tables
        fields_by_table: dict[str, set[str]] = {}
        for source_field in spec.required_fields:
            table, name = parse_source_field(source_field)
            fields_by_table.setdefault(table, set()).add(name)
        self._declared: dict[str, frozenset[str]] = {
            table: frozenset(names) for table, names in fields_by_table.items()
        }
        self._max_effective_knowledge: datetime | None = None

    @property
    def as_of(self) -> datetime:
        return self._as_of

    @property
    def spec(self) -> FeatureSpec:
        return self._spec

    @property
    def max_input_knowledge_time(self) -> datetime | None:
        """Max effective knowledge time (knowledge_time + applied lag) over
        every row returned so far; ``None`` until a row has been seen."""
        return self._max_effective_knowledge

    def _applied_lag(self, table: str) -> timedelta:
        """CI-005 rule: the registry publication lag gates every vintaged
        (statement-like) source table; bar-shaped tables carry no lag."""
        return (
            self._spec.publication_lag if get_schema(table).vintaged else timedelta(0)
        )

    def frame(
        self,
        table: str,
        keys: KeyFilter | None = None,
        *,
        as_of: datetime | None = None,
    ) -> pd.DataFrame:
        """Rows of ``table`` knowable at ``as_of`` (default: the context's).

        Enforcement, in order: (1) the table must host a declared required
        field; (2) a caller ``as_of`` may only look *back* (CI-004(b)
        trailing statistics; looking forward is structurally impossible —
        CI-001); (3) metric-namespaced tables must be filtered to declared
        metric ids, and the outgoing filter is rewritten to the validated
        string ids (RT-G022-N1); (4) every frame comes back with declared
        fields plus plumbing only (RT-G022-N2).
        """
        if table not in self._declared:
            raise FeatureComputationError(
                f"feature {self._spec.feature_id!r} v{self._spec.version} reads "
                f"undeclared source table {table!r}; declared tables: "
                f"{sorted(self._declared)} (MP §18 required_fields is enforced)"
            )
        effective_as_of = (
            self._as_of
            if as_of is None
            else require_utc_datetime(as_of, "frame(as_of=...)")
        )
        if effective_as_of > self._as_of:
            raise FeatureComputationError(
                f"feature {self._spec.feature_id!r} requested as_of "
                f"{effective_as_of.isoformat()} beyond the computation as_of "
                f"{self._as_of.isoformat()} (CI-001: no forward looks)"
            )
        requested_lag = self._applied_lag(table) or None
        if table in self._metric_tables:
            keys = self._with_validated_metric_filter(table, keys)
        frame = self._pit.as_of_frame(
            table, effective_as_of, keys=keys, lag=requested_lag
        )
        # RT-G022-B1: the stamp must reflect the lag the store ACTUALLY
        # applied — max(configured PitQueryConfig floor, registry lag) —
        # not the registry lag alone, or a configured floor above the
        # registry lag would produce stamps at instants where this very
        # store serves zero rows. The store's own rule is the single
        # source of truth (RT-G020-B2/N1); a private-API read is
        # deliberate drift-proofing until PitStore exposes it publicly
        # (proposed follow-up for the PIT owner).
        effective_lag = self._pit._effective_lag(table, requested_lag)
        self._record_knowledge(table, frame, effective_lag)
        return frame[self._visible_columns(table)]

    def _with_validated_metric_filter(
        self, table: str, keys: KeyFilter | None
    ) -> KeyFilter:
        """Validate the metric filter AND rewrite it with the validated
        ``str`` ids (RT-G022-N1: the store matches with the caller
        object's ``__eq__`` — a key object whose ``__str__`` names a
        declared metric but whose ``__eq__`` matches an undeclared one
        must not reach the store)."""
        declared = self._declared[table]
        metric = keys.get("metric") if keys is not None else None
        if metric is None:
            raise FeatureComputationError(
                f"query on metric table {table!r} must filter 'metric' to the "
                f"declared ids {sorted(declared)} (undeclared reads refused)"
            )
        requested = (
            {str(m) for m in metric}
            if isinstance(metric, set | frozenset | tuple | list)
            else {str(metric)}
        )
        undeclared = sorted(requested - declared)
        if undeclared:
            raise FeatureComputationError(
                f"feature {self._spec.feature_id!r} v{self._spec.version} reads "
                f"undeclared metric(s) {undeclared} on {table!r}; declared: "
                f"{sorted(declared)}"
            )
        rewritten = dict(keys) if keys is not None else {}
        rewritten["metric"] = tuple(sorted(requested))  # validated strs only
        return rewritten

    def _visible_columns(self, table: str) -> list[str]:
        """Served columns, in schema order (deterministic): plumbing
        (primary key, sort key, knowledge time) plus declared fields
        (column tables) or ``value`` + declared event columns (metric
        tables — RT-G022-N2: bookkeeping like ``ingestion_time`` is a
        post-as_of wall-clock stamp and must never reach a kernel)."""
        schema = get_schema(table)
        visible = set(schema.primary_key) | set(schema.sort_key)
        if schema.knowledge_time_column is not None:
            visible.add(schema.knowledge_time_column)
        if table in self._metric_tables:
            visible.add("value")
            visible.update(_METRIC_TABLE_EVENT_COLUMNS.get(table, ()))
        else:
            visible.update(self._declared[table])
        return [c for c in schema.column_names if c in visible]

    def _record_knowledge(
        self, table: str, frame: pd.DataFrame, effective_lag: timedelta
    ) -> None:
        column = get_schema(table).knowledge_time_column
        if column is None:  # pragma: no cover - metric/price tables carry one
            return
        for value in frame[column]:
            if isinstance(value, datetime):
                effective = value + effective_lag
                if (
                    self._max_effective_knowledge is None
                    or effective > self._max_effective_knowledge
                ):
                    self._max_effective_knowledge = effective
