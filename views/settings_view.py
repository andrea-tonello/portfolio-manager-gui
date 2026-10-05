import flet as ft

from components.action_card import action_card
from components.dialogs import build_github_repo, show_contacts, show_privacy_policy
from components.file_export import get_file_picker, save_bytes
from components.inputs import rounded_dropdown, rounded_text_field
from components.snack import error_message, show_snack
from components.theme import PALETTE_COLORS, THEME_MODES, apply_theme
from domain.errors import ValidationError
from services import config_service
from utils.constants import APP_VERSION, DEFAULT_LANG, LANGUAGES

PAGE_WIDTH = 720


class SettingsView:
    def __init__(self, app):
        """Build the Settings page for the controller's page and current state."""
        self.app = app
        self.page = app.page
        self.state = app.state

    def build(self) -> ft.Control:
        self.file_picker = get_file_picker(self.page)  # for backup export and import


        return ft.Row([
            ft.Column([
                self._build_theming_section(),
                ft.Container(ft.Divider(), width=850),
                self._build_language_section(),
                ft.Container(ft.Divider(), width=850),
                self._build_accounts_section(),
                ft.Container(ft.Divider(), width=850),
                self._build_backup_section(),
                ft.Container(ft.Divider(), width=850),
                self._build_reset_section(),
                ft.Container(ft.Divider(), width=850),
                self._build_info_section(),
                ft.Container(height=120)
            ], 
            spacing=5, scroll=ft.ScrollMode.AUTO, expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER)
        ], 
        alignment=ft.MainAxisAlignment.CENTER, 
        expand=True,
        )
    

    # ── Theming ──────────────────────────────────────────────────────

    def _build_theming_section(self) -> ft.Control:
        t = self.state.translator

        theme_label = t.get(f"settings.theme.{self.state.theme_mode}")
        palette_label = t.get(f"settings.palette.{self.state.color_seed}")

        self._theme_btn = ft.FilledTonalButton(
            theme_label,
            width=140,
            on_click=self._open_theme_dialog,
            elevation=2,
        )
        self._palette_btn = ft.FilledTonalButton(
            palette_label,
            width=140,
            on_click=self._open_palette_dialog,
            elevation=2,
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
            width=PAGE_WIDTH,
        )

    def _open_theme_dialog(self, e):
        """Let the user pick light, dark or the device's mode."""
        t = self.state.translator
        self._open_choice_dialog(
            "settings.theme.title", {mode: t.get(f"settings.theme.{mode}") for mode in THEME_MODES},
            self.state.theme_mode, lambda mode: self._change_theme(mode, self.state.color_seed),
        )

    def _open_palette_dialog(self, e):
        """Let the user pick the colour palette."""
        t = self.state.translator
        self._open_choice_dialog(
            "settings.palette.title", {key: t.get(f"settings.palette.{key}") for key in PALETTE_COLORS},
            self.state.color_seed, lambda palette: self._change_theme(self.state.theme_mode, palette),
        )

    def _open_choice_dialog(self, title_key, options, current, on_pick):
        """Show `options` ({key: label}) as radio buttons, `current` selected; a pick closes it and calls on_pick(key)."""
        def picked(e):
            """Close the dialog and hand over the key picked."""
            self.page.pop_dialog()
            on_pick(choices.value)

        choices = ft.RadioGroup(
            value=current,
            on_change=picked,
            content=ft.Column([
                ft.Radio(value=key, label=label) for key, label in options.items()
            ], spacing=0, tight=True),
        )
        self.page.show_dialog(ft.AlertDialog(
            title=ft.Text(self.state.translator.get(title_key)),
            content=choices,
        ))

    def _change_theme(self, mode, palette):
        """Save the light/dark mode and palette, apply them to the page, and show them on the two buttons."""
        s = self.state
        t = s.translator
        s.theme_mode, s.color_seed = mode, palette
        config_service.save_theme(s.config_folder, mode, palette)
        apply_theme(self.page, mode, palette)

        self._theme_btn.content = ft.Text(t.get(f"settings.theme.{mode}"))
        self._palette_btn.content = ft.Text(t.get(f"settings.palette.{palette}"))
        self.page.update()

    # ── Language ──────────────────────────────────────────────────────

    def _build_language_section(self) -> ft.Control:
        t = self.state.translator
        options = [ft.dropdown.Option(key=code, text=name) for code, name in LANGUAGES.items()]
        current = self.state.lang_code or DEFAULT_LANG
        return ft.Container(
            content=ft.Column([
                ft.Text(t.get("settings.language.title"), size=16, weight=ft.FontWeight.BOLD),
                rounded_dropdown(
                    value=current,
                    options=options,
                    on_select=self._on_language_change,
                    expand=True,
                ),
            ], spacing=10),
            padding=20,
            width=PAGE_WIDTH,
        )

    def _on_language_change(self, e):
        lang_code = e.control.value
        s = self.state
        config_service.save_language(s.config_folder, lang_code)
        s.lang_code = lang_code
        s.translator.load_language(lang_code)
        show_snack(self.page, s.translator.get("settings.language.changed"))
        self.app.show_settings()

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

        self.new_broker_field = rounded_text_field(
            label=t.get("settings.account.add_account"),
            expand=True,
        )

        return ft.Container(
            content=ft.Column([
                ft.Text(t.get("settings.account.title"), size=16, weight=ft.FontWeight.BOLD),
                *broker_tiles,
                ft.Row([
                    self.new_broker_field,
                    ft.Button(
                        t.get("components.confirm"),
                        icon=ft.Icons.ADD,
                        on_click=self._on_add_broker,
                        elevation=2,
                    ),
                ]),
            ], spacing=10),
            padding=20,
            width=PAGE_WIDTH,
        )

    def _on_add_broker(self, e):
        name = self.new_broker_field.value.strip()
        if not name:
            return
        s = self.state
        try:
            s.add_broker(name)
        except ValidationError as ex:
            show_snack(self.page, error_message(s.translator, ex), error=True)
            return
        show_snack(self.page, s.translator.get("settings.account.accounts_added"))
        self.app.show_settings()

    def _on_delete_account(self, idx: int):
        s = self.state
        t = s.translator
        if len(s.brokers) <= 1:
            show_snack(self.page, t.get("settings.account.delete_last"), error=True)
            return

        broker_name = s.brokers[idx]
        dlg = ft.AlertDialog(
            title=ft.Text(t.get("settings.account.delete_account")),
            content=ft.Text(t.get("settings.account.delete_confirm", account=broker_name) + 
                            t.get("settings.account.suggest_backup")),
            actions=[
                ft.TextButton(t.get("components.cancel"), on_click=lambda e: self.page.pop_dialog()),
                ft.TextButton(
                    t.get("settings.account.delete_account"),
                    style=ft.ButtonStyle(color=ft.Colors.RED),
                    on_click=lambda e, i=idx: self._confirm_delete(i),
                ),
            ],
        )
        self.page.show_dialog(dlg)

    def _confirm_delete(self, idx: int):
        s = self.state
        t = s.translator
        self.page.pop_dialog()
        try:
            s.remove_broker(idx)
            show_snack(self.page, t.get("settings.account.account_deleted"))
            self.app.show_settings()
        except Exception as ex:
            show_snack(self.page, str(ex), error=True)

    # ── Backup ────────────────────────────────────────────────────────

    def _build_backup_section(self) -> ft.Control:
        t = self.state.translator
        export_btn = action_card(ft.Icons.UPLOAD_FILE, t.get("settings.account.export_backup"),
                                 self._on_export_backup, expand=True)
        import_btn = action_card(ft.Icons.DOWNLOAD, t.get("settings.account.import_backup"),
                                 self._on_import_backup, expand=True)
        return ft.Container(
            content=ft.Column([
                ft.Text(t.get("settings.account.backup_title"), size=16, weight=ft.FontWeight.BOLD),
                ft.Text(t.get("settings.account.backup_descr"), size=12),
                ft.Row([export_btn, import_btn], spacing=12),
            ], spacing=10),
            padding=20,
            width=PAGE_WIDTH,
        )

    async def _on_export_backup(self, e):
        t = self.state.translator
        zip_bytes = config_service.export_backup(self.state.config_folder)
        filename = "portfolio_backup.zip"
        await save_bytes(self.page, self.file_picker, filename, zip_bytes, "zip",
                         t.get("settings.account.export_success", filename=filename))

    async def _on_import_backup(self, e):
        t = self.state.translator
        files = await self.file_picker.pick_files(
            allowed_extensions=["zip"], allow_multiple=False, with_data=True,
        )
        if not files:
            return
        picked = files[0]

        # with_data=True makes every platform return the file contents in
        # picked.bytes (Android may give no usable path); the path is a fallback.
        zip_bytes = picked.bytes
        if not zip_bytes and picked.path:
            try:
                with open(picked.path, "rb") as f:
                    zip_bytes = f.read()
            except OSError:
                pass

        if not zip_bytes:
            show_snack(self.page, t.get("settings.account.import_error"), error=True)
            return

        try:
            config_service.validate_backup(zip_bytes)
        except ValidationError as ex:
            show_snack(self.page, error_message(t, ex), error=True)
            return

        self._pending_import = zip_bytes
        self._show_import_confirm_dialog()

    def _show_import_confirm_dialog(self):
        t = self.state.translator
        dlg = ft.AlertDialog(
            title=ft.Text(t.get("settings.account.import_backup")),
            content=ft.Text(t.get("settings.account.import_warning") +
                            t.get("settings.account.suggest_backup")),
            actions=[
                ft.TextButton(t.get("components.cancel"),
                              on_click=lambda e: self.page.pop_dialog()),
                ft.TextButton(
                    t.get("settings.account.import_backup"),
                    style=ft.ButtonStyle(color=ft.Colors.RED),
                    on_click=lambda e: self._confirm_import(),
                ),
            ],
        )
        self.page.show_dialog(dlg)

    def _confirm_import(self):
        self.page.pop_dialog()
        try:
            config_service.import_backup(self.state.config_folder, self._pending_import)
            self.app.restart()
        except Exception as ex:
            show_snack(self.page, str(ex), error=True)

    # ── Reset ─────────────────────────────────────────────────────────

    def _build_reset_section(self) -> ft.Control:
        t = self.state.translator
        return ft.Container(
            content=ft.Column([
                ft.Text(t.get("settings.account.reset_title"), size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.RED),
                ft.Text(t.get("settings.account.reset_warning"), size=12),
                ft.OutlinedButton(
                    "Reset",
                    icon=ft.Icons.DELETE_FOREVER,
                    style=ft.ButtonStyle(color=ft.Colors.RED),
                    on_click=self._on_reset_click,
                ),
            ], spacing=10),
            padding=20,
            width=PAGE_WIDTH,
        )

    def _on_reset_click(self, e):
        t = self.state.translator
        self.reset_field = rounded_text_field(
            label=t.get("settings.account.reset_confirm"),
            on_change=self._on_reset_field_change,
            expand=True,
        )
        self._reset_confirm_btn = ft.TextButton(
            "RESET", on_click=lambda e: self._confirm_reset(), disabled=True,
        )
        content = ft.Container(
            ft.Column([
                ft.Text(t.get("settings.account.reset_warning") + 
                        t.get("settings.account.suggest_backup")),
                self.reset_field,
            ], scroll=ft.ScrollMode.AUTO, tight=True)
        )
        dlg = ft.AlertDialog(
            title=ft.Text(t.get("settings.account.reset_title"), color=ft.Colors.RED),
            content=content,
            actions=[
                ft.TextButton(t.get("components.cancel"), on_click=lambda e: self.page.pop_dialog()),
                self._reset_confirm_btn,
            ],
        )
        self.page.show_dialog(dlg)

    def _on_reset_field_change(self, e):
        self._reset_confirm_btn.disabled = (e.control.value.strip() != "RESET")
        self.page.update()

    def _confirm_reset(self):
        if self.reset_field.value.strip() == "RESET":
            s = self.state
            self.page.pop_dialog()
            try:
                config_service.reset_application(s.config_folder)
                self.app.restart()
            except OSError as ex:
                show_snack(self.page, s.translator.get("settings.account.deletion_error", e=str(ex)), error=True)

    # ── Policies / Contacts ─────────────────────────────────────────────────────────

    def _build_info_section(self) -> ft.Control:
        t = self.state.translator

        privacy_policy = ft.Container(
            ft.Row([
                ft.Text(t.get("settings.privacy_policy"), size=16, weight=ft.FontWeight.BOLD),
            ], expand=True),
            on_click=lambda _: show_privacy_policy(self.page, self.state),
            padding=ft.Padding.only(left=16, right=16, top=12, bottom=12),
            border_radius=15,
            ink=True,
        )

        contact_us = ft.Container(
            ft.Row([
                ft.Text(t.get("settings.contacts"), size=16, weight=ft.FontWeight.BOLD),
            ], expand=True),
            on_click=lambda _: show_contacts(self.page, self.state),
            padding=ft.Padding.only(left=16, right=16, top=12, bottom=12),
            border_radius=15,
            ink=True,
        )

        version_text = ft.Container(
            ft.Text(f"Portfolio Manager {APP_VERSION}", size=12, color=ft.Colors.GREY, text_align=ft.TextAlign.CENTER),
            alignment=ft.alignment.Alignment.CENTER,
            padding=ft.Padding.only(top=15),
        )

        return ft.Container(
            content=ft.Column([
                privacy_policy,
                contact_us,
                build_github_repo(self.state, img_size=44, font_size=16, font_bold=True),
                version_text,
            ], spacing=7),
            padding=10,
            width=PAGE_WIDTH,
        )