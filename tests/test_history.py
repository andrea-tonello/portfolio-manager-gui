"""Tests for domain/history.py: how a failure while building the portfolio history is reported."""

import pandas as pd
import pytest

from domain.history import _build_portfolio_timeseries


def test_a_failure_while_building_the_history_names_its_cause():
    """The RuntimeError raised when the history can't be built points to the original error as its cause.

    The traceback then reads "The above exception was the direct cause of
    the following exception" and starts from the real problem (here a
    missing column).
    """
    broken = pd.DataFrame({"date": []})  # lacks the columns the history needs

    with pytest.raises(RuntimeError) as info:
        _build_portfolio_timeseries(broken, pd.DataFrame(), pd.DatetimeIndex([]), [], [])

    assert isinstance(info.value.__cause__, KeyError)
