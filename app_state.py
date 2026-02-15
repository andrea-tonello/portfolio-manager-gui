import os
import configparser
import pandas as pd

from utils.translator import Translator
from utils.constants import LANG, REPORT_PREFIX
from utils.other_utils import create_defaults


class AppState:
    """Central application state replacing CLI module-level globals."""

    def __init__(self, base_path: str):
        self.base_path = base_path
        self.user_folder = os.path.join(base_path, "reports")
        self.config_folder = os.path.join(base_path, "config")
        self.config_res_folder = os.path.join(self.config_folder, "resources")
        os.makedirs(self.user_folder, exist_ok=True)
        os.makedirs(self.config_res_folder, exist_ok=True)

        self.config_path = os.path.join(self.config_folder, "config.ini")
        self.config = configparser.ConfigParser()

        locales_dir = os.path.join(base_path, "locales")
        self.translator = Translator(language_code=LANG[1][0], locales_dir=locales_dir)
        self.lang_code: str | None = None

        self.brokers: dict[int, str] = {}

        # Theming
        self.theme_mode: str = "system"   # "system", "light", "dark"
        self.color_seed: str = "blue"     # palette key

        # Per-account storage: {broker_idx: {"df", "file", "path", "len_df_init", "edited_flag"}}
        self.accounts: dict[int, dict] = {}

        # All accounts list (for format_accounts backward compat)
        self.all_accounts: list[dict] = []

        # Per-page selection
        self.home_selection: str = "overview"  # "overview" or str(broker_idx)
        self.ops_acc_idx: int | None = None
        self.analysis_acc_idx: int | None = None  # None = all accounts
        self.tx_selection: str = "overview"  # "overview" or str(broker_idx)

        # Watchlist
        self.watchlist: list[str] = []

        # Navigation state
        self._last_nav_index: int = 0

        # Backward compat (kept for existing view code during transition)
        self.acc_idx: int | None = None
        self.df: pd.DataFrame | None = None
        self.file: str | None = None
        self.path: str | None = None
        self.len_df_init: int = 0
        self.edited_flag: bool = False

    @property
    def is_edited(self) -> bool:
        if self.df is not None:
            return len(self.df) != self.len_df_init or self.edited_flag
        return False

    def load_config(self):
        """Read config.ini and populate lang_code and brokers."""
        if os.path.exists(self.config_path):
            self.config.read(self.config_path)
            if "Language" in self.config and "Code" in self.config["Language"]:
                self.lang_code = self.config["Language"]["Code"]
            if "Theme" in self.config:
                self.theme_mode = self.config.get("Theme", "mode", fallback="system")
                self.color_seed = self.config.get("Theme", "color", fallback="blue")
            if "Watchlist" in self.config:
                tickers_str = self.config.get("Watchlist", "tickers", fallback="")
                self.watchlist = [t.strip() for t in tickers_str.split(",") if t.strip()]
            if "Brokers" in self.config:
                try:
                    self.brokers = {int(k): v for k, v in self.config.items("Brokers")}
                except ValueError:
                    pass
        if self.lang_code:
            self.translator.load_language(self.lang_code)

    def ensure_defaults(self):
        """Create default CSV files for each broker if missing."""
        for broker_name in self.brokers.values():
            create_defaults(self.config_res_folder, broker_name)

    def load_all_accounts(self):
        """Load all broker accounts into self.accounts and self.all_accounts."""
        from services import account_service
        self.accounts = {}
        self.all_accounts = []
        for idx in sorted(self.brokers.keys()):
            try:
                acc = account_service.load_single_account(self.brokers, self.config_res_folder, idx)
                self.accounts[idx] = acc
                self.all_accounts.append(acc)
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

    # Backward compat
    def set_active_account(self, acc_idx: int, df: pd.DataFrame, file: str, path: str):
        self.acc_idx = acc_idx
        self.df = df
        self.file = file
        self.path = path
        self.len_df_init = len(df)
        self.edited_flag = False

    def mark_saved(self):
        if self.df is not None:
            self.len_df_init = len(self.df)
        self.edited_flag = False
