"""A date input: a text field for typing DD-MM-YYYY plus a calendar button opening Flet's date picker."""

from datetime import date, datetime, timedelta

import flet as ft

from components.inputs import DATE_INPUT_FILTER, rounded_text_field
from domain.ledger import LEDGER_START_DATE
from utils.constants import DATE_FORMAT
from utils.date_utils import parse_date_input


class DateField:
    """A date the user can type (DD-MM-YYYY) or pick from a calendar.

    `control` is the row to place in a layout; `field` is the text box (for
    focus chains and scroll keys); `value` is the date typed or picked, or None
    while the text isn't a complete, valid date.

    `min_date` / `max_date` limit the picker. Each can be a date, or a function
    returning one (asked when the picker opens), so two fields can limit each
    other; None, or a function returning None, means the default: the
    accounts' opening date (LEDGER_START_DATE) and today.
    """

    def __init__(self, page: ft.Page, label: str, hint_text: str, *, min_date=None, max_date=None):
        """Build the text box and the calendar button; the value starts empty."""
        self.page = page
        self.min_date = min_date
        self.max_date = max_date
        self._value = None
        self.field = rounded_text_field(
            label=label,
            hint_text=hint_text,
            keyboard_type=ft.KeyboardType.DATETIME,
            input_filter=DATE_INPUT_FILTER,
            on_change=self._on_typed,
            expand=True,
        )
        self.button = ft.FilledTonalIconButton(icon=ft.Icons.CALENDAR_MONTH, on_click=self._open_picker)
        self.control = ft.Row([self.field, self.button])

    @property
    def value(self) -> date | None:
        """The chosen date, or None."""
        return self._value

    @value.setter
    def value(self, day: date | None):
        """Set the date and show it in the text box (empty for None)."""
        self._value = day
        self.field.value = day.strftime(DATE_FORMAT) if day else ""

    def _on_typed(self, e):
        """Update the value while the user types; the text is left as typed."""
        self._value = parse_date_input(e.control.value)

    def _open_picker(self, e):
        """Open the date picker, limited to the dates allowed right now."""
        picker = ft.DatePicker(
            first_date=_as_datetime(_resolve(self.min_date) or LEDGER_START_DATE),
            last_date=_as_datetime(_resolve(self.max_date) or datetime.now()),
            on_change=self._on_picked,
        )
        self.page.show_dialog(picker)

    def _on_picked(self, e):
        """Use the picked day as the value.

        The picker reports midnight of the chosen day in UTC, which in a time
        zone behind UTC arrives as the evening before. Adding 12 hours before
        taking the date lands on the chosen day either way.
        """
        picked = e.control.value
        if isinstance(picked, datetime):
            picked = (picked + timedelta(hours=12)).date()
        self.value = picked
        self.page.update()


def date_range_fields(page: ft.Page, start_label: str, end_label: str, hint_text: str):
    """Return (start, end) DateFields whose pickers keep the end at least a day after the start.

    Example: with the end set to 30-06-2024, the start's picker stops at
    29-06-2024; with the start set to 01-03-2024, the end's picker starts at
    02-03-2024. Dates typed by hand are not limited; the screens check them.
    """
    start = DateField(page, start_label, hint_text)
    end = DateField(page, end_label, hint_text)
    start.max_date = lambda: end.value - timedelta(days=1) if end.value else None
    end.min_date = lambda: start.value + timedelta(days=1) if start.value else None
    return start, end


def _resolve(bound):
    """Return the limit itself, or call it first if it is a function."""
    return bound() if callable(bound) else bound


def _as_datetime(day):
    """The date picker takes datetimes: turn a plain date into midnight of that day."""
    return day if isinstance(day, datetime) else datetime.combine(day, datetime.min.time())
