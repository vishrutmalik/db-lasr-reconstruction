"""Level-1 simple portfolio tests (G027; MP §24 Level 1).

CI bindings in this file (docs/methodology/correctness_criteria.md):

- CI-050 — the fractile mapping matches the version spec: P1 US deciles /
  global quintiles resolved from the real nlasr_2012 config fixture
  (P1-35; OQ-P1-13 equal weighting), and the L/S spread return equals the
  top-fractile minus bottom-fractile equal-weight return on a hand
  fixture;
- CI-043 — deterministic ties + input-order invariance at the portfolio
  level;
- CI-047 substrate — gross = configured target, |net| ~ 0 by construction.

Property tests (task spec): for random score vectors the Level-1 book is
dollar-neutral to 1e-12 and the turnover between consecutive identical
score vectors is exactly zero.
"""

from __future__ import annotations

from math import fsum
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from lasr.config import load_version_spec
from lasr.config.sections import PortfolioConfig
from lasr.portfolio.base import Portfolio
from lasr.portfolio.errors import (
    NonFiniteInputError,
    PortfolioConfigError,
    UniverseTooSmallError,
)
from lasr.portfolio.simple import SimplePortfolioSpec, build_simple_portfolio

pytestmark = pytest.mark.unit

FIXTURE = Path(__file__).resolve().parents[2] / "tests/fixtures/config/nlasr_2012.yaml"

#: Ten names, scores descending in id: S01 has the highest score (10.0).
TEN = {f"S{i:02d}": float(11 - i) for i in range(1, 11)}

QUINTILE_SPEC = SimplePortfolioSpec(n_fractiles=5, gross_exposure=2.0)


def _one_way_turnover(a: Portfolio, b: Portfolio) -> float:
    union = sorted(set(a.weights) | set(b.weights))
    return 0.5 * fsum(
        abs(b.weights.get(sec, 0.0) - a.weights.get(sec, 0.0)) for sec in union
    )


class TestBuildSimplePortfolio:
    def test_hand_fixture_quintiles(self) -> None:
        """10 names, quintiles, gross 2: top two +0.5, bottom two -0.5."""
        book = build_simple_portfolio(TEN, QUINTILE_SPEC)
        assert book.weights == {
            "S01": 0.5,
            "S02": 0.5,
            "S09": -0.5,
            "S10": -0.5,
        }
        assert book.gross == 2.0
        assert book.net == 0.0
        assert book.gross_target == 2.0

    def test_uneven_legs_stay_dollar_neutral(self) -> None:
        """n=7, k=5 -> top bin 1 name, bottom bin 2 (A-G027-01): the long
        name carries +1.0, each short -0.5; legs still sum to +/-G/2."""
        scores = {f"S{i}": float(i) for i in range(7)}  # S6 highest
        book = build_simple_portfolio(scores, QUINTILE_SPEC)
        assert book.weights == {"S6": 1.0, "S0": -0.5, "S1": -0.5}
        assert book.net == 0.0

    def test_ci050_spread_equals_top_minus_bottom(self) -> None:
        """CI-050: with gross 2 the book return Σw·r equals the equal-weight
        top-fractile return minus the bottom-fractile return, by hand:
        top {S01,S02} returns (0.04, 0.02) -> mean 0.03; bottom {S09,S10}
        returns (-0.02, 0.04) -> mean 0.01; spread 0.02."""
        book = build_simple_portfolio(TEN, QUINTILE_SPEC)
        returns = {"S01": 0.04, "S02": 0.02, "S09": -0.02, "S10": 0.04}
        book_return = fsum(w * returns[sec] for sec, w in book.weights.items())
        assert book_return == pytest.approx(0.03 - 0.01, abs=1e-15)

    def test_deterministic_ties_and_order_invariance(self) -> None:
        """CI-043/OQ-P1-01: a boundary tie goes to the id rule; input order
        cannot change the book."""
        scores = {"A": 1.0, "B": 2.0, "C": 2.0, "D": 2.0, "E": 3.0}
        spec = SimplePortfolioSpec(n_fractiles=5, gross_exposure=2.0)
        book = build_simple_portfolio(scores, spec)
        # ascending: A(1), B(2), C(2), D(2), E(3) -> bottom=A, top=E
        assert book.weights == {"E": 1.0, "A": -1.0}
        shuffled = dict(reversed(list(scores.items())))
        assert build_simple_portfolio(shuffled, spec).weights == book.weights

    def test_gross_exposure_is_explicit(self) -> None:
        book = build_simple_portfolio(
            TEN, SimplePortfolioSpec(n_fractiles=5, gross_exposure=1.5)
        )
        assert book.gross == pytest.approx(1.5, abs=1e-12)
        assert book.weights["S01"] == pytest.approx(0.375, abs=1e-15)

    def test_small_universes_are_typed(self) -> None:
        """Empty and n=1 universes raise (task: typed behavior)."""
        with pytest.raises(UniverseTooSmallError):
            build_simple_portfolio({}, QUINTILE_SPEC)
        with pytest.raises(UniverseTooSmallError):
            build_simple_portfolio({"A": 1.0}, QUINTILE_SPEC)

    @given(
        scores=st.dictionaries(
            keys=st.sampled_from([f"S{i:02d}" for i in range(40)]),
            values=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False),
            min_size=5,
        )
    )
    def test_property_neutral_and_repeat_turnover_zero(
        self, scores: dict[str, float]
    ) -> None:
        """Task property: dollar-neutral to 1e-12; identical consecutive
        scores produce exactly zero turnover; gross hits the target."""
        book = build_simple_portfolio(scores, QUINTILE_SPEC)
        assert abs(book.net) <= 1e-12
        assert book.gross == pytest.approx(2.0, abs=1e-12)
        again = build_simple_portfolio(dict(scores), QUINTILE_SPEC)
        assert _one_way_turnover(book, again) == 0.0


