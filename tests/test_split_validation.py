"""Tests for the split-ratio check in operations_service.execute_split.

A split ratio says how many new shares replace one old share: 2.0 is a 2:1
split (shares double), 0.5 is a 1:2 reverse split (shares halve). The app
accepts ratios from 0.001 to 1000 and rejects anything else before touching
the account.
"""

import pytest

import services.operations_service as operations_service
from domain.errors import ValidationError


@pytest.fixture
def split_recorder(monkeypatch):
    """Replace the real split-row builder with a stand-in that only records the ratio it receives.

    This isolates the validation: if the check lets a ratio through, the
    stand-in is called; if it rejects it, ValidationError is raised first.
    """
    received = []

    def fake_newrow_split(df, date_str, ref_date, broker, ticker, ratio):
        """Record the ratio instead of building a real split row."""
        received.append(ratio)
        return "split recorded"

    monkeypatch.setattr(operations_service, "newrow_split", fake_newrow_split)
    return received


@pytest.mark.parametrize("ratio", [0.001, 0.5, 2, 1000])
def test_ratios_in_range_are_accepted(ratio, split_recorder):
    """Ratios from 0.001 to 1000 (both ends included) reach the split builder, as floats."""
    result = operations_service.execute_split(None, "Broker", "01-07-2024", None, "AAA.MI", ratio)

    assert result == "split recorded"
    assert split_recorder == [float(ratio)]


@pytest.mark.parametrize("ratio", [0, -2, 0.0005, 1000.5, "2"])
def test_ratios_out_of_range_or_not_numbers_are_rejected(ratio, split_recorder):
    """Zero, negatives, values outside 0.001-1000 and non-numbers raise ValidationError."""
    with pytest.raises(ValidationError) as info:
        operations_service.execute_split(None, "Broker", "01-07-2024", None, "AAA.MI", ratio)

    assert info.value.key == "operations.split.ratio_error"
    assert split_recorder == []
