"""Moving the accounts recorded before the journal to it, once, when the app starts.

It runs before Home is shown, so nothing else can open a dialog over it or
record an operation meanwhile (Home's split prompt, the update notice come
after). While migration_service works out each account's journal (it
downloads prices), a dialog that can't be closed says the accounts are
being updated. Then the accounts are saved, after showing the values that
came out different, if any, and Home is shown. If it fails, nothing is
saved, the user is told, and the next start tries again.
"""

import logging

import flet as ft

from components.dialogs import show_info_dialog
from components.snack import error_message, show_snack
from domain.errors import ValidationError
from services import migration_service
from utils.columns import export_headers, localized_value_maps

logger = logging.getLogger(__name__)

# How many of an account's differences the dialog lists before "...and N more".
_SHOWN_DIFFERENCES = 10


def needs_migration(state) -> bool:
    """Return True when an account of the current user has no journal yet."""
    return any(account.journal is None for account in state.accounts.values())


def migrate_accounts(app, then) -> None:
    """Move every account of the current user without a journal to it, in the background, then call `then`.

    `then` shows what comes next (Home), whether the migration succeeded or not.
    """
    state, page, t = app.state, app.page, app.state.translator
    working = ft.AlertDialog(
        modal=True,
        title=ft.Text(t.get("journal.migration.title")),
        content=ft.Row([ft.ProgressRing(width=24, height=24), ft.Text(t.get("journal.migration.working"), expand=True)],
                       spacing=16, tight=True),
    )
    page.show_dialog(working)

    def worker():
        """Work out the journals off the screen's thread, then save them or first show what differs."""
        try:
            migrations = migration_service.migrate(state.accounts)
        except ValidationError as ex:  # an operation that can't be converted: the same at every start
            logger.exception("Could not move the accounts to the journal")
            _close(page, working)
            then()
            show_info_dialog(page, t.get("journal.migration.title"), error_message(t, ex))
            return
        except Exception:  # most likely offline: no prices
            logger.exception("Could not move the accounts to the journal")
            _close(page, working)
            then()
            show_snack(page, t.get("journal.migration.failed"), error=True)
            return
        _close(page, working)
        if any(migration.differences for migration in migrations.values()):
            _show_differences(app, migrations, then)
        else:
            _save(app, migrations, then)

    page.run_thread(worker)


def _close(page, dialog) -> None:
    """Close `dialog` itself: page.pop_dialog() would close whichever dialog was opened last."""
    dialog.open = False
    page.update()


def _save(app, migrations, then) -> None:
    """Save the migrated accounts, then call `then`. Work them out again if an account changed meanwhile."""
    try:
        saved = app.state.commit_migration(migrations)
    except OSError:
        logger.exception("Could not save the accounts moved to the journal")
        then()
        show_snack(app.page, app.state.translator.get("journal.migration.failed"), error=True)
        return
    if not saved:
        migrate_accounts(app, then)
        return
    then()


def differences_text(state, migrations) -> str:
    """Return, as Markdown, the values that differ in each migrated account, in the user's language.

    Example: "**Fineco**\n- 05-03-2025 · Buy ISP.MI · Eff. Value: -3901.25 → -3901.26".
    At most _SHOWN_DIFFERENCES per account, then how many more, as a line of its own.
    """
    t = state.translator
    headers, operations = export_headers(t), localized_value_maps(t)["operation"]
    parts = [t.get("journal.migration.differences_intro")]
    for idx, migration in migrations.items():
        if not migration.differences:
            continue
        lines = [f"**{state.accounts[idx].name}**"]
        for d in migration.differences[:_SHOWN_DIFFERENCES]:
            what = " ".join(filter(None, [operations.get(d.operation, d.operation), d.ticker]))
            lines.append(f"- {d.date} · {what} · {headers[d.column]}: {_shown(d.before)} → {_shown(d.after)}")
        part = "\n".join(lines)
        hidden = len(migration.differences) - _SHOWN_DIFFERENCES
        if hidden > 0:  # a paragraph of its own: right after the list, it would join its last line
            part += "\n\n" + t.get("journal.migration.more", count=hidden)
        parts.append(part)
    return "\n\n".join(parts)


def _shown(value) -> str:
    """Return a ledger value as the differences list shows it: numbers rounded to 6 decimals, "—" for an empty cell."""
    if value is None or (isinstance(value, float) and value != value):
        return "—"
    return str(round(value, 6)) if isinstance(value, float) else str(value)


def _show_differences(app, migrations, then) -> None:
    """Show the values that came out different, and save the accounts when the user continues."""
    page, t = app.page, app.state.translator
    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(t.get("journal.migration.differences_title")),
        content=ft.Container(ft.Markdown(differences_text(app.state, migrations)), width=450),
        scrollable=True,
    )

    def on_continue(_):
        """Close the dialog and save the accounts with their recalculated values."""
        _close(page, dialog)
        _save(app, migrations, then)

    dialog.actions = [ft.TextButton(t.get("journal.migration.continue"), on_click=on_continue)]
    page.show_dialog(dialog)
