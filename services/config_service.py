import configparser
import io
import os
import shutil
import zipfile


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


def save_tx_filter(config_folder: str, mode: str, value: int):
    path, config = _load_config(config_folder)
    _ensure_section(config, "Transactions")
    config.set("Transactions", "filter_mode", mode)
    config.set("Transactions", "filter_value", str(value))
    _save_config(path, config)


def load_tx_filter(config_folder: str) -> tuple[str, int]:
    _, config = _load_config(config_folder)
    if not config.has_section("Transactions"):
        return "count", 5
    mode = config.get("Transactions", "filter_mode", fallback="count")
    if mode not in ("count", "days"):
        mode = "count"
    try:
        value = int(config.get("Transactions", "filter_value", fallback="5"))
        if value <= 0:
            raise ValueError
    except (ValueError, TypeError):
        value = 5 if mode == "count" else 90
    return mode, value


def reset_application(config_folder: str):
    if os.path.exists(config_folder):
        shutil.rmtree(config_folder)


# ── Backup export / import ─────────────────────────────────────

_CRITICAL_COLUMNS = {"date", "account", "operation", "product"}


def export_backup(config_folder: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, _, filenames in os.walk(config_folder):
            for fname in filenames:
                full = os.path.join(dirpath, fname)
                arcname = os.path.relpath(full, config_folder)
                zf.write(full, arcname)
    return buf.getvalue()


def validate_backup(zip_bytes: bytes, t) -> tuple[bool, str]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except Exception:
        return False, t.get("settings.account.import_error")

    names = zf.namelist()

    # config.ini must exist
    if "config.ini" not in names:
        return False, "Missing config.ini in backup."

    # config.ini must be parseable with a Brokers section
    config = configparser.ConfigParser()
    try:
        config.read_string(zf.read("config.ini").decode("utf-8"))
    except Exception:
        return False, "config.ini is not a valid configuration file."

    if not config.has_section("Brokers") or not config.options("Brokers"):
        return False, "config.ini has no broker entries."

    # resources/ must have CSV files
    csv_names = [n for n in names if n.startswith("resources/") and n.endswith(".csv")]
    if not csv_names:
        return False, "No CSV files found in resources/."

    # every broker must have a matching CSV
    for key in config.options("Brokers"):
        broker_name = config.get("Brokers", key)
        expected = f"resources/Report {broker_name}.csv"
        if expected not in names:
            return False, f"Missing CSV for broker '{broker_name}': {expected}"

    # each CSV must contain critical columns
    for csv_name in csv_names:
        try:
            header_line = zf.read(csv_name).decode("utf-8").split("\n", 1)[0]
            columns = {c.strip() for c in header_line.split(",")}
        except Exception:
            return False, f"Cannot read header of {csv_name}."
        missing = _CRITICAL_COLUMNS - columns
        if missing:
            return False, f"{csv_name} is missing columns: {', '.join(sorted(missing))}"

    zf.close()
    return True, ""


def import_backup(config_folder: str, zip_bytes: bytes):
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))

    # path traversal check
    target = os.path.realpath(config_folder)
    for member in zf.namelist():
        resolved = os.path.realpath(os.path.join(config_folder, member))
        if not resolved.startswith(target + os.sep) and resolved != target:
            raise ValueError(f"Unsafe path in archive: {member}")

    if os.path.exists(config_folder):
        shutil.rmtree(config_folder)
    os.makedirs(config_folder, exist_ok=True)
    zf.extractall(config_folder)
    zf.close()
