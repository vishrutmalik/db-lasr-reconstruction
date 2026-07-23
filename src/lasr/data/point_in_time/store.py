"""PitStore: the point-in-time query API over canonical vintages (D-006).

# arch: system_design.md §2 L-PIT: NOT a stored copy — a query API over
append-only canonical vintage tables. No materialized snapshots
(decisions.md D-006: materializing per-as_of snapshots duplicates data and
invites drift; as-of joins over append-only vintages are cheap and
directly testable). Interface per canonical_schemas.md §11.

Semantics (each pinned by a CI-cited test):

- ``as_of_frame(table, as_of)`` returns only rows with
  ``knowledge_time <= as_of - effective_lag`` — the CI-001 ``knowable``
  predicate with EXACT ``<=`` boundary semantics, and CI-005 configured
  publication lags (A-002: lags are config, never hard-coded).
- ONE cutoff rule for EVERY query path (RT-G020-B2): ``as_of_frame``,
  ``universe`` (membership AND listing sides), and ``classification`` all
  compute their knowledge cutoff through the same ``_cutoff`` helper, so a
  configured lag cannot gate one surface and not another (split-brain
  impossible by construction). ``PitQueryConfig`` refuses lags for tables
  that carry no knowledge time, so the config can never promise what a
  path does not deliver.
- The configured lag is a FLOOR (RT-G020-N1): a per-call ``lag`` may
  extend but never shorten it (``effective = max(configured, requested)``)
  — CI-005's "never returns" cannot be defeated by a caller passing
  ``lag=0``.
- Vintaged tables return the latest ``vintage_seq`` per event key among
  knowable rows (CI-002: U2 guarantees knowledge_time strictly increases
  in vintage_seq, so the max vintage IS the latest knowable statement);
  later inserts never change earlier answers because datasets are
  content-addressed and immutable.
- ``universe(universe_id, as_of)`` is interval containment over rows with
  ``knowledge_time <= cutoff`` (CI-003) — optionally intersected with
  active listing intervals; backfill from current constituents is
  impossible by construction (membership is an interval table). Interval
  containment itself is evaluated at ``as_of``'s date: a lag delays
  KNOWLEDGE, never event-time validity.
- ``classification(scheme, as_of)`` returns the effective-dated value per
  security (CI-017/025/028 substrate) with a documented deterministic
  tie rule: latest ``(valid_from, knowledge_time)`` wins.
- Unknown identifiers are typed errors, never silent empties
  (RT-G020-N5, verifier NB-3): unknown table / universe_id / scheme /
  key-filter column raise ``PitQueryError``.

Determinism: results are sorted by the table's canonical sort key (U4);
dataset selection is explicit (``dataset_ids`` argument) or unambiguous
(``only_dataset``) — never a mtime-based "latest". Datasets are verified
against their manifests on first load (``CanonicalStore.verified_records``,
RT-G020-B4).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

from lasr.core.errors import LasrError, TimeSemanticsError
from lasr.core.time_semantics import DateInterval, ensure_utc
from lasr.data.canonical.store import CanonicalStore
from lasr.data.schemas.base import Row, TableSchema
from lasr.data.schemas.registry import get_schema

#: Real stubbed type (pandas-stubs is a dev dependency since G043).
DataFrame = pd.DataFrame

__all__ = [
    "KeyFilter",
    "PitQueryConfig",
    "PitQueryError",
    "PitStore",
    "select_latest_vintages",
]

logger = logging.getLogger(__name__)

#: Column -> required value (scalar) or admissible values (set/frozenset/
#: tuple/list). Scalars compare by equality; collections by membership.
KeyFilter = Mapping[str, object]


class PitQueryError(LasrError):
    """Invalid PIT query (unknown table, ambiguous dataset, bad lag)."""


@dataclass(frozen=True)
class PitQueryConfig:
    """Config-driven query behavior — no hard-coded lags (CI-005, A-002).

    ``publication_lags`` maps canonical table names to the availability lag
    applied to EVERY query path touching that table (the
    ``publication_lag_days`` knob of assumptions_register A-002; e.g. the
    nlasr_2020 3-month fundamental lag, E-P4-04). Validation (RT-G020-B2):
    lag entries must name known canonical tables that carry a knowledge
    time — the config can never promise a lag no query path can deliver.
    """

    publication_lags: Mapping[str, timedelta] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for table, lag in self.publication_lags.items():
            if lag < timedelta(0):
                raise TimeSemanticsError(
                    f"publication lag for table {table!r} must be >= 0, got {lag!r}"
                )
            try:
                schema = get_schema(table)
            except KeyError as exc:
                raise PitQueryError(
                    f"publication lag configured for unknown table {table!r}"
                ) from exc
            if schema.knowledge_time_column is None:
                raise PitQueryError(
                    f"publication lag configured for {table!r}, which carries "
                    "no knowledge time (U1 exemption) — no query path can "
                    "apply it (RT-G020-B2)"
                )


def _matches(record: Row, keys: KeyFilter | None) -> bool:
    if keys is None:
        return True
    for column, expected in keys.items():
        value = record.get(column)
        if isinstance(expected, set | frozenset | tuple | list):
            if value not in expected:
                return False
        elif value != expected:
            return False
    return True


def select_latest_vintages(
    records: tuple[Row, ...],
    *,
    event_key: tuple[str, ...],
    knowledge_column: str,
    cutoff: datetime,
) -> tuple[Row, ...]:
    """Latest knowable vintage per event key (the CI-002 kernel).

    Pure function (property-tested against a brute-force reference): among
    rows with ``knowledge_column <= cutoff`` (exact ``<=``, CI-001), keep
    per event key the row with the maximum ``(knowledge_time,
    vintage_seq)``. U2 makes the two orderings agree within an event key;
    the tuple order is the documented deterministic tie rule for
    degenerate inputs.
    """
    best: dict[tuple[object, ...], Row] = {}
    order: dict[tuple[object, ...], tuple[Any, Any]] = {}
    for record in records:
        kt = record.get(knowledge_column)
        if not isinstance(kt, datetime) or kt > cutoff:
            continue
        key = tuple(record.get(c) for c in event_key)
        rank = (kt, record.get("vintage_seq", 0))
        if key not in best or rank > order[key]:
            best[key] = record
            order[key] = rank
    return tuple(best.values())


class PitStore:
    """Point-in-time queries over a :class:`CanonicalStore` (D-006).

    ``dataset_ids`` pins which dataset serves each table; tables absent
    from the mapping resolve via ``CanonicalStore.only_dataset`` (which
    refuses ambiguity). Loaded datasets are cached — safe because
    canonical datasets are immutable (append = new dataset id).
    """

    def __init__(
        self,
        store: CanonicalStore,
        dataset_ids: Mapping[str, str] | None = None,
        config: PitQueryConfig | None = None,
    ) -> None:
        self._store = store
        self._dataset_ids = dict(dataset_ids) if dataset_ids else {}
        self._config = config if config is not None else PitQueryConfig()
        self._cache: dict[tuple[str, str], tuple[Row, ...]] = {}

    # -- resolution ------------------------------------------------------------

    @staticmethod
    def _schema(table: str) -> TableSchema:
        """Typed unknown-table error (verifier NB-3 / RT-G020-N5)."""
        try:
            return get_schema(table)
        except KeyError as exc:
            raise PitQueryError(str(exc)) from exc

    def dataset_id(self, table: str) -> str:
        if table in self._dataset_ids:
            return self._dataset_ids[table]
        return self._store.only_dataset(table)

    def _records(self, table: str) -> tuple[Row, ...]:
        self._schema(table)  # typed error before touching the store (NB-3)
        dataset = self.dataset_id(table)
        key = (table, dataset)
        if key not in self._cache:
            # verified read: payload re-hashed + stamp-consistency checked
            # against the manifest before anything is served (RT-G020-B4)
            self._cache[key] = self._store.verified_records(table, dataset)
        return self._cache[key]

    def _effective_lag(self, table: str, lag: timedelta | None) -> timedelta:
        """Configured lag as a FLOOR; a per-call lag may only extend it
        (RT-G020-N1: ``lag=0`` cannot defeat a configured embargo)."""
        configured = self._config.publication_lags.get(table, timedelta(0))
        if lag is None:
            return configured
        if lag < timedelta(0):
            raise TimeSemanticsError(f"publication lag must be >= 0, got {lag!r}")
        return max(configured, lag)

    def _cutoff(self, table: str, as_of: datetime, lag: timedelta | None) -> datetime:
        """THE knowledge cutoff — the single gating rule shared by every
        query path (RT-G020-B2: split-brain impossible by construction)."""
        return ensure_utc(as_of) - self._effective_lag(table, lag)

    # -- core query (canonical_schemas.md §11) ----------------------------------

    def as_of_frame(
        self,
        table: str,
        as_of: datetime,
        keys: KeyFilter | None = None,
        lag: timedelta | None = None,
    ) -> DataFrame:
        """Rows knowable at ``as_of`` (CI-001), latest vintage per event
        key for vintaged tables (CI-002), lag-shifted per CI-005.

        Append-immutable: later inserts never change earlier answers —
        the served dataset is content-addressed and immutable (D-006).
        """
        schema = self._schema(table)
        if keys is not None:
            unknown = sorted(set(keys) - set(schema.column_names))
            if unknown:
                raise PitQueryError(
                    f"key filter names undeclared columns {unknown!r} on "
                    f"{table!r} — a typo would silently match nothing "
                    "(RT-G020-N5)"
                )
        cutoff = self._cutoff(table, as_of, lag)
        records = tuple(r for r in self._records(table) if _matches(r, keys))
        ktc = schema.knowledge_time_column
        if ktc is None:
            # documented U1 exemption (trading_calendars, N-5): a derived
            # grid, not observed facts — no knowledge gating applies.
            if lag is not None:
                raise PitQueryError(
                    f"lag on {table!r}, which carries no knowledge time — "
                    "a silently ignored lag is a hidden no-op (RT-G020-B2)"
                )
            selected = records
        elif schema.vintaged:
            selected = select_latest_vintages(
                records,
                event_key=schema.event_key,
                knowledge_column=ktc,
                cutoff=cutoff,
            )
        else:
            selected = tuple(
                r
                for r in records
                if isinstance(r.get(ktc), datetime) and r[ktc] <= cutoff  # type: ignore[operator]
            )
        return self._to_frame(schema, selected)

    @staticmethod
    def _to_frame(schema: TableSchema, records: tuple[Row, ...]) -> DataFrame:
        ordered = sorted(
            records, key=lambda r: tuple(r.get(c) for c in schema.sort_key)
        )
        data = {
            column: [r.get(column) for r in ordered] for column in schema.column_names
        }
        return pd.DataFrame(data, columns=list(schema.column_names), dtype=object)

    # -- universe membership (CI-003) -------------------------------------------

    def universe(
        self,
        universe_id: str,
        as_of: datetime,
        *,
        membership_table: str = "universe_membership_intervals",
        listing_table: str | None = None,
        lag: timedelta | None = None,
    ) -> frozenset[str]:
        """Members at ``as_of``: interval containment over rows with
        ``knowledge_time <= as_of - effective_lag`` (CI-003, CI-005).

        Membership backfill is impossible by construction: membership is an
        interval table and rows are knowledge-gated, so a snapshot-stamped
        record can never claim the past. Pass ``listing_table`` to also
        require an active listing interval at ``as_of`` (the CI-003
        exclusion side: delisted-before / listed-after securities drop
        out); ``None`` skips the intersection EXPLICITLY (for providers
        with no listing data — never a silent fallback). Lag gating uses
        the shared ``_cutoff`` rule (RT-G020-B2); the listing side applies
        the listing table's own configured lag. An unknown ``universe_id``
        raises (RT-G020-N5) — a universe with zero *knowable* rows at
        ``as_of`` is a legal empty answer, an id with zero rows at all is
        a typo.
        """
        cutoff = self._cutoff(membership_table, as_of, lag)
        day = ensure_utc(as_of).date()  # lag delays knowledge, not validity
        members: set[str] = set()
        known_ids: set[str] = set()
        for record in self._records(membership_table):
            known_ids.add(str(record.get("universe_id")))
            if record.get("universe_id") != universe_id:
                continue
            kt = record.get("knowledge_time")
            if not isinstance(kt, datetime) or kt > cutoff:
                continue
            if self._interval_contains(record, day):
                members.add(str(record["security_id"]))
        if universe_id not in known_ids:
            raise PitQueryError(
                f"unknown universe_id {universe_id!r}; known: "
                f"{sorted(known_ids)} (RT-G020-N5: silent empties forbidden)"
            )
        if listing_table is not None:
            listing_cutoff = self._cutoff(listing_table, as_of, None)
            members &= self._actively_listed(listing_table, listing_cutoff, day)
        return frozenset(members)

    def _actively_listed(
        self, listing_table: str, cutoff: datetime, day: date
    ) -> set[str]:
        active: set[str] = set()
        for record in self._records(listing_table):
            kt = record.get("knowledge_time")
            if not isinstance(kt, datetime) or kt > cutoff:
                continue
            listing = record.get("listing_date")
            delisting = record.get("delisting_date")
            if not isinstance(listing, date):
                continue
            interval = DateInterval(
                valid_from=listing,
                valid_to=delisting if isinstance(delisting, date) else None,
            )
            if interval.contains(day):
                active.add(str(record["security_id"]))
        return active

    @staticmethod
    def _interval_contains(record: Row, day: date) -> bool:
        valid_from = record.get("valid_from")
        if not isinstance(valid_from, date):
            return False
        valid_to = record.get("valid_to")
        interval = DateInterval(
            valid_from=valid_from,
            valid_to=valid_to if isinstance(valid_to, date) else None,
        )
        return interval.contains(day)

    # -- classifications (CI-017/025/028 substrate) ------------------------------

    def classification(
        self,
        scheme: str,
        as_of: datetime,
        *,
        table: str = "classification_intervals",
        lag: timedelta | None = None,
    ) -> dict[str, str]:
        """security_id → value effective at ``as_of`` under ``scheme``.

        Knowledge-gated interval query through the shared ``_cutoff`` rule
        (RT-G020-B2); among a security's knowable intervals containing
        ``as_of``'s date, the latest ``(valid_from, knowledge_time)`` wins
        (documented deterministic rule — CI-043 family). An unknown
        ``scheme`` raises (RT-G020-N5).
        """
        cutoff = self._cutoff(table, as_of, lag)
        day = ensure_utc(as_of).date()  # lag delays knowledge, not validity
        best: dict[str, tuple[date, datetime]] = {}
        values: dict[str, str] = {}
        known_schemes: set[str] = set()
        for record in self._records(table):
            known_schemes.add(str(record.get("scheme")))
            if record.get("scheme") != scheme:
                continue
            kt = record.get("knowledge_time")
            if not isinstance(kt, datetime) or kt > cutoff:
                continue
            if not self._interval_contains(record, day):
                continue
            security_id = str(record["security_id"])
            valid_from = record.get("valid_from")
            assert isinstance(valid_from, date)  # _interval_contains checked
            rank = (valid_from, kt)
            if security_id not in best or rank > best[security_id]:
                best[security_id] = rank
                values[security_id] = str(record["value"])
        if scheme not in known_schemes:
            raise PitQueryError(
                f"unknown classification scheme {scheme!r}; known: "
                f"{sorted(known_schemes)} (RT-G020-N5: silent empties forbidden)"
            )
        return values

    # -- calendar (canonical_schemas.md §11) --------------------------------------

    def trading_days(
        self,
        calendar_id: str,
        start: date | None = None,
        end: date | None = None,
        *,
        table: str = "trading_calendars",
    ) -> tuple[date, ...]:
        """Trading days of ``calendar_id`` within ``[start, end]``.

        The §11 stub returns a ``TradingCalendar``; that type lands with
        the validation clock (G026) — until then the PIT surface exposes
        the underlying grid (documented interface deviation).
        """
        days: list[date] = []
        for record in self._records(table):
            if record.get("calendar_id") != calendar_id:
                continue
            if not record.get("is_trading_day"):
                continue
            day = record.get("event_date")
            if not isinstance(day, date):
                continue
            if start is not None and day < start:
                continue
            if end is not None and day > end:
                continue
            days.append(day)
        return tuple(sorted(days))
