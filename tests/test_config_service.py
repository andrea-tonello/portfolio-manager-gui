"""Tests for the save_* functions in services/config_service.py: what each one writes to config.ini.

Settings live in config.ini files (one for the app, one per user), e.g.
    [Theme]
    mode = dark
    color = teal
Each save_* function updates one section and must leave the rest of the file
as it was. (save_brokers has its own tests in test_save_brokers.py.)
"""

import configparser

import pytest

from services import config_service


def read_config(folder):
    """Return folder/config.ini as {section: {option: value}}."""
    config = configparser.ConfigParser()
    config.read(folder / "config.ini")
    return {section: dict(config.items(section)) for section in config.sections()}


SAVES = [
    pytest.param(lambda f: config_service.save_language(f, "it"),
                 {"Language": {"code": "it"}}, id="language"),
    pytest.param(lambda f: config_service.save_theme(f, "dark", "teal"),
                 {"Theme": {"mode": "dark", "color": "teal"}}, id="theme"),
    pytest.param(lambda f: config_service.save_watchlist(f, ["AAA.MI", "BBB.MI"]),
                 {"Watchlist": {"tickers": "AAA.MI,BBB.MI"}}, id="watchlist"),
    pytest.param(lambda f: config_service.save_brokers(f, {1: "Fineco", 2: "Directa"}),
                 {"Brokers": {"1": "Fineco", "2": "Directa"}}, id="brokers"),
    pytest.param(lambda f: config_service.save_home_hidden(f, True),
                 {"Home": {"hidden": "true"}}, id="home-hidden"),
    pytest.param(lambda f: config_service.save_home_pnl_mode(f, 2),
                 {"Home": {"pnl_mode": "2"}}, id="home-pnl-mode"),
    pytest.param(lambda f: config_service.save_split_ignores(f, {"BBB.MI|*", "AAA.MI|2024-07-01"}),
                 {"SplitIgnores": {"entries": "AAA.MI|2024-07-01,BBB.MI|*"}}, id="split-ignores"),
    pytest.param(lambda f: config_service.save_tx_filter(f, "days", 30),
                 {"Transactions": {"filter_mode": "days", "filter_value": "30"}}, id="tx-filter"),
    pytest.param(lambda f: config_service.save_tx_columns(f, ["date", "pl"]),
                 {"Transactions": {"visible_columns": "date,pl"}}, id="tx-columns"),
    pytest.param(lambda f: config_service.save_users(f, {1: "Ann", 2: "Bob"}),
                 {"Users": {"1": "Ann", "2": "Bob"}}, id="users"),
    pytest.param(lambda f: config_service.save_active_user(f, 2),
                 {"Active": {"user": "2"}}, id="active-user"),
]


@pytest.mark.parametrize("save, written", SAVES)
def test_each_save_writes_its_section_and_keeps_the_rest(tmp_path, save, written):
    """Each save_* writes its own section, with these exact option names and text, and leaves [Other] alone."""
    (tmp_path / "config.ini").write_text("[Other]\nkeep = yes\n")

    save(str(tmp_path))

    assert read_config(tmp_path) == {"Other": {"keep": "yes"}, **written}


@pytest.mark.parametrize("save, written", SAVES)
def test_each_save_creates_config_ini_if_missing(tmp_path, save, written):
    """On first launch there is no config.ini yet: saving creates it with just that section."""
    save(str(tmp_path))

    assert read_config(tmp_path) == written


def test_saving_one_option_keeps_the_other_options_of_the_section(tmp_path):
    """[Home] holds two settings saved separately; saving one keeps the other."""
    config_service.save_home_hidden(str(tmp_path), True)
    config_service.save_home_pnl_mode(str(tmp_path), 1)

    assert read_config(tmp_path) == {"Home": {"hidden": "true", "pnl_mode": "1"}}


def test_users_are_replaced_not_merged(tmp_path):
    """save_users writes exactly the users given, so a deleted user disappears from the file."""
    (tmp_path / "config.ini").write_text("[Users]\n1 = Ann\n3 = Carl\n")

    config_service.save_users(str(tmp_path), {1: "Ann"})

    assert read_config(tmp_path) == {"Users": {"1": "Ann"}}


def test_clearing_split_ignores_leaves_an_empty_section(tmp_path):
    """With no ignored splits left, [SplitIgnores] stays in the file, empty."""
    (tmp_path / "config.ini").write_text("[SplitIgnores]\nentries = AAA.MI|*\n")

    config_service.save_split_ignores(str(tmp_path), set())

    assert read_config(tmp_path) == {"SplitIgnores": {}}
