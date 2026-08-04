"""Red-team keeper tests for G022 (docs/red_team/G022.md) — transforms.

Metamorphic probes DIFFERENT from the shipped unit suite (which pins the
F-P2-1 golden cell, shuffle-invariance and basic locality):

- winsorizer bounds frozen ACROSS dates: fit on date T, apply to a shifted
  date T' — every T' value must clip to T's bounds; refitting on T' gives
  different bounds (teeth), and refitting on T reproduces the original
  bounds bit-identically (no hidden state from the applies);
- rank monotone-extension: appending one strictly-lower member rescales
  every existing score by exactly n/(n+1) and preserves the relative
  order; interleaving an unrelated "other date" cross-section between two
  identical calls changes nothing (no module state);
- adversarial float ties: -0.0 vs 0.0 and 1e16 vs 1e16+1 (equal doubles)
  must share a rank under the ``average`` rule and split deterministically
  under ``security_id``; 0.1+0.2 vs 0.3 (UNEQUAL doubles) must never be
  treated as a tie; 40 shuffled runs produce exactly one output per rule.
"""

from __future__ import annotations

import math
import random

import pytest

from lasr.features.transforms import FittedWinsorizer, rank_normalize

pytestmark = pytest.mark.leakage


class TestWinsorizerCrossDateFreeze:
    def test_bounds_frozen_across_dates_with_teeth(self):
        date_t = {f"S{i}": float(i) for i in range(1, 101)}
        date_t1 = {f"S{i}": float(1000 + i) for i in range(1, 101)}
        fitted = FittedWinsorizer.fit(date_t, lower_quantile=0.05, upper_quantile=0.95)

        applied = fitted.apply(date_t1)
        # every T+1 value clips to date-T's (frozen) upper bound
        assert set(applied.values()) == {fitted.upper_bound}
        assert fitted.upper_bound < 1000.0
        # repeated application is bit-identical (no accumulation)
        assert fitted.apply(date_t1) == applied

        # teeth: a refit on T+1 WOULD give different bounds — so the frozen
        # application above genuinely used date-T state, not a refit
        refit_t1 = FittedWinsorizer.fit(
            date_t1, lower_quantile=0.05, upper_quantile=0.95
        )
        assert (refit_t1.lower_bound, refit_t1.upper_bound) != (
            fitted.lower_bound,
            fitted.upper_bound,
        )
        # and date-T bounds are reproducible after the applies (no drift)
        refit_t = FittedWinsorizer.fit(date_t, lower_quantile=0.05, upper_quantile=0.95)
        assert (refit_t.lower_bound, refit_t.upper_bound) == (
            fitted.lower_bound,
            fitted.upper_bound,
        )


class TestRankMetamorphic:
    def test_no_cross_call_state_and_monotone_extension(self):
        base = {f"S{i:02d}": math.sin(i * 1.7) * (i % 13) for i in range(50)}
        before = rank_normalize(base)
        rank_normalize({"X1": 5.0, "X2": -3.0})  # unrelated "other date"
        assert rank_normalize(base) == before  # no module-level state

        extended = {**base, "ZZZ_new": min(base.values()) - 1.0}
        after = rank_normalize(extended)
        n, m = len(base), len(extended)
        for security_id in base:
            assert after[security_id] == pytest.approx(
                before[security_id] * n / m, abs=1e-12
            )
        assert sorted(base, key=before.__getitem__) == sorted(
            base, key=after.__getitem__
        )

    def test_adversarial_float_ties_deterministic(self):
        cross_section = {
            "B": -0.0,
            "A": 0.0,
            "C": 1e16,
            "D": 1e16 + 1,  # == 1e16 as a double
            "E": 0.1 + 0.2,  # != 0.3 as a double
            "F": 0.3,
        }
        assert 1e16 == 1e16 + 1 and (0.1 + 0.2) != 0.3  # probe preconditions

        outputs_by_rule: dict[str, set] = {"security_id": set(), "average": set()}
        items = list(cross_section.items())
        for seed in range(20):
            random.Random(seed).shuffle(items)
            shuffled = dict(items)
            for rule in ("security_id", "average"):
                outputs_by_rule[rule].add(
                    tuple(sorted(rank_normalize(shuffled, tie_rule=rule).items()))
                )
        assert all(len(v) == 1 for v in outputs_by_rule.values())

        averaged = rank_normalize(cross_section, tie_rule="average")
        assert averaged["A"] == averaged["B"]  # -0.0 == 0.0 tie shared
        assert averaged["C"] == averaged["D"]  # equal doubles tie shared
        assert averaged["E"] != averaged["F"]  # NOT a tie: distinct doubles

        split = rank_normalize(cross_section, tie_rule="security_id")
        assert split["A"] != split["B"] and split["C"] != split["D"]
        # documented tie order: ascending security_id gets the lower score
        assert split["A"] < split["B"] and split["C"] < split["D"]
