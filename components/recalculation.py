"""Recalculating the history from the screens: from Settings, or offered at start after an update that changes the rules.

The work is services/recalculation_service.py's; the rules version is domain/rules.py's.
"""

import flet as ft

from components.dialogs import close_dialog, working_dialog
from components.journal_change import ask, change_accounts
from components.journal_migration import differences_text
from components.snack import show_snack
from domain import rules
from services import recalculation_service


def recalculate_history(app) -> None:
    """Ask whether to recalculate the history, saying what that does; if so, recalculate it (see _recalculate).

    From Settings, which stays shown: the tabs show the new values when the user goes back to them.
    """
    t = app.state.translator
    question = (t.get("journal.recalculate.title"), t.get("journal.recalculate.explained"),
                t.get("journal.recalculate.confirm"))
    ask(app.page, t, question, on_confirm=lambda: _recalculate(app, then=lambda: None), on_cancel=lambda: None)


def offer_recalculation(app) -> None:
    """At start, offer to recalculate the history when the user's accounts were last computed with older rules.

    The offer lists what each newer version of the rules changed
    (RULES_CHANGES). "Later" asks again at the next start. A user without
    any operation has nothing to recalculate: their accounts count as
    computed with the current rules at once (AppState.note_rules_current,
    unless one of them couldn't be loaded). Example: rules noted as version
    1, the app's at 2 -> "This version of the app calculates some values
    differently: - The Tax Carryforward now expires on 31 December ...",
    with Later and Recalculate.
    """
    state = app.state
    t = state.translator
    since = state.rules_version()
    if since >= rules.RULES_VERSION:
        return
    if not any(account.journal for account in state.accounts.values()):
        state.note_rules_current()
        return
    changed = [t.get(key) for version, key in sorted(rules.RULES_CHANGES.items()) if version > since]
    # Plain texts, whose line breaks show as written; only the list of changes is Markdown.
    text = ft.Column([
        ft.Text(t.get("journal.recalculate.offer")),
        *([ft.Markdown("\n".join(f"- {sentence}" for sentence in changed))] if changed else []),
        ft.Text(t.get("journal.recalculate.explained")),
    ], spacing=12, tight=True)
    ask(app.page, t, (t.get("journal.recalculate.offer_title"), text, t.get("journal.recalculate.confirm")),
        on_confirm=lambda: _recalculate(app, then=app.refresh, when_busy=lambda: offer_recalculation(app)),
        on_cancel=lambda: None, cancel_label=t.get("journal.recalculate.later"))


def _recalculate(app, then, when_busy=None) -> None:
    """Recalculate every account's history in the background, list the values that change, and save if the user agrees.

    A dialog says it is under way meanwhile. When no value changes (market
    values aside: they are re-priced anyway) it is saved at once. Saving
    keeps the ledgers whose values change and notes the current rules
    (AppState.commit_recalculation); then `then` runs. Offline, or with an
    operation the current rules refuse, nothing is saved and a snack says
    why. While another change is under way, a snack says so and
    `when_busy` runs, e.g. offering the recalculation again.
    """
    page, state = app.page, app.state
    t = state.translator
    if state.changing:
        show_snack(page, t.get("journal.busy"), error=True)
        if when_busy is not None:
            when_busy()
        return
    working = working_dialog(t.get("journal.recalculate.working"))
    page.show_dialog(working)

    def work_out():
        """Recalculate every account; the dialog closes when it is done, however it ends."""
        try:
            return recalculation_service.recalculate(state.accounts)
        finally:
            close_dialog(page, working)

    def question(changes):
        """The question listing the values the recalculation changes, or None when there are none."""
        found = recalculation_service.differences(state.accounts, changes)
        if not found:
            return None
        text = ft.Markdown(differences_text(state, found, "journal.recalculate.differences_intro"))
        return t.get("journal.recalculate.differences_title"), text, t.get("journal.recalculate.save")

    change_accounts(app, work_out, question=question, saved_message=t.get("journal.recalculate.done"), then=then,
                    commit=state.commit_recalculation)
