"""Tests for the split-ratio check in operations_service.parse_split_ratio.

A split ratio says how many new shares replace one old share: 2.0 is a 2:1
split (shares double), 0.5 is a 1:2 reverse split (shares halve). The app
accepts ratios from 0.001 to 1000 and rejects anything else before touching
the account.
"""

import pytest

from domain.errors import ValidationError
from services.operations_service import parse_split_ratio


@pytest.mark.parametrize("text, ratio", [("0.001", 0.001), ("0.5", 0.5), ("2", 2.0), ("1000", 1000.0)])
def test_ratios_in_range_are_accepted(text, ratio):
    """Ratios from 0.001 to 1000 (both ends included) are accepted, as floats."""
    assert parse_split_ratio(text) == ratio


@pytest.mark.parametrize("text", ["0", "-2", "0.0005", "1000.5", "two", "", None])
def test_ratios_out_of_range_or_not_numbers_are_rejected(text):
    """Zero, negatives, values outside 0.001-1000, non-numbers and a blank field raise ValidationError."""
    with pytest.raises(ValidationError) as info:
        parse_split_ratio(text)

    assert info.value.key == "operations.split.ratio_error"
