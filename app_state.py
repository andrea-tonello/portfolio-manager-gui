import os
import configparser

import flet as ft
import pandas as pd

from domain.account import Account
from domain.errors import ValidationError
from services import account_service, config_service
from utils.translator import Translator
from utils.constants import DEFAULT_LANG, I18N_DIR


class AppState:
    """Central application state replacing CLI module-level globals."""

    def __init__(self, base_path: str):
        self.base_path = base_path
        self.config_folder = os.path.join(base_path, "config")
        os.makedirs(self.config_folder, exist_ok=True)

        self.config_path = os.path.join(self.config_folder, "config.ini")

        self.translator = Translator(language_code=DEFAULT_LANG, locales_dir=I18N_DIR)
        self.lang_code: str | None = None

        # Multi-user
        self.users: dict[int, str] = {}
        self.active_user_idx: int | None = None
        self.active_user_name: str | None = None
        self.user_config_folder: str | None = None   # per-user config dir
        self.config_res_folder: str | None = None     # per-user resources dir

        self.brokers: dict[int, str] = {}

        # Theming
        self.theme_mode: str = "system"   # "system", "light", "dark"
        self.color_seed: str = "blue"     # palette key

        # The loaded accounts, by broker index
        self.accounts: dict[int, Account] = {}

        # Per-page selection
        self.home_selection: str = "overview"  # "overview" or str(broker_idx)
        self.ops_acc_idx: int | None = None
        self.analysis_acc_idx: int | None = None  # None = all accounts
        self.analysis_tab_index: int = 0  # last selected Analysis tab (0 = first tab)
        self.tx_selection: str = "overview"  # "overview" or str(broker_idx)

        # Watchlist
        self.watchlist: list[str] = []

        # Home view
        self.home_values_hidden: bool = False
        self.home_pnl_mode: int = 0
        # Home's last computed values; None makes Home fetch fresh ones. Cleared
        # whenever an account changes (commit, add_broker, remove_broker).
        self.home_cache: dict | None = None
        self.home_nav_count: int = 0  # tab switches since Home last fetched live values

        # Split auto-detection: set of "TICKER|YYYY-MM-DD" or "TICKER|*" entries to suppress prompts
        self.split_ignores: set[str] = set()
        self.split_checked_session: bool = False

        # Haptic feedback
        self._haptic: ft.HapticFeedback | None = None

        # Navigation state
        self.last_nav_index: int = 0

    def init_haptic(self, page: ft.Page):
        """Register the HapticFeedback service once, reuse on rebuilds."""
        existing = [s for s in page.services if isinstance(s, ft.HapticFeedback)]
        if existing:
            self._haptic = existing[0]
        else:
            self._haptic = ft.HapticFeedback()
            page.services.append(self._haptic)

    def haptic(self, page: ft.Page):
        """Fire a heavy-impact haptic. Safe to call from any view."""
        if self._haptic:
            async def _safe_haptic():
                try:
                    await self._haptic.heavy_impact()
                except RuntimeError:
                    pass
            page.run_task(_safe_haptic)

    def load_config(self):
        """Read root config.ini for global settings, then load active user's per-user config."""
        config = configparser.ConfigParser()
        if os.path.exists(self.config_path):
            config.read(self.config_path)
            if "Language" in config and "Code" in config["Language"]:
                self.lang_code = config["Language"]["Code"]
            if "Theme" in config:
                self.theme_mode = config.get("Theme", "mode", fallback="system")
                self.color_seed = config.get("Theme", "color", fallback="blue")

        if self.lang_code:
            self.translator.load_language(self.lang_code)

        # Load users from root config
        self.users = config_service.load_users(self.config_folder)
        self.active_user_idx = config_service.load_active_user(self.config_folder)

        if self.active_user_idx and self.active_user_idx in self.users:
            self.active_user_name = self.users[self.active_user_idx]
            self.user_config_folder = config_service.get_user_folder(
                self.config_folder, self.active_user_name
            )
            self.config_res_folder = config_service.get_user_res_folder(
                self.config_folder, self.active_user_name
            )
            os.makedirs(self.config_res_folder, exist_ok=True)
            settings = config_service.load_user_settings(self.user_config_folder)
        else:
            self.active_user_name = None
            self.user_config_folder = None
            self.config_res_folder = None
            settings = config_service.UserSettings()

        self.brokers = settings.brokers
        self.watchlist = settings.watchlist
        self.home_values_hidden = settings.values_hidden
        self.home_pnl_mode = settings.pnl_mode
        self.split_ignores = settings.split_ignores

    # ── Changes to accounts, brokers and users ───────────────────────

    def commit(self, acc_idx: int, df: pd.DataFrame) -> None:
        """Make `df` the ledger of account `acc_idx`, after recording an operation, and save it.

        Also clears Home's cached values, which were computed from the old ledger.
        """
        account = self.accounts[acc_idx]
        account.df = df
        account_service.save_account(account)
        self.home_cache = None

    def add_broker(self, name: str) -> int:
        """Add an account called `name` (spaces trimmed), save it with an empty CSV, and return its number.

        Raises ValidationError("settings.account.duplicate") if the name is
        already used, ignoring capitals: "Fineco" and "fineco" would share one
        CSV on Windows and macOS. A blank name raises ValueError; screens
        check for it first.
        """
        name = name.strip()
        if not name:
            raise ValueError("account name is empty")
        if name.casefold() in {existing.casefold() for existing in self.brokers.values()}:
            raise ValidationError("settings.account.duplicate", account=name)
        idx = max(self.brokers, default=0) + 1
        self.brokers[idx] = name
        config_service.save_brokers(self.user_config_folder, self.brokers, reset=True)
        account_service.create_defaults(self.config_res_folder, name)
        self.load_all_accounts()
        self.home_cache = None
        return idx

    def remove_broker(self, idx: int) -> None:
        """Delete account `idx`: its CSV, its config.ini entry and the loaded account.

        Screens that were showing it go back to their default (all accounts,
        or none selected in Operations).
        """
        account_service.delete_account_files(self.brokers[idx], self.config_res_folder)
        del self.brokers[idx]
        config_service.save_brokers(self.user_config_folder, self.brokers, reset=True)
        self.load_all_accounts()
        self.home_cache = None
        if self.ops_acc_idx == idx:
            self.ops_acc_idx = None
        if self.analysis_acc_idx == idx:
            self.analysis_acc_idx = None
        if self.home_selection == str(idx):
            self.home_selection = "overview"
        if self.tx_selection == str(idx):
            self.tx_selection = "overview"

    def add_user(self, name: str) -> int:
        """Add a user called `name` (spaces trimmed), make them the active user, and return their number.

        Creates the user's folders and loads their (still empty) settings.
        Raises ValidationError("settings.user_mgmt.duplicate") if the name is
        already used, ignoring capitals, since each user has a folder named
        after them. A blank name raises ValueError; screens check for it first.
        """
        name = name.strip()
        if not name:
            raise ValueError("user name is empty")
        if name.casefold() in {existing.casefold() for existing in self.users.values()}:
            raise ValidationError("settings.user_mgmt.duplicate")
        idx = max(self.users, default=0) + 1
        self.users[idx] = name
        config_service.save_users(self.config_folder, self.users)
        os.makedirs(config_service.get_user_res_folder(self.config_folder, name), exist_ok=True)
        self.switch_user(idx)
        return idx

    def switch_user(self, idx: int) -> None:
        """Make user `idx` the active user: save the choice and load their settings and accounts.

        Clears Home's cached values, which belonged to the previous user. The
        user manager restarts the app afterwards, which rebuilds every screen.
        """
        config_service.save_active_user(self.config_folder, idx)
        self.load_config()
        self.load_all_accounts()
        self.home_cache = None

    def remove_user(self, idx: int) -> None:
        """Delete user `idx`: their folder (settings and account CSVs) and their entry in config.ini.

        Raises ValueError for the active user, whose data is in use: switch to
        another user first.
        """
        if idx == self.active_user_idx:
            raise ValueError("cannot remove the active user; switch to another user first")
        config_service.delete_user_files(self.config_folder, self.users[idx])
        del self.users[idx]
        config_service.save_users(self.config_folder, self.users)

    def ensure_defaults(self):
        """Create default CSV files for each broker if missing."""
        for broker_name in self.brokers.values():
            account_service.create_defaults(self.config_res_folder, broker_name)

    def load_all_accounts(self):
        """Load all broker accounts into self.accounts."""
        self.accounts = {}
        for idx in sorted(self.brokers.keys()):
            try:
                self.accounts[idx] = account_service.load_single_account(self.brokers, self.config_res_folder, idx)
            except FileNotFoundError:
                pass

    def get_account(self, idx: int) -> Account | None:
        return self.accounts.get(idx)
