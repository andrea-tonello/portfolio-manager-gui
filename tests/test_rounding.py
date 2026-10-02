"""Tests for round_half_up in utils/other_utils.py, used for every amount written to an account.

It rounds the number as written, halves away from zero, like a bank: 2.675
becomes 2.68. (Python's round() gives 2.67, because the float 2.675 is
really 2.67499999... and round() sends halves to the even neighbour.)
"""

import math

import pytest

from utils.other_utils import round_half_up


@pytest.mark.parametrize("value, decimal, expected", [
    (2.675, "0.01", 2.68),
    (-2.675, "0.01", -2.68),
    (2.674, "0.01", 2.67),
    (100.12345, "0.0001", 100.1235),
    (3, "0.01", 3.0),
])
def test_rounds_halves_away_from_zero(value, decimal, expected):
    """Amounts are rounded to `decimal` places, halves away from zero."""
    assert round_half_up(value, decimal=decimal) == expected


@pytest.mark.parametrize("value", [float("nan"), None])
def test_missing_values_stay_missing(value):
    """An empty cell (NaN or None) gives NaN, so empty columns stay empty in the CSV."""
    assert math.isnan(round_half_up(value))


@pytest.mark.parametrize("value", ["abc", float("inf")])
def test_values_that_are_not_finite_numbers_raise(value):
    """Text or an infinite amount raises ValueError.

    They used to come back unchanged and could end up written into an
    account row.
    """
    with pytest.raises(ValueError):
        round_half_up(value)
