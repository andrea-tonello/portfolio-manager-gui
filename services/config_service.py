import os
import configparser
import shutil


def save_language(config_folder: str, lang_code: str):
    path = os.path.join(config_folder, "config.ini")
    config = configparser.ConfigParser()
    if os.path.exists(path):
        config.read(path)
    if not config.has_section("Language"):
        config.add_section("Language")
    config.set("Language", "code", lang_code)
    with open(path, "w", encoding="utf-8") as f:
        config.write(f)


def save_theme(config_folder: str, mode: str, color: str):
    path = os.path.join(config_folder, "config.ini")
    config = configparser.ConfigParser()
    if os.path.exists(path):
        config.read(path)
    if not config.has_section("Theme"):
        config.add_section("Theme")
    config.set("Theme", "mode", mode)
    config.set("Theme", "color", color)
    with open(path, "w", encoding="utf-8") as f:
        config.write(f)


def save_watchlist(config_folder: str, tickers: list[str]):
    path = os.path.join(config_folder, "config.ini")
    config = configparser.ConfigParser()
    if os.path.exists(path):
        config.read(path)
    if not config.has_section("Watchlist"):
        config.add_section("Watchlist")
    config.set("Watchlist", "tickers", ",".join(tickers))
    with open(path, "w", encoding="utf-8") as f:
        config.write(f)


def save_brokers(config_folder: str, brokers: dict[int, str], reset: bool = False):
    path = os.path.join(config_folder, "config.ini")
    config = configparser.ConfigParser()
    if os.path.exists(path):
        config.read(path)
    if reset and config.has_section("Brokers"):
        config.remove_section("Brokers")
    if not config.has_section("Brokers"):
        config.add_section("Brokers")
    # Clear existing broker entries when resetting
    if reset:
        for key in list(config["Brokers"].keys()):
            config.remove_option("Brokers", key)
    for idx, name in brokers.items():
        config.set("Brokers", str(idx), name)
    with open(path, "w", encoding="utf-8") as f:
        config.write(f)


def save_home_hidden(config_folder: str, hidden: bool):
    path = os.path.join(config_folder, "config.ini")
    config = configparser.ConfigParser()
    if os.path.exists(path):
        config.read(path)
    if not config.has_section("Home"):
        config.add_section("Home")
    config.set("Home", "hidden", str(hidden).lower())
    with open(path, "w", encoding="utf-8") as f:
        config.write(f)


def reset_application(config_folder: str, user_folder: str):
    if os.path.exists(config_folder):
        shutil.rmtree(config_folder)
    if os.path.exists(user_folder):
        shutil.rmtree(user_folder)
