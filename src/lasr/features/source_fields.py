"""Declared source-field vocabulary for feature registration (MP §18).

Every :class:`~lasr.data.schemas.features.FeatureSpec` names its
``required_fields`` as ``"<table>.<field>"`` strings. This module owns the
vocabulary those strings are validated against, so that registering a
feature over an undeclared source field is refused (MP §18 "required source
fields" is an enforced declaration, not documentation):

- for **column-shaped** canonical tables (e.g. ``prices_daily``) the field
  must be a declared schema column;
- for **metric-namespaced** long/narrow tables (``fundamentals``,
  ``estimates_consensus``) the field is a canonical metric id
  (dictionary-governed, docs/data/data_dictionary.md via field_mapping.md)
  and must appear in the catalog's declared metric set.

The default catalog declares only the metric ids the G022 audited library
consumes, each cited to its field_mapping.md row; later goals extend it via
:meth:`SourceFieldCatalog.with_metrics` — never by editing feature code.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from lasr.core.errors import LasrError
from lasr.data.schemas.registry import SCHEMAS

__all__ = [
    "DEFAULT_METRIC_IDS",
    "SOURCE_FIELD_SEPARATOR",
    "SourceFieldCatalog",
    "SourceFieldError",
    "parse_source_field",
]

#: ``"<table>.<field>"`` — the single separator of the field vocabulary.
SOURCE_FIELD_SEPARATOR = "."

#: Metric ids declared for the G022 audited library, per table. Citations:
#: docs/data/field_mapping.md (``dict rN`` = data_dictionary.md W1 row N).
DEFAULT_METRIC_IDS: Mapping[str, frozenset[str]] = {
    "fundamentals": frozenset(
        {
            "BOOK_VALUE",  # dict r202 — B/P numerator (field_mapping §5.1)
            "TOT_ASSET",  # dict r117 — asset growth (field_mapping §5.2)
            "EPS_WAD",  # dict r38 — EPS growth / earnings yield (§5.2)
        }
    ),
    "estimates_consensus": frozenset(
        {
            "EPS",  # consensus EPS levels FY+1/FY+2 (field_mapping §5.4)
        }
    ),
}


class SourceFieldError(LasrError):
    """A source-field string is malformed or names an undeclared field."""


def parse_source_field(source_field: str) -> tuple[str, str]:
    """Split ``"<table>.<field>"``; malformed strings raise (never guessed)."""
    table, sep, name = source_field.partition(SOURCE_FIELD_SEPARATOR)
    if not sep or not table or not name:
        raise SourceFieldError(
            f"malformed source field {source_field!r}: expected "
            f"'<table>{SOURCE_FIELD_SEPARATOR}<field>' (MP §18 required source fields)"
        )
    return table, name


@dataclass(frozen=True)
class SourceFieldCatalog:
    """The declared-field vocabulary a registry validates against.

    ``metric_ids`` maps each metric-namespaced table to its declared metric
    ids; tables absent from the mapping are column-shaped and validate
    against their :class:`TableSchema` columns. The mapping is coerced to a
    read-only proxy over frozensets (RT-G022-N3): in-place mutation raises,
    so :meth:`with_metrics` (copy-on-extend) is the ONLY extension path.
    """

    metric_ids: Mapping[str, frozenset[str]] = field(
        default_factory=lambda: dict(DEFAULT_METRIC_IDS)
    )

    def __post_init__(self) -> None:
        for table in self.metric_ids:
            if table not in SCHEMAS:
                raise SourceFieldError(
                    f"metric namespace declared for unknown canonical table "
                    f"{table!r}; known: {sorted(SCHEMAS)}"
                )
        # deep immutability (RT-G022-N3): read-only mapping of frozensets
        object.__setattr__(
            self,
            "metric_ids",
            MappingProxyType(
                {table: frozenset(ids) for table, ids in self.metric_ids.items()}
            ),
        )

    @property
    def metric_tables(self) -> frozenset[str]:
        """Tables whose source fields are metric ids, not columns."""
        return frozenset(self.metric_ids)

    def with_metrics(self, table: str, metric_ids: Iterable[str]) -> SourceFieldCatalog:
        """New catalog with ``metric_ids`` added under ``table`` (extension
        point for later goals' feature libraries; append-only)."""
        merged = {t: set(ids) for t, ids in self.metric_ids.items()}
        merged.setdefault(table, set()).update(metric_ids)
        return SourceFieldCatalog(
            metric_ids={t: frozenset(ids) for t, ids in merged.items()}
        )

    def validate_field(self, source_field: str) -> tuple[str, str]:
        """Validate one ``"<table>.<field>"`` string; return ``(table, field)``.

        Raises :class:`SourceFieldError` for an unknown table, an undeclared
        column, or an undeclared metric id — a typo can never register
        (MP §18; RT-G020-N5 silent-empties discipline).
        """
        table, name = parse_source_field(source_field)
        if table not in SCHEMAS:
            raise SourceFieldError(
                f"source field {source_field!r} names unknown canonical table "
                f"{table!r}; known: {sorted(SCHEMAS)}"
            )
        if table in self.metric_ids:
            if name not in self.metric_ids[table]:
                raise SourceFieldError(
                    f"source field {source_field!r} names undeclared metric "
                    f"{name!r} on {table!r}; declared: "
                    f"{sorted(self.metric_ids[table])} "
                    "(extend the catalog via with_metrics, never bypass it)"
                )
        elif name not in SCHEMAS[table].column_names:
            raise SourceFieldError(
                f"source field {source_field!r} names undeclared column "
                f"{name!r} on {table!r}; declared: "
                f"{sorted(SCHEMAS[table].column_names)}"
            )
        return table, name
