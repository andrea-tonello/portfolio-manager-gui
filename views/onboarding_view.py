"""The first-launch screens: choose a language, create a user, add the user's accounts.

AppController.restart shows whichever step is still missing. The user and
account screens are also reused when adding a user from the user manager.
"""

import flet as ft

from components.inputs import rounded_dropdown, rounded_text_field, RADIUS
from components.snack import error_message, show_snack
from domain.errors import ValidationError
from services import config_service
from utils.constants import LANGUAGES

# Height of what sits above each screen's input. It is the same on all three
# screens, so the language dropdown and the user and account text fields are
# at the same place on each.
_HEADER_HEIGHT = 220


def _screen(content, bottom):
    """Lay out an onboarding screen inside the safe area, centred and at most 800 wide like the tabs.

    `content` (the header, the input, the accounts added) fills the screen from
    the top and scrolls when it doesn't fit, e.g. with the keyboard open or a
    long list of accounts. `bottom` (the button, and any note above it) stays
    at the bottom, so the button is at the same place on every screen.
    """
    center = ft.CrossAxisAlignment.CENTER
    return ft.SafeArea(
        ft.Container(
            ft.Container(
                ft.Column([
                    ft.Column(content, spacing=15, horizontal_alignment=center, scroll=ft.ScrollMode.AUTO, expand=True),
                    ft.Column(bottom, spacing=15, horizontal_alignment=center, tight=True),
                ], spacing=15, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                width=800,
                padding=15,
            ),
            alignment=ft.alignment.Alignment.TOP_CENTER,
        ),
        expand=True,
    )


def _header(*controls, top=None):
    """The part of an onboarding screen above its input: `controls` at its bottom, `top` (the close button row) at its top."""
    return ft.Container(
        ft.Column([top or ft.Container(), ft.Container(expand=True), *controls],
                  spacing=15, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        height=_HEADER_HEIGHT,
    )


def show_language_picker(app):
    """Show the language choice; applying it saves the language and restarts into the next setup step."""
    page, t = app.page, app.state.translator
    options = [ft.dropdown.Option(key=code, text=name) for code, name in LANGUAGES.items()]
    dd = rounded_dropdown(
        label=t.get("settings.language.title"),
        options=options,
        expand=True,
    )

    def on_submit(e):
        if not dd.value:
            return
        config_service.save_language(app.state.config_folder, dd.value)
        page.controls.clear()
        app.restart()

    page.controls.clear()
    page.controls.append(_screen(
        [
            _header(ft.Text(t.get("settings.language.select"), size=20, weight=ft.FontWeight.BOLD)),
            ft.Row([dd]),  # in a Row, the dropdown's expand fills the width instead of the height
        ],
        [ft.FilledButton(t.get("components.apply"), icon=ft.Icons.CHECK, width=150, height=50, on_click=on_submit)],
    ))
    page.update()


def show_user_creation(app, on_complete=None, first_time=True, on_cancel=None):
    """User creation screen. Used at first boot and when adding users in-app.

    Confirming adds the user and calls `on_complete`, or by default moves on
    to the account screen. `on_cancel`, if given, shows a close button.
    """
    page, state = app.page, app.state
    t = state.translator
    username_field = rounded_text_field(label=t.get("settings.user_mgmt.username_hint"))

    def on_submit(e):
        name = username_field.value.strip()
        if not name:
            return
        try:
            state.add_user(name)
        except ValidationError as ex:
            show_snack(page, error_message(t, ex), error=True)
            return

        if on_complete:
            on_complete()
        else:
            page.controls.clear()
            app.show_broker_onboarding()

    close_btn = ft.IconButton(
        icon=ft.Icons.CLOSE,
        icon_size=28,
        on_click=lambda _: on_cancel(),
        visible=on_cancel is not None,
    )

    page.controls.clear()
    page.controls.append(_screen(
        [
            _header(
                ft.Icon(ft.Icons.PERSON, size=80),
                ft.Container(height=30),
                ft.Text(t.get("settings.user_mgmt.add_title"), size=20, weight=ft.FontWeight.BOLD),
                top=ft.Row([close_btn], alignment=ft.MainAxisAlignment.START),
            ),
            username_field,
        ],
        [
            ft.Text(t.get("settings.user_mgmt.add_later") if first_time else t.get("settings.user_mgmt.duplicate_hint"),
                    size=14, color=ft.Colors.GREY, text_align=ft.TextAlign.CENTER),
            ft.Container(height=20),
            ft.FilledButton(t.get("components.confirm"), icon=ft.Icons.CHECK,
                            width=150, height=50, on_click=on_submit),
        ],
    ))
    page.update()


def show_broker_onboarding(app, on_complete=None, on_cancel=None):
    """Account screen: the user lists their accounts, and Confirm saves them.

    Confirming calls `on_complete`, or by default restarts into the tabs.
    `on_cancel`, if given, shows a close button.
    """
    page, state = app.page, app.state
    t = state.translator
    broker_field = rounded_text_field(
        label=t.get("settings.account.add_account"),
        expand=True,
    )
    broker_list = ft.Column([], spacing=5)
    brokers_temp = {}

    def on_add(e):
        name = broker_field.value.strip()
        if not name:
            return
        # Same rule as AppState.add_broker: names differing only in capitals count as the same.
        if name.casefold() in {existing.casefold() for existing in brokers_temp.values()}:
            show_snack(page, t.get("settings.account.duplicate", account=name), error=True)
            return
        next_idx = max(brokers_temp.keys(), default=0) + 1
        brokers_temp[next_idx] = name

        def on_remove(ev, idx=next_idx):
            brokers_temp.pop(idx, None)
            broker_list.controls[:] = [
                c for c in broker_list.controls
                if c.data != idx
            ]
            page.update()

        broker_list.controls.append(ft.Row([
            ft.Text(f"  {next_idx}. {name}", expand=True),
            ft.IconButton(icon=ft.Icons.DELETE, icon_size=18, on_click=on_remove),
        ], data=next_idx, alignment=ft.MainAxisAlignment.CENTER))
        broker_field.value = ""
        page.update()

    def on_done(e):
        if not brokers_temp:
            show_snack(page, t.get("settings.account.op_denied"), error=True)
            return
        for name in brokers_temp.values():
            state.add_broker(name)
        page.controls.clear()
        if on_complete:
            on_complete()
        else:
            app.restart()

    add_button = ft.FilledButton(
        content=ft.Icon(ft.Icons.ADD_CIRCLE_OUTLINE, size=26),
        height=46,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=RADIUS)),
        on_click=on_add,
    )

    close_btn = ft.IconButton(
        icon=ft.Icons.CLOSE,
        icon_size=28,
        on_click=lambda _: on_cancel(),
        visible=on_cancel is not None,
    )

    page.controls.clear()
    page.controls.append(_screen(
        [
            _header(
                ft.Text(t.get("settings.new_acc", username=state.active_user_name or ""), size=20),
                ft.Text(t.get("settings.new_acc_example"), size=14),
                top=ft.Row([close_btn], alignment=ft.MainAxisAlignment.START),
            ),
            ft.Container(content=ft.Row([broker_field, add_button])),
            broker_list,
        ],
        [ft.FilledButton(t.get("components.confirm"), icon=ft.Icons.CHECK, width=150, height=50, on_click=on_done)],
    ))
    page.update()