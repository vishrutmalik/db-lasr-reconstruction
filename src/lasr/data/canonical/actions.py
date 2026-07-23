"""Corporate-action derivations: adjustment factors, delisting-return view.

# arch: canonical_schemas.md §2.1: cumulative split/dividend factors are
computed from ``corporate_actions`` by the canonical layer — NEVER
provider-supplied (FM-17: the provider adjustment basis is
NOT_ESTABLISHED). CI-049 substrate: a split or dividend produces zero
phantom return through the factor identity, and every price discontinuity
has exactly one typed explanation.

Factor convention (documented; pinned by the hand-ledger test):

- ``split_factor_cum(t)`` = ∏ over split-type actions with action date
  ≤ t of ``ratio_num / ratio_den``. Adjusted price
  ``close_adj = close x split_factor_cum`` puts every date on the
  pre-action share basis, so a 2:1 split (price halves, factor doubles)
  yields a continuous adjusted series: r = (c/2 x 2f)/(c x f) - 1 = 0.
- ``total_return_factor_cum(t)`` additionally multiplies, on each cash
  dividend's action date, ``1 + amount / close(action date)`` — so the
  adjusted-series return over the ex-date equals the economic total return
  ``(close_ex + amount) / close_prev - 1`` exactly (CI-019
  ``return_type=total``).
- The *action date* is ``ex_date`` when present, else ``effective_date``.
- ``knowledge_time`` per §2.1 = max ``announcement_time`` over the actions
  contributing to the row's cumulative value (an announcement may precede
  the effective date — the documented U3 exception).

N-2 / CI-049 single home: ``corporate_actions.terminal_return`` is
authoritative; :func:`derive_delisting_returns` populates the DERIVED
``listing_intervals.delisting_return`` view from it.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date, datetime

from lasr.core.errors import SchemaValidationError
from lasr.data.canonical.builders import BuildContext, BuildResult
from lasr.data.providers.base import FieldFamily, grade_dataset
from lasr.data.schemas.base import Row
from lasr.data.schemas.corporate_actions import ActionType

__all__ = [
    "build_adjustment_factors",
    "compute_adjustment_factors",
    "derive_delisting_returns",
]

logger = logging.getLogger(__name__)

_SPLIT_TYPES = frozenset({ActionType.SPLIT.value, ActionType.STOCK_DIVIDEND.value})


def _action_date(action: Row) -> date:
    ex = action.get("ex_date")
    if isinstance(ex, date):
        return ex
    effective = action.get("effective_date")
    if isinstance(effective, date):
        return effective
    raise SchemaValidationError(
        "adjustment_factors",
        (f"action {action.get('action_id')!r} has no usable date",),
    )


def compute_adjustment_factors(
    action_records: Sequence[Row],
    price_records: Sequence[Row],
) -> tuple[Row, ...]:
    """Cumulative factors per security at every factor-change date (§2.1).

    ``price_records`` supplies the unadjusted close on each cash dividend's
    action date (required for the total-return factor); a missing close is
    an error, never a silently skipped dividend.
    """
    closes: dict[tuple[object, object], float] = {}
    for record in price_records:
        close = record.get("close")
        if isinstance(close, int | float):
            closes[(record["security_id"], record["event_date"])] = float(close)
    by_security: dict[str, list[Row]] = {}
    for action in action_records:
        by_security.setdefault(str(action["security_id"]), []).append(action)
    rows: list[Row] = []
    for security_id in sorted(by_security):
        actions = sorted(
            by_security[security_id],
            key=lambda a: (_action_date(a), str(a.get("action_id"))),
        )
        split_cum = 1.0
        tr_cum = 1.0
        contributing: list[str] = []
        max_announcement: datetime | None = None
        by_date: dict[date, list[Row]] = {}
        for action in actions:
            by_date.setdefault(_action_date(action), []).append(action)
        for when in sorted(by_date):
            changed = False
            for action in by_date[when]:
                action_type = str(action["action_type"])
                if action_type in _SPLIT_TYPES:
                    num = action.get("ratio_num")
                    den = action.get("ratio_den")
                    if not (
                        isinstance(num, int | float) and isinstance(den, int | float)
                    ):
                        raise SchemaValidationError(
                            "adjustment_factors",
                            (
                                f"split action {action.get('action_id')!r} "
                                "lacks a ratio",
                            ),
                        )
                    split_cum *= float(num) / float(den)
                    tr_cum *= float(num) / float(den)
                elif action_type == ActionType.CASH_DIVIDEND.value:
                    amount = action.get("amount")
                    if not isinstance(amount, int | float):
                        raise SchemaValidationError(
                            "adjustment_factors",
                            (f"dividend {action.get('action_id')!r} lacks an amount",),
                        )
                    close = closes.get((security_id, when))
                    if close is None:
                        raise SchemaValidationError(
                            "adjustment_factors",
                            (
                                f"no unadjusted close for {security_id!r} on "
                                f"{when.isoformat()} — the total-return factor "
                                "needs the ex-date close (CI-019/CI-049)",
                            ),
                        )
                    tr_cum *= 1.0 + float(amount) / close
                else:
                    continue  # non-price actions carry no factor
                changed = True
                contributing.append(str(action["action_id"]))
                announcement = action.get("announcement_time")
                if not isinstance(announcement, datetime):
                    raise SchemaValidationError(
                        "adjustment_factors",
                        (
                            f"action {action.get('action_id')!r} has no "
                            "announcement_time; factors need a knowledge "
                            "time (§2.1)",
                        ),
                    )
                if max_announcement is None or announcement > max_announcement:
                    max_announcement = announcement
            if not changed:
                continue
            assert max_announcement is not None  # set with the first change
            rows.append(
                {
                    "security_id": security_id,
                    "event_date": when,
                    "split_factor_cum": split_cum,
                    "total_return_factor_cum": tr_cum,
                    "derived_from_action_ids": tuple(contributing),
                    "knowledge_time": max_announcement,
                }
            )
    return tuple(rows)


def build_adjustment_factors(
    action_records: Sequence[Row],
    price_records: Sequence[Row],
    ctx: BuildContext,
) -> BuildResult:
    """``adjustment_factors`` build (§2.1 derived canonical).

    The manifest is graded under ``CORPORATE_ACTIONS`` — the factors
    inherit the knowledge semantics of the action feed they derive from.
    """
    records = compute_adjustment_factors(action_records, price_records)
    grade = grade_dataset(
        FieldFamily.CORPORATE_ACTIONS,
        ctx.capability,
        synthetic_truth=ctx.stamping.synthetic_truth,
        adjustment_basis_acknowledged=ctx.stamping.adjustment_basis_acknowledged,
    )
    return BuildResult(
        table_name="adjustment_factors",
        family=FieldFamily.CORPORATE_ACTIONS,
        records=records,
        pit_grade=grade,
        downgrade_events=(),
        context=ctx,
        notes="derived from corporate_actions; never provider-supplied (FM-17)",
    )


def derive_delisting_returns(
    listing_records: Sequence[Row],
    action_records: Sequence[Row],
) -> tuple[Row, ...]:
    """Populate the DERIVED ``listing_intervals.delisting_return`` view from
    its authoritative home ``corporate_actions.terminal_return`` (N-2,
    CI-049 single-home rule).

    For each delisting action with a terminal return: the security's open
    listing interval (or the interval whose ``delisting_date`` equals the
    action's effective date) receives ``delisting_date`` +
    ``delisting_return``. Ambiguity (two candidate intervals) is an error.
    """
    updated = [dict(record) for record in listing_records]
    for action in sorted(
        action_records, key=lambda a: (str(a.get("security_id")), _action_date(a))
    ):
        if str(action["action_type"]) != ActionType.DELISTING.value:
            continue
        terminal = action.get("terminal_return")
        if terminal is None:
            continue
        security_id = action["security_id"]
        effective = action.get("effective_date")
        candidates = [
            record
            for record in updated
            if record["security_id"] == security_id
            and (
                record.get("delisting_date") is None
                or record.get("delisting_date") == effective
            )
        ]
        if len(candidates) != 1:
            raise SchemaValidationError(
                "listing_intervals",
                (
                    f"delisting for {security_id!r} matches {len(candidates)} "
                    "listing intervals; the terminal return has exactly one "
                    "home (CI-049)",
                ),
            )
        candidates[0]["delisting_date"] = effective
        candidates[0]["delisting_return"] = terminal
        logger.info(
            "delisting return derived: security=%s effective=%s return=%s",
            security_id,
            effective,
            terminal,
        )
    return tuple(updated)
