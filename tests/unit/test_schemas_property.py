"""Property tests for interval logic and the knowable predicate (G017).

Hypothesis with an explicitly derandomized profile so the suite is
deterministic regardless of environment (CI-042 discipline; the conftest
"ci" profile derandomizes only under CI env).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from lasr.core import DateInterval, TimeSemanticsError, knowable

pytestmark = pytest.mark.unit

DETERMINISTIC = settings(derandomize=True, max_examples=200)

_dates = st.dates(min_value=date(1980, 1, 1), max_value=date(2049, 12, 31))
_datetimes = st.datetimes(
    min_value=datetime(1980, 1, 1),
    max_value=datetime(2049, 12, 31),
    timezones=st.just(UTC),
)
_lags = st.timedeltas(min_value=timedelta(0), max_value=timedelta(days=365))


@st.composite
def _intervals(draw: st.DrawFn) -> DateInterval:
    start = draw(_dates)
    end = draw(
        st.one_of(
            st.none(),
            st.dates(min_value=start, max_value=date(2049, 12, 31)),
        )
    )
    return DateInterval(start, end)


class TestDateIntervalProperties:
    @DETERMINISTIC
    @given(ivl=_intervals())
    def test_endpoints_contained(self, ivl: DateInterval) -> None:
        assert ivl.contains(ivl.valid_from)
        if ivl.valid_to is not None:
            assert ivl.contains(ivl.valid_to)

    @DETERMINISTIC
    @given(ivl=_intervals())
    def test_outside_endpoints_not_contained(self, ivl: DateInterval) -> None:
        if ivl.valid_from > date.min:
            assert not ivl.contains(ivl.valid_from - timedelta(days=1))
        if ivl.valid_to is not None and ivl.valid_to < date.max:
            assert not ivl.contains(ivl.valid_to + timedelta(days=1))

    @DETERMINISTIC
    @given(a=_intervals(), b=_intervals())
    def test_overlap_symmetric(self, a: DateInterval, b: DateInterval) -> None:
        assert a.overlaps(b) == b.overlaps(a)

    @DETERMINISTIC
    @given(a=_intervals(), b=_intervals())
    def test_overlap_iff_later_start_in_both(
        self, a: DateInterval, b: DateInterval
    ) -> None:
        """For inclusive date intervals, two intervals overlap exactly when
        the later start day lies in both."""
        later_start = max(a.valid_from, b.valid_from)
        assert a.overlaps(b) == (a.contains(later_start) and b.contains(later_start))

    @DETERMINISTIC
    @given(start=_dates, days=st.integers(min_value=1, max_value=10_000))
    def test_ci003_inverted_interval_always_rejected(
        self, start: date, days: int
    ) -> None:
        if start - timedelta(days=days) >= date.min:
            with pytest.raises(TimeSemanticsError):
                DateInterval(start, start - timedelta(days=days))


class TestKnowableProperties:
    @DETERMINISTIC
    @given(kt=_datetimes, as_of=_datetimes)
    def test_ci001_definition(self, kt: datetime, as_of: datetime) -> None:
        assert knowable(kt, as_of) == (kt <= as_of)

    @DETERMINISTIC
    @given(kt=_datetimes, as_of=_datetimes, lag=_lags)
    def test_ci005_lag_only_restricts(
        self, kt: datetime, as_of: datetime, lag: timedelta
    ) -> None:
        """A configured lag can only shrink the knowable set (CI-005)."""
        if knowable(kt, as_of, lag=lag):
            assert knowable(kt, as_of)

    @DETERMINISTIC
    @given(kt=_datetimes, as_of=_datetimes, later=_lags)
    def test_monotone_in_as_of(
        self, kt: datetime, as_of: datetime, later: timedelta
    ) -> None:
        """Once knowable, always knowable: append-only history (CI-002)."""
        if knowable(kt, as_of) and as_of + later <= datetime(2050, 1, 1, tzinfo=UTC):
            assert knowable(kt, as_of + later)
