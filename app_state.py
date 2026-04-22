import os
import configparser

import flet as ft

from services import config_service
from utils.translator import Translator
from utils.constants import LANG
from utils.other_utils import create_defaults


class AppState:
    """Central application state replacing CLI module-level globals."""

    def __init__(self, base_path: str):
        self.base_path = base_path
        self.config_folder = os.path.join(base_path, "config")
        os.makedirs(self.config_folder, exist_ok=True)

        self.config_path = os.path.join(self.config_folder, "config.ini")
        self.config = configparser.ConfigParser()

        locales_dir = os.path.join(os.path.dirname(__file__), "locales")
        self.translator = Translator(language_code=LANG[1][0], locales_dir=locales_dir)
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

        # Per-account storage: {broker_idx: {"df", "file", "path", "len_df_init", "edited_flag"}}
        self.accounts: dict[int, dict] = {}

        # Per-page selection
        self.home_selection: str = "overview"  # "overview" or str(broker_idx)
        self.ops_acc_idx: int | None = None
        self.analysis_acc_idx: int | None = None  # None = all accounts
        self.tx_selection: str = "overview"  # "overview" or str(broker_idx)

        # Watchlist
        self.watchlist: list[str] = []

        # Home view
        self._home_values_hidden: bool = False
        self._home_pnl_mode: int = 0
        self._home_cache: dict | None = None
        self._home_nav_count: int = 0
        self._home_nav_threshold: int = 10

        # Split auto-detection: set of "TICKER|YYYY-MM-DD" or "TICKER|*" entries to suppress prompts
        self._split_ignores: set[str] = set()
        self._split_checked_session: bool = False

        # Haptic feedback
        self._haptic: ft.HapticFeedback | None = None

        # Navigation state
        self._last_nav_index: int = 0

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
        self.config = configparser.ConfigParser()
        if os.path.exists(self.config_path):
            self.config.read(self.config_path)
            if "Language" in self.config and "Code" in self.config["Language"]:
                self.lang_code = self.config["Language"]["Code"]
            if "Theme" in self.config:
                self.theme_mode = self.config.get("Theme", "mode", fallback="system")
                self.color_seed = self.config.get("Theme", "color", fallback="blue")

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

            # Load per-user settings
            user_config = configparser.ConfigParser()
            user_config_path = os.path.join(self.user_config_folder, "config.ini")
            if os.path.exists(user_config_path):
                user_config.read(user_config_path)
            if user_config.has_section("Brokers"):
                try:
                    self.brokers = {int(k): v for k, v in user_config.items("Brokers")}
                except ValueError:
                    self.brokers = {}
            else:
                self.brokers = {}
            if user_config.has_section("Watchlist"):
                tickers_str = user_config.get("Watchlist", "tickers", fallback="")
                self.watchlist = [t.strip() for t in tickers_str.split(",") if t.strip()]
            else:
                self.watchlist = []
            if user_config.has_section("Home"):
                self._home_values_hidden = user_config.get("Home", "hidden", fallback="false") == "true"
                try:
                    mode = int(user_config.get("Home", "pnl_mode", fallback="0"))
                    self._home_pnl_mode = mode if mode in (0, 1, 2) else 0
                except ValueError:
                    self._home_pnl_mode = 0
            else:
                self._home_values_hidden = False
                self._home_pnl_mode = 0
            if user_config.has_section("SplitIgnores"):
                raw = user_config.get("SplitIgnores", "entries", fallback="")
                self._split_ignores = {s.strip() for s in raw.split(",") if s.strip()}
            else:
                self._split_ignores = set()
        else:
            self.active_user_name = None
            self.user_config_folder = None
            self.config_res_folder = None
            self.brokers = {}
            self.watchlist = []
            self._home_values_hidden = False
            self._home_pnl_mode = 0
            self._split_ignores = set()

    def ensure_defaults(self):
        """Create default CSV files for each broker if missing."""
        for broker_name in self.brokers.values():
            create_defaults(self.config_res_folder, broker_name)

    def load_all_accounts(self):
        """Load all broker accounts into self.accounts."""
        from services import account_service
        self.accounts = {}
        for idx in sorted(self.brokers.keys()):
            try:
                acc = account_service.load_single_account(self.brokers, self.config_res_folder, idx)
                self.accounts[idx] = acc
            except FileNotFoundError:
                pass

    def get_account(self, idx: int) -> dict | None:
        return self.accounts.get(idx)

    def is_account_edited(self, idx: int) -> bool:
        acc = self.accounts.get(idx)
        if acc is None:
            return False
        df = acc["df"]
        return len(df) != acc["len_df_init"] or acc.get("edited_flag", False)

    def mark_account_saved(self, idx: int):
        acc = self.accounts.get(idx)
        if acc:
            acc["len_df_init"] = len(acc["df"])
            acc["edited_flag"] = False
