"""Changing the accounts' operations from a screen: work the change out in the background, ask first if needed, then save it.

Operations records and edits operations through change_accounts, Transactions
removes them, Home records the splits found on Yahoo.
"""

import flet as ft

from components.background import run_in_background
from components.dialogs import close_dialog
from components.snack import show_snack


def change_accounts(app, work_out, *, question=None, saved_message, then=None, loading=None):
    """Work out a change of the accounts in the background with `work_out`, then save it, asking first with `question`.

    `work_out` returns journal_service's changes (record, delete or edit),
    or None once it has said why there are none (e.g. a ticker of the wrong
    kind). They are worked out before asking, so the question only comes for
    a change that can be made: a refusal (the operation's own, or a later
    operation's it makes impossible) is shown instead, in a red snack.

    `question` is (title, text, confirm label), e.g. naming the operations
    that will be recalculated, or None to save at once; Cancel saves
    nothing. Once saved, `saved_message` is shown and `then` runs
    (app.refresh when not given). `loading` is the spinner to show meanwhile.

    One change at a time (AppState.changing), from the tap until it is
    saved, refused or cancelled: another one meanwhile isn't made, and the
    user is told to try again. Saving is refused anyway if an account
    changed meanwhile (AppState.commit_changes).
    """
    page, state = app.page, app.state
    t = state.translator
    if state.changing:
        show_snack(page, t.get("journal.busy"), error=True)
        return
    state.changing = True

    def end():
        """The change is over (saved, refused or cancelled): another can start."""
        state.changing = False

    def in_background(work):
        """Run `work` in the background with the spinner; the change ends with it, unless it is asking first."""
        def guarded():
            """Run `work`, then end the change unless a question is waiting for its answer."""
            asking = False
            try:
                asking = work()
            finally:
                if not asking:
                    end()

        run_in_background(page, t, guarded, loading=loading)

    def save(changes, built_from):
        """Save the changes, say so, and go on with `then`."""
        state.commit_changes(changes, built_from=built_from)
        show_snack(page, saved_message)
        (then or app.refresh)()

    def work_out_and_save():
        """Work out the changes, then save them; or ask first, returning True while the question waits."""
        built_from = state.journals()
        changes = work_out()
        if changes is None:
            return False
        if question is None:
            save(changes, built_from)
            return False
        ask(page, t, question, on_confirm=lambda: in_background(lambda: save(changes, built_from)), on_cancel=end)
        return True

    in_background(work_out_and_save)


def ask(page, translator, question, on_confirm, on_cancel):
    """Show `question`, a (title, text, confirm label), with Cancel: `on_confirm` or `on_cancel` runs, once.

    It may be called from a background thread: the dialog is opened on the
    event loop (page.run_task), as Flet needs. Dismissing it without an
    answer (e.g. Android's back button) cancels. It is closed by reference,
    since another dialog may have opened above it.
    """
    title, text, confirm_label = question
    answered = False

    def answer(go_on):
        """Close the question and go on as answered, unless it was already answered (a second tap)."""
        nonlocal answered
        if answered:
            return
        answered = True
        close_dialog(page, dialog)
        go_on()

    dialog = ft.AlertDialog(
        title=ft.Text(title),
        content=ft.Text(text),
        actions=[
            ft.TextButton(translator.get("components.cancel"), on_click=lambda _: answer(on_cancel)),
            ft.TextButton(confirm_label, on_click=lambda _: answer(on_confirm)),
        ],
        on_dismiss=lambda _: answer(on_cancel),
    )

    async def show():
        """Open the question, on the event loop."""
        page.show_dialog(dialog)

    page.run_task(show)


def recalculated_text(translator, count, group):
    """Say that `count` other operations will be recalculated, in the words of `group` ("journal.insert", ".edit", ".delete").

    Each group has the singular ("one") and the plural ("many"). Example:
    recalculated_text(t, 12, "journal.insert") -> "This operation comes
    before 12 later operations, which will be recalculated (taxes, Tax
    Carryforward and market values included)."
    """
    return translator.get(f"{group}.one" if count == 1 else f"{group}.many", count=count)
