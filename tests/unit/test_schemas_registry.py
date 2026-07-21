"""Registry-wide structural invariants over every canonical table (G017).

Binds: U1/U2/U4 across all tables, the N-6 PK/sort-key resolutions, the
N-2/CI-049 delisting-return single home, N-5 knowledge-time exemptions,
and row-model <-> TableSchema column consistency.
"""

from __future__ import annotations

import pytest

from lasr.data.schemas import (
    DELISTING_RETURN_AUTHORITATIVE_HOME,
    PRICES_DAILY,
    SCHEMAS,
    TableSchema,
    get_schema,
)

pytestmark = pytest.mark.unit

EXPECTED_TABLES = {
    # canonical_schemas.md §1 (MP §14.1)
    "securities",
    "identifier_map",
    "listing_intervals",
    # §2 (MP §14.2)
    "prices_daily",
    "adjustment_factors",
    # §3 (MP §14.3)
    "fundamentals",
    # §4 (MP §14.4)
    "estimates_consensus",
    # §5 (MP §14.5)
    "corporate_actions",
    # §6 (MP §14.6)
    "classification_intervals",
    "derived_exposures",
    "universe_membership_intervals",
    # §7 (MP §14.7)
    "borrow_daily",
    "trading_calendars",
    "fx_rates",
    # §8
    "feature_values",
    # §10
    "training_examples",
}

ALL_SCHEMAS = sorted(SCHEMAS.values(), key=lambda s: s.name)


def test_every_mp14_family_has_a_schema() -> None:
    assert set(SCHEMAS) == EXPECTED_TABLES


@pytest.mark.parametrize("schema", ALL_SCHEMAS, ids=lambda s: s.name)
def test_u4_canonical_sort_key_declared(schema: TableSchema) -> None:
    assert schema.sort_key, f"{schema.name} must declare a sort key (U4/CI-043)"


@pytest.mark.parametrize("schema", ALL_SCHEMAS, ids=lambda s: s.name)
def test_primary_key_declared_and_non_nullable(schema: TableSchema) -> None:
    assert schema.primary_key
    for col in schema.primary_key:
        assert not schema.column(col).nullable


@pytest.mark.parametrize("schema", ALL_SCHEMAS, ids=lambda s: s.name)
def test_row_model_fields_match_columns(schema: TableSchema) -> None:
    """The pydantic row model and the TableSchema descriptor never drift."""
    assert tuple(schema.row_model.model_fields) == schema.column_names


@pytest.mark.parametrize("schema", ALL_SCHEMAS, ids=lambda s: s.name)
def test_nullability_policy_matches_row_model(schema: TableSchema) -> None:
    """A nullable column is exactly an Optional row-model field."""
    for col in schema.columns:
        required = schema.row_model.model_fields[col.name].is_required()
        if not col.nullable:
            assert required, f"{schema.name}.{col.name}: non-nullable but optional"
        else:
            assert not required, f"{schema.name}.{col.name}: nullable but required"


def test_u1_knowledge_time_columns() -> None:
    """U1 with the two documented deviations (G015-verification N-5)."""
    expected = {
        "securities": "first_knowledge_time",  # naming per §1.1
        "corporate_actions": "announcement_time",  # knowledge of existence, §5
        "training_examples": "knowledge_cutoff",  # §10 audit field
        "trading_calendars": None,  # derived grid — the documented exemption
    }
    for schema in ALL_SCHEMAS:
        assert schema.knowledge_time_column == expected.get(
            schema.name, "knowledge_time"
        ), schema.name


def test_u2_vintaged_tables() -> None:
    vintaged = {s.name for s in ALL_SCHEMAS if s.vintaged}
    assert vintaged == {"fundamentals", "estimates_consensus"}
    for name in vintaged:
        assert "vintage_seq" in SCHEMAS[name].primary_key


def test_derived_tables_flagged() -> None:
    """§2.1/§6.2: computed by the canonical layer, never ingested."""
    derived = {s.name for s in ALL_SCHEMAS if s.derived_table}
    assert derived == {"adjustment_factors", "derived_exposures"}


def test_n6_primary_key_resolutions_pinned() -> None:
    """The six tables the architecture left unkeyed (G015-verification N-6)
    plus training_examples (PK = the §10 join key)."""
    expected = {
        "listing_intervals": ("security_id", "exchange", "listing_date"),
        "adjustment_factors": ("security_id", "event_date"),
        "derived_exposures": ("security_id", "measure", "event_date"),
        "borrow_daily": ("security_id", "event_date"),
        "fx_rates": ("base_ccy", "quote_ccy", "event_date"),
        "trading_calendars": ("calendar_id", "event_date"),
        "training_examples": ("config_hash", "security_id", "as_of"),
    }
    for name, pk in expected.items():
        assert SCHEMAS[name].primary_key == pk, name
        assert SCHEMAS[name].sort_key == pk, name


def test_ci049_delisting_return_has_exactly_one_home() -> None:
    """N-2 resolution: corporate_actions.terminal_return is authoritative;
    every other terminal-return column is a derived view."""
    homes = [
        (schema.name, col.name)
        for schema in ALL_SCHEMAS
        for col in schema.columns
        if col.name in {"delisting_return", "terminal_return"}
        and col.derived_from is None
    ]
    assert homes == [DELISTING_RETURN_AUTHORITATIVE_HOME]
    assert DELISTING_RETURN_AUTHORITATIVE_HOME == (
        "corporate_actions",
        "terminal_return",
    )
    derived = SCHEMAS["listing_intervals"].column("delisting_return")
    assert derived.derived_from == "corporate_actions.terminal_return"


def test_fm17_guard_present_on_market_data() -> None:
    assert "adj_close" in PRICES_DAILY.forbidden_columns
    assert "adjusted_close" in PRICES_DAILY.forbidden_columns


def test_market_data_partitioned_by_year() -> None:
    # arch: system_design.md §5 — by family and year for canonical market data
    assert PRICES_DAILY.partition_keys == ("year(event_date)",)


def test_get_schema_unknown_table_raises() -> None:
    with pytest.raises(KeyError, match="unknown table"):
        get_schema("not_a_table")
