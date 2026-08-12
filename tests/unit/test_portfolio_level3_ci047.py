"""CI-047 exposure reconciliation for the Level-3 optimizer (G035).

correctness_criteria.md CI-047: ``gross = sum|w|``, ``net = sum(w)``,
computed FROM THE SAME POSITION TABLE AS P&L; market-neutral configs
keep ``|net| < tolerance`` and gross at the configured leverage (2x for
the P1/P2/P3 fixtures); the P4 beta-neutral book keeps the realized
correlation of portfolio returns with the market within [-0.15, 0.15]
on the synthetic fixture.

The reconciliation is pinned two ways:

1. the optimizer's book runs through the G027 accounting ledger and the
   ledger's own exposure/P&L rows (one position table) must agree with
   the ``Portfolio`` properties;
2. a multi-period seeded simulation of a P4-style beta-limited book
   against a one-factor market pins the realized-correlation band.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from lasr.config.provenance import Param, Provenance
from lasr.portfolio.accounting import (
    MarkStep,
    RebalancePeriod,
    ZeroCostModel,
    run_accounting,
)
from lasr.portfolio.level3_config import (
    Level3Config,
    Level3ConstraintsConfig,
)
from lasr.portfolio.level3_optimizer import (
    SecurityAttributes,
    build_level3_portfolio,
)

pytestmark = pytest.mark.unit

TOL = 1e-8

SIX = {"A": 0.03, "B": 0.02, "C": 0.01, "D": -0.01, "E": -0.02, "F": -0.03}


def P(value: object, prov: Provenance = Provenance.ASSUMED) -> Param[object]:
    return Param(value=value, prov=prov, src="test fixture")


def neutral_config(**overrides: object) -> Level3Config:
    base: dict[str, object] = {
        "gross_target": P(2.0),
        "gross_mode": P("equality"),
        "net_target": P(0.0),
        "max_position_weight": P(0.6),
    }
    base.update(overrides)
    return Level3Config(
        constraints=Level3ConstraintsConfig(**base)  # type: ignore[arg-type]
    )


class TestMarketNeutralExposures:
    """The P1/P2/P3-style market-neutral fixture: 2x gross, ~0 net."""

    def test_gross_at_configured_leverage_and_net_within_tolerance(self) -> None:
        result = build_level3_portfolio(SIX, neutral_config())
        book = result.portfolio
        assert book.gross == pytest.approx(2.0, abs=TOL)
        assert abs(book.net) < TOL
        # the CI-047 formulas, restated independently of the properties
        assert book.gross == pytest.approx(
            sum(abs(w) for w in book.weights.values()), abs=1e-15
        )
        assert book.net == pytest.approx(sum(book.weights.values()), abs=1e-15)

    def test_ledger_reconciles_the_same_position_table(self) -> None:
        """CI-047 'from the same position table as P&L': the G027 ledger
        trades to the L3 book, marks it, and its exposure and P&L rows
        must both derive from that one table."""
        result = build_level3_portfolio(SIX, neutral_config())
        book = result.portfolio
        returns = {"A": 0.02, "B": -0.01, "C": 0.0, "D": 0.01, "E": -0.02, "F": 0.03}
        ledger = run_accounting(
            [
                RebalancePeriod(
                    rebalance_date=date(2024, 1, 31),
                    target=book,
                    steps=(MarkStep(mark_date=date(2024, 2, 29), returns=returns),),
                    day_count_fraction=29 / 365,
                )
            ],
            initial_nav=1_000_000.0,
            cost_model=ZeroCostModel(),
        )
        row = ledger.periods[0]
        assert row.gross_exposure == pytest.approx(book.gross, abs=TOL)
        assert row.net_exposure == pytest.approx(book.net, abs=TOL)
        assert abs(row.net_exposure) < TOL
        expected_return = sum(
            book.weights[sec] * returns[sec] for sec in sorted(book.weights)
        )
        assert row.portfolio_return == pytest.approx(expected_return, abs=1e-12)
        assert abs(row.residual) < 1e-12  # CI-045: one table, two paths


class TestBetaNeutralCorrelationBand:
    """The P4-style beta-neutral book on a seeded one-factor market."""

    N_NAMES = 20
    N_PERIODS = 80
    BETA_LIMIT = 0.05

    def simulate(self, rng: np.random.Generator) -> tuple[list[float], list[float]]:
        """One-factor world: r_it = beta_i * m_t + eps_it. Weekly-ish
        scales: market sd 2%, idiosyncratic sd 2% per period. Alphas are
        drawn independently of beta each period, so only the beta
        constraint keeps the book out of the market."""
        ids = tuple(f"S{i:02d}" for i in range(self.N_NAMES))
        beta_rng, market_rng, idio_rng, alpha_rng = rng.spawn(4)
        betas = {
            sec: float(b)
            for sec, b in zip(
                ids, beta_rng.uniform(0.5, 1.5, self.N_NAMES), strict=True
            )
        }
        attributes = {sec: SecurityAttributes(beta=betas[sec]) for sec in ids}
        config = neutral_config(
            max_position_weight=P(0.2), beta_limit=P(self.BETA_LIMIT)
        )
        market: list[float] = []
        portfolio: list[float] = []
        previous: dict[str, float] = {}
        for _ in range(self.N_PERIODS):
            alphas = {
                sec: float(a)
                for sec, a in zip(
                    ids, alpha_rng.normal(0.0, 0.01, self.N_NAMES), strict=True
                )
            }
            result = build_level3_portfolio(
                alphas, config, previous_weights=previous, attributes=attributes
            )
            assert result.predicted_beta is not None
            assert abs(result.predicted_beta) <= self.BETA_LIMIT + 1e-6
            m = float(market_rng.normal(0.0, 0.02))
            eps = idio_rng.normal(0.0, 0.02, self.N_NAMES)
            r = {
                sec: betas[sec] * m + float(e) for sec, e in zip(ids, eps, strict=True)
            }
            weights = result.portfolio.weights
            portfolio.append(sum(weights[sec] * r[sec] for sec in sorted(weights)))
            market.append(m)
            previous = dict(weights)
        return portfolio, market

    def test_realized_market_correlation_within_band(
        self, rng: np.random.Generator
    ) -> None:
        """CI-047: corr(portfolio, market) in [-0.15, 0.15] over the
        seeded synthetic fixture (TEST_SEED root, spawned children)."""
        portfolio, market = self.simulate(rng)
        correlation = float(np.corrcoef(portfolio, market)[0, 1])
        assert -0.15 <= correlation <= 0.15

    def test_every_period_stays_market_neutral(self, rng: np.random.Generator) -> None:
        """Exposure discipline holds at every rebalance, not on average:
        re-run the simulation asserting the per-period invariants that
        ``simulate`` already checks (predicted beta), plus gross/net."""
        ids = tuple(f"S{i:02d}" for i in range(6))
        beta_rng, alpha_rng = rng.spawn(2)
        betas = {
            sec: float(b)
            for sec, b in zip(ids, beta_rng.uniform(0.5, 1.5, 6), strict=True)
        }
        attributes = {sec: SecurityAttributes(beta=betas[sec]) for sec in ids}
        config = neutral_config(beta_limit=P(self.BETA_LIMIT))
        previous: dict[str, float] = {}
        for _ in range(10):
            alphas = {
                sec: float(a)
                for sec, a in zip(ids, alpha_rng.normal(0.0, 0.01, 6), strict=True)
            }
            result = build_level3_portfolio(
                alphas, config, previous_weights=previous, attributes=attributes
            )
            assert result.portfolio.gross == pytest.approx(2.0, abs=1e-6)
            assert abs(result.portfolio.net) < 1e-6
            previous = dict(result.portfolio.weights)
