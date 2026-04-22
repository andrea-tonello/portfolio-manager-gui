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


def save_home_pnl_mode(config_folder: str, mode: int):
    path, config = _load_config(config_folder)
    _ensure_section(config, "Home")
    config.set("Home", "pnl_mode", str(mode))
    _save_config(path, config)


def save_split_ignores(config_folder: str, ignores: set[str]):
    """Persist a set of ignored split identifiers (strings like 'TICKER|YYYY-MM-DD' or 'TICKER|*')."""
    path, config = _load_config(config_folder)
    _ensure_section(config, "SplitIgnores")
    for key in list(config["SplitIgnores"].keys()):
        config.remove_option("SplitIgnores", key)
    if ignores:
        config.set("SplitIgnores", "entries", ",".join(sorted(ignores)))
    _save_config(path, config)


def load_split_ignores(config_folder: str) -> set[str]:
    _, config = _load_config(config_folder)
    raw = config.get("SplitIgnores", "entries", fallback="")
    if not raw:
        return set()
    return {s.strip() for s in raw.split(",") if s.strip()}


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


def save_tx_columns(config_folder: str, visible_cols: list[str]):
    path, config = _load_config(config_folder)
    _ensure_section(config, "Transactions")
    config.set("Transactions", "visible_columns", ",".join(visible_cols))
    _save_config(path, config)


def load_tx_columns(config_folder: str) -> list[str] | None:
    _, config = _load_config(config_folder)
    raw = config.get("Transactions", "visible_columns", fallback=None)
    if raw is None:
        return None
    return [c.strip() for c in raw.split(",") if c.strip()]


def reset_application(config_folder: str):
    if os.path.exists(config_folder):
        shutil.rmtree(config_folder)


# ── Multi-user management ────────────────────────────────────

def save_users(config_folder: str, users: dict[int, str]):
    path, config = _load_config(config_folder)
    _ensure_section(config, "Users")
    for key in list(config["Users"].keys()):
        config.remove_option("Users", key)
    for idx, name in users.items():
        config.set("Users", str(idx), name)
    _save_config(path, config)


def load_users(config_folder: str) -> dict[int, str]:
    _, config = _load_config(config_folder)
    if not config.has_section("Users"):
        return {}
    return {int(k): v for k, v in config.items("Users")}


def save_active_user(config_folder: str, user_idx: int):
    path, config = _load_config(config_folder)
    _ensure_section(config, "Active")
    config.set("Active", "user", str(user_idx))
    _save_config(path, config)


def load_active_user(config_folder: str) -> int | None:
    _, config = _load_config(config_folder)
    raw = config.get("Active", "user", fallback=None)
    return int(raw) if raw else None


def get_user_folder(config_folder: str, username: str) -> str:
    return os.path.join(config_folder, "users", username)


def get_user_res_folder(config_folder: str, username: str) -> str:
    return os.path.join(config_folder, "users", username, "resources")


def delete_user(config_folder: str, users: dict[int, str], user_idx: int):
    username = users[user_idx]
    user_folder = get_user_folder(config_folder, username)
    if os.path.exists(user_folder):
        shutil.rmtree(user_folder)
    del users[user_idx]
    save_users(config_folder, users)


def needs_user_migration(config_folder: str) -> bool:
    _, config = _load_config(config_folder)
    return config.has_section("Brokers") and not config.has_section("Users")


def migrate_to_multi_user(config_folder: str, username: str):
    path, config = _load_config(config_folder)

    user_folder = get_user_folder(config_folder, username)
    user_res = get_user_res_folder(config_folder, username)
    os.makedirs(user_res, exist_ok=True)

    # Move per-user sections into a separate config.ini
    user_config = configparser.ConfigParser()
    for section in ("Brokers", "Watchlist", "Transactions", "Home"):
        if config.has_section(section):
            user_config.add_section(section)
            for k, v in config.items(section):
                user_config.set(section, k, v)
            config.remove_section(section)

    user_config_path = os.path.join(user_folder, "config.ini")
    with open(user_config_path, "w", encoding="utf-8") as f:
        user_config.write(f)

    # Move resources/ contents into user subfolder
    old_res = os.path.join(config_folder, "resources")
    if os.path.exists(old_res):
        for fname in os.listdir(old_res):
            shutil.move(os.path.join(old_res, fname), os.path.join(user_res, fname))
        shutil.rmtree(old_res)

    # Add [Users] and [Active] to root config
    _ensure_section(config, "Users")
    config.set("Users", "1", username)
    _ensure_section(config, "Active")
    config.set("Active", "user", "1")
    _save_config(path, config)


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

    config = configparser.ConfigParser()
    try:
        config.read_string(zf.read("config.ini").decode("utf-8"))
    except Exception:
        return False, "config.ini is not a valid configuration file."

    # Multi-user backup: root config has [Users], per-user configs have [Brokers]
    if config.has_section("Users") and config.options("Users"):
        for key in config.options("Users"):
            username = config.get("Users", key)
            user_config_path = f"users/{username}/config.ini"
            if user_config_path not in names:
                return False, f"Missing config for user '{username}'."
            user_config = configparser.ConfigParser()
            try:
                user_config.read_string(zf.read(user_config_path).decode("utf-8"))
            except Exception:
                return False, f"Cannot parse config for user '{username}'."
            if not user_config.has_section("Brokers") or not user_config.options("Brokers"):
                return False, f"User '{username}' has no broker entries."
            for bkey in user_config.options("Brokers"):
                broker_name = user_config.get("Brokers", bkey)
                expected = f"users/{username}/resources/Report {broker_name}.csv"
                if expected not in names:
                    return False, f"Missing CSV for broker '{broker_name}' (user '{username}')."
            csv_names = [n for n in names
                         if n.startswith(f"users/{username}/resources/") and n.endswith(".csv")]
            for csv_name in csv_names:
                try:
                    header_line = zf.read(csv_name).decode("utf-8").split("\n", 1)[0]
                    columns = {c.strip() for c in header_line.split(",")}
                except Exception:
                    return False, f"Cannot read header of {csv_name}."
                missing = _CRITICAL_COLUMNS - columns
                if missing:
                    return False, f"{csv_name} is missing columns: {', '.join(sorted(missing))}"
    elif config.has_section("Brokers") and config.options("Brokers"):
        # Legacy single-user backup
        csv_names = [n for n in names if n.startswith("resources/") and n.endswith(".csv")]
        if not csv_names:
            return False, "No CSV files found in resources/."
        for key in config.options("Brokers"):
            broker_name = config.get("Brokers", key)
            expected = f"resources/Report {broker_name}.csv"
            if expected not in names:
                return False, f"Missing CSV for broker '{broker_name}': {expected}"
        for csv_name in csv_names:
            try:
                header_line = zf.read(csv_name).decode("utf-8").split("\n", 1)[0]
                columns = {c.strip() for c in header_line.split(",")}
            except Exception:
                return False, f"Cannot read header of {csv_name}."
            missing = _CRITICAL_COLUMNS - columns
            if missing:
                return False, f"{csv_name} is missing columns: {', '.join(sorted(missing))}"
    else:
        return False, "config.ini has no user or broker entries."

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