@pytest.fixture(scope="module")
def portfolio_config() -> PortfolioConfig:
    """The real nlasr_2012 fixture's portfolio section (P1-35)."""
    return load_version_spec(FIXTURE).portfolio


class TestSpecFromConfig:
    def test_ci050_us_deciles_global_quintiles(
        self, portfolio_config: PortfolioConfig
    ) -> None:
        """CI-050: fractile scheme comes from the version spec, not code."""
        us = SimplePortfolioSpec.from_config(
            portfolio_config, fractile_key="us", gross_exposure=2.0
        )
        world = SimplePortfolioSpec.from_config(
            portfolio_config, fractile_key="global", gross_exposure=2.0
        )
        assert us.n_fractiles == 10
        assert world.n_fractiles == 5

    def test_unknown_fractile_key_is_typed(
        self, portfolio_config: PortfolioConfig
    ) -> None:
        with pytest.raises(PortfolioConfigError, match="fractile key"):
            SimplePortfolioSpec.from_config(
                portfolio_config, fractile_key="mars", gross_exposure=2.0
            )

    def test_wrong_mapping_is_typed(self) -> None:
        config = PortfolioConfig(
            signal_mapping={
                "value": "signal_weighted_ls",
                "prov": "EXPLICIT",
                "src": "E-P4-23",
            },
            turnover_limit_one_way_monthly={
                "value": None,
                "prov": "EXPLICIT_ABSENCE",
                "src": "E-P4-32",
            },
        )
        with pytest.raises(PortfolioConfigError, match="signal_mapping"):
            SimplePortfolioSpec.from_config(
                config, fractile_key="us", gross_exposure=2.0
            )

    def test_cap_weighted_fractiles_out_of_scope(self) -> None:
        """OQ-P1-13's cap-weighted alternative is a typed error at Level 1."""
        config = PortfolioConfig(
            signal_mapping={"value": "fractile_ls", "prov": "EXPLICIT", "src": "P1-35"},
            fractiles={"value": {"us": 10}, "prov": "EXPLICIT", "src": "P1-35"},
            fractile_weighting={
                "value": "cap_weighted",
                "prov": "ASSUMED",
                "src": "OQ-P1-13",
            },
            turnover_limit_one_way_monthly={
                "value": 0.30,
                "prov": "EXPLICIT",
                "src": "P1-36",
            },
        )
        with pytest.raises(PortfolioConfigError, match="cap"):
            SimplePortfolioSpec.from_config(
                config, fractile_key="us", gross_exposure=2.0
            )

    def test_bad_gross_is_typed(self, portfolio_config: PortfolioConfig) -> None:
        for gross in (0.0, -1.0, float("inf")):
            with pytest.raises(PortfolioConfigError, match="gross_exposure"):
                SimplePortfolioSpec.from_config(
                    portfolio_config, fractile_key="us", gross_exposure=gross
                )


class TestPortfolioType:
    def test_zero_weight_entries_forbidden(self) -> None:
        with pytest.raises(NonFiniteInputError, match="zero-weight"):
            Portfolio(weights={"A": 0.5, "B": 0.0}, gross_target=1.0)

    def test_non_finite_weight_forbidden(self) -> None:
        with pytest.raises(NonFiniteInputError):
            Portfolio(weights={"A": float("nan")}, gross_target=1.0)

    def test_weights_canonicalized_ascending(self) -> None:
        book = Portfolio(weights={"B": -0.5, "A": 0.5}, gross_target=1.0)
        assert list(book.weights) == ["A", "B"]
        assert book.long_ids == ("A",)
        assert book.short_ids == ("B",)
