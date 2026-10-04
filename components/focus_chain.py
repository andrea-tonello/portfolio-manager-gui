import flet as ft


def scroll_into_view_on_focus(column, fields, prefix):
    """When one of `fields` gets the focus, scroll `column` so the field is visible (e.g. above the phone's keyboard).

    Each field gets the scroll key "<prefix>-<position>", e.g. "cash-0".
    Flet only scrolls to controls whose key is an ft.ScrollKey (a plain text key is silently ignored), 
    and keeps one registry of these keys for the whole app, so the prefix must differ between the forms of a screen.
    TickerSearchFields can be passed like TextFields.
    """
    async def on_focus(e):
        """Scroll the column to the field that just got the focus."""
        await column.scroll_to(scroll_key=e.control.key, duration=300)

    for position, field in enumerate(fields):
        field.key = ft.ScrollKey(f"{prefix}-{position}")
        field.on_focus = on_focus


def chain_focus(fields):
    """Wire on_submit on each field to focus the next visible field in the list.

    Each entry is either a TextField or a tuple (TextField, visibility_control) where visibility_control 
    is the control whose .visible determines if the field is reachable (e.g. a parent Row that hides/shows the field).
    """
    def _unpack(entry):
        if isinstance(entry, tuple):
            return entry
        return entry, entry

    items = [_unpack(e) for e in fields]

    for i, (field, _) in enumerate(items):
        remaining = items[i + 1:]

        async def handler(_, targets=remaining):
            for target_field, vis_control in targets:
                if vis_control.visible:
                    try:
                        await target_field.focus()
                    except RuntimeError:
                        pass
                    return
        field.on_submit = handler
