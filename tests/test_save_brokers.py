"""Tests for config_service.save_brokers: writing the account list to config.ini.

The accounts live in the user's config.ini as a [Brokers] section, e.g.
    [Brokers]
    1 = Fineco
    2 = Directa
With reset=True the section must end up with exactly the brokers given (used
when an account is deleted); with reset=False existing entries are kept.
"""

import configparser

from services.config_service import save_brokers, save_watchlist


def read_section(folder, section):
    """Return the entries of `section` in folder/config.ini as a dict, e.g. {"1": "Fineco"}."""
    config = configparser.ConfigParser()
    config.read(folder / "config.ini")
    return dict(config.items(section)) if config.has_section(section) else {}


def test_reset_creates_the_section_on_first_save(tmp_path):
    """First-launch setup: with no config.ini yet, reset=True writes the brokers given."""
    save_brokers(str(tmp_path), {1: "Fineco", 2: "Directa"}, reset=True)

    assert read_section(tmp_path, "Brokers") == {"1": "Fineco", "2": "Directa"}


def test_reset_drops_a_deleted_account(tmp_path):
    """Deleting "Directa": its line must disappear, or the account would come back on the next launch."""
    save_brokers(str(tmp_path), {1: "Fineco", 2: "Directa"}, reset=True)

    save_brokers(str(tmp_path), {1: "Fineco"}, reset=True)

    assert read_section(tmp_path, "Brokers") == {"1": "Fineco"}


def test_without_reset_existing_entries_are_kept(tmp_path):
    """Adding an account with reset=False keeps the entries already in the file."""
    save_brokers(str(tmp_path), {1: "Fineco"}, reset=True)

    save_brokers(str(tmp_path), {2: "Directa"}, reset=False)

    assert read_section(tmp_path, "Brokers") == {"1": "Fineco", "2": "Directa"}


def test_reset_leaves_other_sections_untouched(tmp_path):
    """Resetting [Brokers] must not affect the rest of config.ini, e.g. the watchlist."""
    save_watchlist(str(tmp_path), ["AAPL", "ISP.MI"])
    save_brokers(str(tmp_path), {1: "Fineco", 2: "Directa"}, reset=True)

    save_brokers(str(tmp_path), {1: "Fineco"}, reset=True)

    assert read_section(tmp_path, "Watchlist") == {"tickers": "AAPL,ISP.MI"}
