"""Tests for config_service.load_tx_filter: which operations the Transactions screen lists.

The filter is saved in the user's config.ini, e.g.
    [Transactions]
    filter_mode = days
    filter_value = 30
"count" lists the last N operations, "days" those of the last N days. When
nothing usable is saved, the defaults are the last 5 operations or the last
90 days (DEFAULT_TX_FILTER).
"""

import pytest

from services.config_service import load_tx_filter, save_tx_filter


def test_nothing_saved_lists_the_last_5_operations(tmp_path):
    """With no config.ini, the screen lists the last 5 operations."""
    assert load_tx_filter(str(tmp_path)) == ("count", 5)


def test_saved_filter_is_read_back(tmp_path):
    """A filter saved by the screen is loaded unchanged."""
    save_tx_filter(str(tmp_path), "days", 30)

    assert load_tx_filter(str(tmp_path)) == ("days", 30)


@pytest.mark.parametrize("value_line", ["filter_value = 0\n", "filter_value = abc\n", ""],
                         ids=["zero", "not-a-number", "missing"])
@pytest.mark.parametrize("mode, default", [("count", 5), ("days", 90)])
def test_unusable_value_falls_back_to_the_default_of_the_saved_mode(tmp_path, mode, default, value_line):
    """A zero, non-numeric or missing value gives the saved mode's default: 5 operations or 90 days.

    Before D2 a *missing* value always gave 5, even in "days" mode.
    """
    (tmp_path / "config.ini").write_text(f"[Transactions]\nfilter_mode = {mode}\n{value_line}")

    assert load_tx_filter(str(tmp_path)) == (mode, default)
