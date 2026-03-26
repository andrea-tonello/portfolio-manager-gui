def chain_focus(fields):
    """Wire on_submit on each field to focus the next visible field in the list.

    Each entry is either a TextField or a tuple (TextField, visibility_control)
    where visibility_control is the control whose .visible determines if the
    field is reachable (e.g. a parent Row that hides/shows the field).
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
