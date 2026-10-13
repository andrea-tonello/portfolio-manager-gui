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


def scrolling_form(form, fields, prefix, padding, *, button, loading) -> ft.Container:
    """Return a tab's `form` in a column that scrolls, above its `button` kept at the bottom of the tab.

    Each of `fields` is brought into view when it is focused (`fields` and
    `prefix` are as for scroll_into_view_on_focus).

    `button` (the pill confirming the form) stays in view below the scrolling
    column, as on the onboarding screens. `loading`, the spinner shown while
    it works, has a slot at its left, matched by an empty one at its right:
    the button stays centred and nothing moves when the spinner appears.

    `padding` is the space around the form. Above and below it goes outside
    the scrolling column; left and right it goes inside, so the column itself
    starts at the tab's left edge. Flet's scroll_to moves every scrolling
    area around the field, the swipeable tabs included, until what it scrolls
    is at their start: a column set in from the edge made the whole tab slide
    left by that much, then spring back, whenever a field was focused.
    """
    scroller = ft.Column(
        [ft.Container(form, padding=ft.Padding.symmetric(horizontal=padding))],
        scroll=ft.ScrollMode.AUTO,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        expand=True,
    )
    scroll_into_view_on_focus(scroller, fields, prefix)
    pinned = ft.Row([
        ft.Container(loading, width=loading.width),
        button,
        ft.Container(width=loading.width),
    ], alignment=ft.MainAxisAlignment.CENTER)
    return ft.Container(
        ft.Column([scroller, pinned], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
        padding=ft.Padding.symmetric(vertical=padding),
        expand=True,
    )


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
