"""Tests for config_service.save_brokers: writing the account list to config.ini.

The accounts live in the user's config.ini as a [Brokers] section, e.g.
    [Brokers]
    1 = Fineco
    2 = Directa
The section ends up with exactly the brokers given (e.g. after an account is
deleted: see test_remove_broker_deletes_it_everywhere in test_app_state.py).
"""

import configparser

from services.config_service import save_brokers, save_watchlist


def read_section(folder, section):
    """Return the entries of `section` in folder/config.ini as a dict, e.g. {"1": "Fineco"}."""
    config = configparser.ConfigParser()
    config.read(folder / "config.ini")
    return dict(config.items(section)) if config.has_section(section) else {}


def test_replacing_the_accounts_leaves_other_sections_untouched(tmp_path):
    """Replacing [Brokers] must not affect the rest of config.ini, e.g. the watchlist."""
    save_watchlist(str(tmp_path), ["AAPL", "ISP.MI"])
    save_brokers(str(tmp_path), {1: "Fineco", 2: "Directa"})

    save_brokers(str(tmp_path), {1: "Fineco"})

    assert read_section(tmp_path, "Watchlist") == {"tickers": "AAPL,ISP.MI"}
