"""A date input: a text field for typing DD-MM-YYYY plus a calendar button opening Flet's date picker."""

import calendar
import re
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

    `on_change`, when set, is called with no arguments after the user types
    or picks a date; setting `value` in code doesn't call it.
    """

    def __init__(self, page: ft.Page, label: str, hint_text: str, *, min_date=None, max_date=None):
        """Build the text box and the calendar button; the value starts empty."""
        self.page = page
        self.min_date = min_date
        self.max_date = max_date
        self.on_change = None
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
        """Add the dashes while the user types digits, and update the value.

        Examples: typing 02102026 shows 02-10-2026; "021" shows "02-1". A dash
        typed after a one-digit day or month adds its zero ("2-" shows "02"),
        and digits past a full date are dropped.
        """
        typed = e.control.value or ""
        digits = "".join(c for c in re.sub(r"(?<!\d)(\d)-", r"0\1-", typed) if c.isdigit())[:8]
        text = "-".join(part for part in (digits[:2], digits[2:4], digits[4:]) if part)
        if text != typed:
            self.field.value = text
            self.page.update()
        self._value = parse_date_input(text)
        if self.on_change:
            self.on_change()

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
        if self.on_change:
            self.on_change()
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


# The periods offered above a start/end pair (PeriodShortcuts), in screen order. Each ends today;
# their labels are "components.periods.<period>" in the locale files.
PERIODS = ("1m", "3m", "6m", "1y", "3y", "ytd", "max")
_PERIOD_MONTHS = {"1m": 1, "3m": 3, "6m": 6, "1y": 12, "3y": 36}


def period_start(period: str, today: date, first_day: date | None) -> date | None:
    """Return the first day of `period` ending `today`, never before `first_day` (the first operation, or None).

    "ytd" starts on 1 January, "max" on `first_day`. The others go back that
    many months, to the same day of the month, or to the month's last day when
    it is shorter. With today 31-03-2026: "1m" -> 28-02-2026, "1y" -> 31-03-2025,
    "ytd" -> 01-01-2026. A period longer than the history starts on its first
    day instead: with the first operation on 04-03-2025, "3y" -> 04-03-2025.
    """
    if period == "max":
        return first_day
    if period == "ytd":
        start = date(today.year, 1, 1)
    else:
        year, month = divmod(today.year * 12 + today.month - 1 - _PERIOD_MONTHS[period], 12)
        month += 1
        start = date(year, month, min(today.day, calendar.monthrange(year, month)[1]))
    return max(start, first_day) if first_day else start


class PeriodShortcuts:
    """Buttons above a start/end pair of DateFields that fill them with a period ending today: 1M ... 3Y, YTD, MAX.

    It starts on MAX, from `first_day` (the first operation; the start stays
    empty when None) to today. The dates can still be typed or picked by hand,
    which unselects the button: it no longer describes them. `control` is
    the row to place above the two fields.
    """

    def __init__(self, translator, start: DateField, end: DateField, first_day: date | None):
        """Build the buttons, fill the dates with MAX, and listen for dates set by hand."""
        self.start, self.end, self.first_day = start, end, first_day
        self.buttons = ft.SegmentedButton(
            show_selected_icon=False,
            selected=["max"],
            allow_multiple_selection=False,
            allow_empty_selection=False,  # True only while the dates were set by hand (_on_dates_set_by_hand)
            expand=True,  # as wide as its row
            style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=4)),
            on_change=lambda _: self._select(self.buttons.selected[0]) if self.buttons.selected else None,
            segments=[ft.Segment(value=period, label=translator.get(f"components.periods.{period}"))
                      for period in PERIODS],
        )
        self.control = ft.Row([self.buttons])
        start.on_change = end.on_change = self._on_dates_set_by_hand
        self._fill("max")

    def _fill(self, period):
        """Set the two dates to `period`, ending today."""
        today = date.today()
        self.start.value, self.end.value = period_start(period, today, self.first_day), today

    def _select(self, period):
        """The user picked `period`: fill the dates with it, and keep a period selected from now on."""
        self._fill(period)
        self.buttons.allow_empty_selection = False
        self.start.page.update()

    def _on_dates_set_by_hand(self):
        """A date was typed or picked: no period is selected any more (tapping one fills the dates again)."""
        if self.buttons.selected:
            self.buttons.selected = []
            self.buttons.allow_empty_selection = True
            self.start.page.update()


def _resolve(bound):
    """Return the limit itself, or call it first if it is a function."""
    return bound() if callable(bound) else bound


def _as_datetime(day):
    """The date picker takes datetimes: turn a plain date into midnight of that day."""
    return day if isinstance(day, datetime) else datetime.combine(day, datetime.min.time())
