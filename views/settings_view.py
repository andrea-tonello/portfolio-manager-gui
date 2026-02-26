import flet as ft

from components.snack import show_snack
from services import config_service, account_service
from utils.constants import LANG
from utils.other_utils import create_defaults


class SettingsView:
    def __init__(self, page: ft.Page, state):
        self.page = page
        self.state = state

    def build(self) -> ft.Control:
        t = self.state.translator
        return ft.Column([
            self._build_theming_section(),
            ft.Divider(),
            self._build_language_section(),
            ft.Divider(),
            self._build_accounts_section(),
            ft.Divider(),
            self._build_reset_section(),
        ], spacing=5, scroll=ft.ScrollMode.AUTO, expand=True)

    # ── Theming ──────────────────────────────────────────────────────

    _THEME_MODES = ["system", "light", "dark"]
    _PALETTE_KEYS = ["blue", "teal", "green", "yellow", "orange", "red", "purple", "indigo"]
    _PALETTE_COLORS = {
        "blue": ft.Colors.BLUE,
        "teal": ft.Colors.TEAL,
        "green": ft.Colors.GREEN,
        "yellow": ft.Colors.YELLOW,
        "orange": ft.Colors.ORANGE,
        "red": ft.Colors.RED,
        "purple": ft.Colors.PURPLE,
        "indigo": ft.Colors.INDIGO,
    }

    def _build_theming_section(self) -> ft.Control:
        t = self.state.translator

        theme_label = t.get(f"settings.theme.{self.state.theme_mode}")
        palette_label = t.get(f"settings.palette.{self.state.color_seed}")

        self._theme_btn = ft.FilledTonalButton(
            theme_label,
            width=140,
            on_click=self._open_theme_dialog,
        )
        self._palette_btn = ft.FilledTonalButton(
            palette_label,
            width=140,
            on_click=self._open_palette_dialog,
        )

        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Text(t.get("settings.theme.title"), size=16),
                    self._theme_btn,
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Row([
                    ft.Text(t.get("settings.palette.title"), size=16),
                    self._palette_btn,
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ], spacing=12),
            padding=20,
        )

    def _open_theme_dialog(self, e):
        t = self.state.translator
        rg = ft.RadioGroup(
            value=self.state.theme_mode,
            on_change=lambda ev: self._on_theme_selected(ev, rg),
            content=ft.Column([
                ft.Radio(value=m, label=t.get(f"settings.theme.{m}"))
                for m in self._THEME_MODES
            ], spacing=4, tight=True),
        )
        dlg = ft.AlertDialog(
            title=ft.Text(t.get("settings.theme.title")),
            content=rg,
        )
        self.page.show_dialog(dlg)

    def _on_theme_selected(self, e, rg):
        new_mode = rg.value
        self.state.theme_mode = new_mode
        config_service.save_theme(self.state.config_folder, new_mode, self.state.color_seed)
        self.page.pop_dialog()
        self._apply_theme()

    def _open_palette_dialog(self, e):
        t = self.state.translator
        rg = ft.RadioGroup(
            value=self.state.color_seed,
            on_change=lambda ev: self._on_palette_selected(ev, rg),
            content=ft.Column([
                ft.Radio(value=k, label=t.get(f"settings.palette.{k}"))
                for k in self._PALETTE_KEYS
            ], spacing=4, tight=True),
        )
        dlg = ft.AlertDialog(
            title=ft.Text(t.get("settings.palette.title")),
            content=rg,
        )
        self.page.show_dialog(dlg)

    def _on_palette_selected(self, e, rg):
        new_color = rg.value
        self.state.color_seed = new_color
        config_service.save_theme(self.state.config_folder, self.state.theme_mode, new_color)
        self.page.pop_dialog()
        self._apply_theme()

    def _apply_theme(self):
        s = self.state
        t = s.translator
        mode_map = {"system": ft.ThemeMode.SYSTEM, "light": ft.ThemeMode.LIGHT, "dark": ft.ThemeMode.DARK}
        self.page.theme_mode = mode_map.get(s.theme_mode, ft.ThemeMode.SYSTEM)
        color = self._PALETTE_COLORS.get(s.color_seed, ft.Colors.BLUE)
        self.page.theme = ft.Theme(color_scheme_seed=color)
        self.page.dark_theme = ft.Theme(color_scheme_seed=color)

        self._theme_btn.content = ft.Text(t.get(f"settings.theme.{s.theme_mode}"))
        self._palette_btn.content = ft.Text(t.get(f"settings.palette.{s.color_seed}"))
        self.page.update()

    # ── Language ──────────────────────────────────────────────────────

    def _build_language_section(self) -> ft.Control:
        t = self.state.translator
        options = [
            ft.dropdown.Option(key=code, text=name)
            for _, (code, name) in sorted(LANG.items())
        ]
        current = self.state.lang_code or LANG[1][0]
        return ft.Container(
            content=ft.Column([
                ft.Text(t.get("settings.language.title"), size=16, weight=ft.FontWeight.BOLD),
                ft.Dropdown(
                    value=current,
                    options=options,
                    on_select=self._on_language_change,
                    expand=True,
                    border_radius=ft.border_radius.all(15),
                    border_color=ft.Colors.with_opacity(0.40, ft.Colors.GREY),
                ),
            ], spacing=10),
            padding=20,
        )

    def _on_language_change(self, e):
        lang_code = e.control.value
        s = self.state
        config_service.save_language(s.config_folder, lang_code)
        s.lang_code = lang_code
        s.translator.load_language(lang_code)
        show_snack(self.page, s.translator.get("settings.language.changed"))
        from views import _show_settings
        _show_settings(self.page, s)

    # ── Accounts ──────────────────────────────────────────────────────

    def _build_accounts_section(self) -> ft.Control:
        t = self.state.translator
        broker_tiles = []
        for idx in sorted(self.state.brokers.keys()):
            broker_tiles.append(
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.ACCOUNT_BALANCE),
                    title=ft.Text(self.state.brokers[idx]),
                    subtitle=ft.Text(f"ID: {idx}"),
                    trailing=ft.IconButton(
                        icon=ft.Icons.DELETE,
                        icon_color=ft.Colors.RED,
                        tooltip=t.get("settings.account.delete_account"),
                        on_click=lambda e, i=idx: self._on_delete_account(i),
                    ),
                )
            )

        self.new_broker_field = ft.TextField(
            label=t.get("settings.account.add_account"),
            border_radius=ft.border_radius.all(15),
            border_color=ft.Colors.with_opacity(0.40, ft.Colors.GREY),
            expand=True,
        )

        return ft.Container(
            content=ft.Column([
                ft.Text(t.get("settings.account.title").strip(), size=16, weight=ft.FontWeight.BOLD),
                *broker_tiles,
                ft.Row([
                    self.new_broker_field,
                    ft.ElevatedButton(
                        t.get("components.confirm"),
                        icon=ft.Icons.ADD,
                        on_click=self._on_add_broker,
                    ),
                ]),
            ], spacing=10),
            padding=20,
        )

    def _on_add_broker(self, e):
        name = self.new_broker_field.value.strip()
        if not name:
            return
        s = self.state
        next_idx = max(s.brokers.keys(), default=0) + 1
        s.brokers[next_idx] = name
        config_service.save_brokers(s.config_folder, s.brokers, reset=False)
        create_defaults(s.config_res_folder, name)
        s.load_all_accounts()
        show_snack(self.page, s.translator.get("settings.account.accounts_added"))
        from views import _show_settings
        _show_settings(self.page, s)

    def _on_delete_account(self, idx: int):
        s = self.state
        t = s.translator
        if len(s.brokers) <= 1:
            show_snack(self.page, t.get("settings.account.delete_last"), error=True)
            return

        broker_name = s.brokers[idx]
        dlg = ft.AlertDialog(
            title=ft.Text(t.get("settings.account.delete_account")),
            content=ft.Text(t.get("settings.account.delete_confirm", account=broker_name)),
            actions=[
                ft.TextButton(t.get("components.cancel"), on_click=lambda e: self.page.pop_dialog()),
                ft.TextButton(
                    t.get("settings.account.delete_account"),
                    style=ft.ButtonStyle(color=ft.Colors.RED),
                    on_click=lambda e, i=idx, name=broker_name: self._confirm_delete(i, name),
                ),
            ],
        )
        self.page.show_dialog(dlg)

    def _confirm_delete(self, idx: int, broker_name: str):
        s = self.state
        t = s.translator
        self.page.pop_dialog()
        try:
            account_service.delete_account_files(broker_name, s.config_res_folder, s.user_folder)
            del s.brokers[idx]
            config_service.save_brokers(s.config_folder, s.brokers, reset=True)
            s.accounts.pop(idx, None)
            s.load_all_accounts()
            # Reset per-page selections if they pointed to this account
            if s.ops_acc_idx == idx:
                s.ops_acc_idx = None
            if s.analysis_acc_idx == idx:
                s.analysis_acc_idx = None
            if s.home_selection == str(idx):
                s.home_selection = "overview"
            if s.tx_selection == str(idx):
                s.tx_selection = "overview"
            show_snack(self.page, t.get("settings.account.account_deleted"))
            from views import _show_settings
            _show_settings(self.page, s)
        except Exception as ex:
            show_snack(self.page, str(ex), error=True)

    # ── Reset ─────────────────────────────────────────────────────────

    def _build_reset_section(self) -> ft.Control:
        t = self.state.translator
        return ft.Container(
            content=ft.Column([
                ft.Text("Danger Zone", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.RED),
                ft.Text(t.get("settings.account.reset_warning"), size=12),
                ft.OutlinedButton(
                    "Reset",
                    icon=ft.Icons.DELETE_FOREVER,
                    style=ft.ButtonStyle(color=ft.Colors.RED),
                    on_click=self._on_reset_click,
                ),
            ], spacing=10),
            padding=20,
        )

    def _on_reset_click(self, e):
        t = self.state.translator
        self.reset_field = ft.TextField(
            label=t.get("settings.account.reset_confirm"),
            border_radius=ft.border_radius.all(15),
            border_color=ft.Colors.with_opacity(0.40, ft.Colors.GREY),
            expand=True,
        )
        dlg = ft.AlertDialog(
            title=ft.Text(t.get("settings.account.reset_warning").strip()),
            content=self.reset_field,
            actions=[
                ft.TextButton(t.get("components.cancel"), on_click=lambda e: self.page.pop_dialog()),
                ft.TextButton("RESET", on_click=lambda e: self._confirm_reset()),
            ],
        )
        self.page.show_dialog(dlg)

    def _confirm_reset(self):
        if self.reset_field.value.strip() == "RESET":
            s = self.state
            self.page.pop_dialog()
            try:
                config_service.reset_application(s.config_folder, s.user_folder)
                show_snack(self.page, s.translator.get("settings.account.reset_completed"))
                import os
                os.makedirs(s.user_folder, exist_ok=True)
                os.makedirs(s.config_res_folder, exist_ok=True)
                s.brokers = {}
                s.accounts = {}
                s.all_accounts = []
                s.ops_acc_idx = None
                s.analysis_acc_idx = None
                s.home_selection = "overview"
                s.tx_selection = "overview"
                from views import _show_settings
                _show_settings(self.page, s)
            except OSError as ex:
                show_snack(self.page, s.translator.get("settings.account.deletion_error", e=str(ex)), error=True)
