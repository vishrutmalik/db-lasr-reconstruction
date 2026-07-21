"""TableSchema descriptor self-checks + validate_rows structural rules (G017).

Binds the canonical_schemas.md universal rules: U1 (non-null knowledge
time), U2 (vintage uniqueness + strictly increasing knowledge_time —
CI-002 substrate), U4 (canonical sort order — CI-043 substrate), plus
nullability policy, PK uniqueness, and the forbidden-column guard (FM-17).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from lasr.core import SchemaValidationError
from lasr.data.schemas import ColumnSpec, SchemaRow, TableSchema, validate_rows

pytestmark = pytest.mark.unit

KT0 = datetime(2012, 1, 31, 21, 0, tzinfo=UTC)
KT1 = datetime(2012, 2, 29, 21, 0, tzinfo=UTC)


class _Row(SchemaRow):
    key: str
    vintage_seq: int
    knowledge_time: datetime
    value: float | None = None


def _schema(**overrides: Any) -> TableSchema:
    spec: dict[str, Any] = {
        "name": "t",
        "columns": (
            ColumnSpec("key", "str"),
            ColumnSpec("vintage_seq", "int64"),
            ColumnSpec("knowledge_time", "datetime"),
            ColumnSpec("value", "float64", nullable=True),
        ),
        "primary_key": ("key", "vintage_seq"),
        "sort_key": ("key", "vintage_seq"),
        "row_model": _Row,
    }
    spec.update(overrides)
    return TableSchema(**spec)


def _row(
    key: str = "a",
    vintage_seq: int = 0,
    knowledge_time: datetime = KT0,
    value: float | None = 1.0,
    **extra: object,
) -> dict[str, object]:
    return {
        "key": key,
        "vintage_seq": vintage_seq,
        "knowledge_time": knowledge_time,
        "value": value,
        **extra,
    }


class TestTableSchemaSelfChecks:
    def test_valid_schema_constructs(self) -> None:
        schema = _schema()
        assert schema.column_names == ("key", "vintage_seq", "knowledge_time", "value")
        assert schema.event_key == ("key", "vintage_seq")  # non-vintaged: PK itself

    def test_primary_key_must_exist_in_columns(self) -> None:
        with pytest.raises(SchemaValidationError, match="not in columns"):
            _schema(primary_key=("missing",))

    def test_primary_key_must_be_declared(self) -> None:
        with pytest.raises(SchemaValidationError, match="N-6"):
            _schema(primary_key=())

    def test_primary_key_columns_must_be_non_nullable(self) -> None:
        with pytest.raises(SchemaValidationError, match="nullable"):
            _schema(primary_key=("value",))

    def test_sort_key_must_be_declared(self) -> None:
        """U4: every table declares a canonical sort key."""
        with pytest.raises(SchemaValidationError, match="U4"):
            _schema(sort_key=())

    def test_knowledge_time_column_must_exist(self) -> None:
        with pytest.raises(SchemaValidationError, match="knowledge_time"):
            _schema(knowledge_time_column="nope")

    def test_u1_knowledge_time_column_must_be_non_nullable(self) -> None:
        with pytest.raises(SchemaValidationError, match="U1"):
            _schema(
                columns=(
                    ColumnSpec("key", "str"),
                    ColumnSpec("vintage_seq", "int64"),
                    ColumnSpec("knowledge_time", "datetime", nullable=True),
                ),
                primary_key=("key", "vintage_seq"),
                sort_key=("key",),
            )

    def test_u2_vintaged_requires_vintage_seq_in_pk(self) -> None:
        with pytest.raises(SchemaValidationError, match="U2"):
            _schema(primary_key=("key",), vintaged=True)

    def test_duplicate_column_names_rejected(self) -> None:
        with pytest.raises(SchemaValidationError, match="duplicate"):
            _schema(
                columns=(
                    ColumnSpec("key", "str"),
                    ColumnSpec("key", "str"),
                    ColumnSpec("vintage_seq", "int64"),
                    ColumnSpec("knowledge_time", "datetime"),
                ),
            )

    def test_vintage_event_key_strips_vintage_seq(self) -> None:
        assert _schema(vintaged=True).event_key == ("key",)


class TestValidateRows:
    def test_valid_sorted_batch_passes(self) -> None:
        schema = _schema(vintaged=True)
        rows = [
            _row("a", 0, KT0),
            _row("a", 1, KT1),  # restatement: later vintage, later knowledge
            _row("b", 0, KT0, value=None),  # nullable column may be null
        ]
        validate_rows(schema, rows)  # must not raise

    def test_u1_null_knowledge_time_rejected(self) -> None:
        with pytest.raises(SchemaValidationError, match="non-nullable"):
            validate_rows(_schema(), [_row(knowledge_time=None)])  # type: ignore[arg-type]

    def test_missing_required_column_rejected(self) -> None:
        row = _row()
        del row["key"]
        with pytest.raises(SchemaValidationError, match="'key'"):
            validate_rows(_schema(), [row])

    def test_undeclared_column_rejected(self) -> None:
        with pytest.raises(SchemaValidationError, match="undeclared"):
            validate_rows(_schema(), [_row(smuggled=1)])

    def test_fm17_forbidden_column_rejected(self) -> None:
        schema = _schema(forbidden_columns=("adj_close",))
        with pytest.raises(SchemaValidationError, match="FM-17"):
            validate_rows(schema, [_row(adj_close=101.0)])

    def test_duplicate_primary_key_rejected(self) -> None:
        with pytest.raises(SchemaValidationError, match="duplicate primary key"):
            validate_rows(_schema(), [_row("a", 0), _row("a", 0, KT1)])

    def test_u4_unsorted_batch_rejected(self) -> None:
        """CI-043: persisted output is sorted by the canonical sort key."""
        with pytest.raises(SchemaValidationError, match="U4"):
            validate_rows(_schema(), [_row("b", 0), _row("a", 0)])

    def test_u2_duplicate_vintage_rejected(self) -> None:
        rows = [_row("a", 0, KT0), _row("a", 0, KT1)]
        with pytest.raises(SchemaValidationError, match="U2"):
            validate_rows(_schema(vintaged=True), rows)

    def test_u2_ci002_knowledge_time_strictly_increasing(self) -> None:
        """A later vintage with equal-or-earlier knowledge_time breaks the
        CI-002 as-of join substrate."""
        rows = [_row("a", 0, KT1), _row("a", 1, KT0)]
        with pytest.raises(SchemaValidationError, match="CI-002"):
            validate_rows(_schema(vintaged=True), rows)
        with pytest.raises(SchemaValidationError, match="CI-002"):
            validate_rows(
                _schema(vintaged=True), [_row("a", 0, KT0), _row("a", 1, KT0)]
            )

    def test_all_problems_reported(self) -> None:
        schema = _schema(forbidden_columns=("adj_close",))
        rows = [
            _row("b", 0, None, adj_close=1.0),  # type: ignore[arg-type]
            _row("a", 0),
        ]
        with pytest.raises(SchemaValidationError) as excinfo:
            validate_rows(schema, rows)
        problems = excinfo.value.problems
        assert len(problems) >= 3  # forbidden + null knowledge + unsorted
        assert any("FM-17" in p for p in problems)
        assert any("non-nullable" in p for p in problems)
        assert any("U4" in p for p in problems)
