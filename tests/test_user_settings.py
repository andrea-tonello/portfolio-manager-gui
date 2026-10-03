"""Tests for how AppState.load_config reads the active user's settings.

Each user has a config.ini in config/users/<name>/, e.g.
    [Brokers]
    1 = Fineco
    [Watchlist]
    tickers = AAA.MI,BBB.MI
    [Home]
    hidden = true
    pnl_mode = 2
    [SplitIgnores]
    entries = AAA.MI|*
Missing sections or unreadable values fall back to defaults.
"""

import pytest

from app_state import AppState
from services.config_service import UserSettings, load_user_settings


def _state_for(tmp_path, user_config=None):
    """Return an AppState whose active user "Ann" has `user_config` as config.ini text (None: no file), loaded."""
    config = tmp_path / "config"
    (config / "users" / "Ann").mkdir(parents=True)
    (config / "config.ini").write_text("[Users]\n1 = Ann\n[Active]\nuser = 1\n")
    if user_config is not None:
        (config / "users" / "Ann" / "config.ini").write_text(user_config)
    state = AppState(base_path=str(tmp_path))
    state.load_config()
    return state


def _settings(state):
    """The per-user settings AppState holds, as one dict for comparing."""
    return {
        "brokers": state.brokers,
        "watchlist": state.watchlist,
        "hidden": state.home_values_hidden,
        "pnl_mode": state.home_pnl_mode,
        "split_ignores": state.split_ignores,
    }


DEFAULTS = {"brokers": {}, "watchlist": [], "hidden": False, "pnl_mode": 0, "split_ignores": set()}


def test_every_setting_is_read(tmp_path):
    """Brokers, watchlist (spaces and empty entries dropped), Home options and ignored splits are all loaded."""
    state = _state_for(tmp_path, (
        "[Brokers]\n1 = Fineco\n3 = Directa\n"
        "[Watchlist]\ntickers = AAA.MI, BBB.MI,\n"
        "[Home]\nhidden = true\npnl_mode = 2\n"
        "[SplitIgnores]\nentries = AAA.MI|*,BBB.MI|2024-07-01\n"
    ))

    assert _settings(state) == {
        "brokers": {1: "Fineco", 3: "Directa"},
        "watchlist": ["AAA.MI", "BBB.MI"],
        "hidden": True,
        "pnl_mode": 2,
        "split_ignores": {"AAA.MI|*", "BBB.MI|2024-07-01"},
    }
    assert state.user_config_folder == str(tmp_path / "config" / "users" / "Ann")
    assert state.config_res_folder == str(tmp_path / "config" / "users" / "Ann" / "resources")


@pytest.mark.parametrize("user_config", [None, ""], ids=["no-file", "empty-file"])
def test_missing_settings_use_the_defaults(tmp_path, user_config):
    """Without a config.ini, or with an empty one, every setting has its default."""
    assert _settings(_state_for(tmp_path, user_config)) == DEFAULTS


@pytest.mark.parametrize("user_config, setting, expected", [
    ("[Brokers]\nfirst = Fineco\n", "brokers", {}),       # broker numbers must be integers
    ("[Home]\npnl_mode = 7\n", "pnl_mode", 0),            # only 0, 1 and 2 exist
    ("[Home]\npnl_mode = two\n", "pnl_mode", 0),
    ("[Home]\nhidden = yes\n", "hidden", False),          # only "true" means hidden
])
def test_unreadable_values_fall_back_to_the_default(tmp_path, user_config, setting, expected):
    """A value the app can't use is replaced by that setting's default."""
    assert _settings(_state_for(tmp_path, user_config))[setting] == expected


def test_no_active_user_means_defaults_and_no_folders(tmp_path):
    """Before any user exists, the settings are the defaults and there are no user folders."""
    state = AppState(base_path=str(tmp_path))
    state.load_config()

    assert _settings(state) == DEFAULTS
    assert (state.active_user_name, state.user_config_folder, state.config_res_folder) == (None, None, None)


def test_load_user_settings_reads_one_users_file(tmp_path):
    """config_service.load_user_settings is the reader behind load_config; it returns a UserSettings."""
    (tmp_path / "config.ini").write_text("[Brokers]\n1 = Fineco\n[Home]\nhidden = true\n")

    assert load_user_settings(str(tmp_path)) == UserSettings(brokers={1: "Fineco"}, values_hidden=True)
