import os
import configparser
import shutil


def _load_config(config_folder: str):
    """Read config.ini and return (path, ConfigParser)."""
    path = os.path.join(config_folder, "config.ini")
    config = configparser.ConfigParser()
    if os.path.exists(path):
        config.read(path)
    return path, config


def _save_config(path: str, config: configparser.ConfigParser):
    """Write config back to disk."""
    with open(path, "w", encoding="utf-8") as f:
        config.write(f)


def _ensure_section(config: configparser.ConfigParser, section: str):
    if not config.has_section(section):
        config.add_section(section)


def save_language(config_folder: str, lang_code: str):
    path, config = _load_config(config_folder)
    _ensure_section(config, "Language")
    config.set("Language", "code", lang_code)
    _save_config(path, config)


def save_theme(config_folder: str, mode: str, color: str):
    path, config = _load_config(config_folder)
    _ensure_section(config, "Theme")
    config.set("Theme", "mode", mode)
    config.set("Theme", "color", color)
    _save_config(path, config)


def save_watchlist(config_folder: str, tickers: list[str]):
    path, config = _load_config(config_folder)
    _ensure_section(config, "Watchlist")
    config.set("Watchlist", "tickers", ",".join(tickers))
    _save_config(path, config)


def save_brokers(config_folder: str, brokers: dict[int, str], reset: bool = False):
    path, config = _load_config(config_folder)
    if reset and config.has_section("Brokers"):
        config.remove_section("Brokers")
    _ensure_section(config, "Brokers")
    if reset:
        for key in list(config["Brokers"].keys()):
            config.remove_option("Brokers", key)
    for idx, name in brokers.items():
        config.set("Brokers", str(idx), name)
    _save_config(path, config)


def save_home_hidden(config_folder: str, hidden: bool):
    path, config = _load_config(config_folder)
    _ensure_section(config, "Home")
    config.set("Home", "hidden", str(hidden).lower())
    _save_config(path, config)


def reset_application(config_folder: str):
    if os.path.exists(config_folder):
        shutil.rmtree(config_folder)
