"""Date inputs: a text field for typing DD-MM-YYYY plus a calendar button opening Flet's date picker,
and a start/end range shown as text, with one button opening a dialog to change both."""

import calendar
import re
from datetime import date, datetime, timedelta

import flet as ft

from components.focus_chain import chain_focus
from components.inputs import DATE_INPUT_FILTER, rounded_text_field
from components.snack import error_message
from domain.errors import ValidationError
from domain.ledger import LEDGER_START_DATE
from services.validation import validate_date_range
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
        """Open the date picker on the date shown (or today), limited to the dates allowed right now."""
        last = _as_datetime(_resolve(self.max_date) or datetime.now())
        first = min(_as_datetime(_resolve(self.min_date) or LEDGER_START_DATE), last)
        shown = _as_datetime(self.value or date.today())
        picker = ft.DatePicker(
            first_date=first,
            last_date=last,
            value=min(max(shown, first), last),
            on_change=self._on_picked,
        )
        self.page.show_dialog(picker)

    def _on_picked(self, e):
        """Use the picked day as the value."""
        self.value = _picked_day(e.control.value)
        if self.on_change:
            self.on_change()
        self.page.update()


class _RangeDate:
    """One end of a DateRange: its date, and the calendar limit and listener a DateField would have.

    `value` is the date (None while unset); setting it redraws the range's
    text, but doesn't call `on_change`, which is for dates the user changed.
    `min_date` / `max_date` limit the dialog's calendars, as for a DateField
    (only the start's min_date and the end's max_date are used).
    """

    def __init__(self, page: ft.Page, redraw):
        """An unset date; `redraw()` writes the range's text again."""
        self.page = page
        self.min_date = None
        self.max_date = None
        self.on_change = None
        self._value = None
        self._redraw = redraw

    @property
    def value(self) -> date | None:
        """The date, or None."""
        return self._value

    @value.setter
    def value(self, day: date | None):
        """Set the date and show it in the range's text."""
        self._value = day
        self._redraw()


class DateRange:
    """A start and an end date shown as text, with one button opening a dialog to change both.

    The text reads e.g. "Dal: 04-03-2025   Al: 26-10-2026" ("—" for a date
    not set). `start` and `end` hold the dates (see _RangeDate); `control` is
    the row to place in a layout. The dialog has the two dates as DateFields,
    so they are typed as anywhere else in the app (digits only, dashes added),
    or picked from each one's calendar. Its OK sets both and calls their
    `on_change`.
    """

    def __init__(self, page: ft.Page, translator, start_label: str, end_label: str):
        """Build the text and the button; both dates start unset."""
        self.page = page
        self.t = translator
        self._labels = (start_label, end_label)
        self.text = ft.Text(size=16, expand=True)
        self.start = _RangeDate(page, self._redraw)
        self.end = _RangeDate(page, self._redraw)
        self.button = ft.FilledTonalIconButton(icon=ft.Icons.DATE_RANGE, on_click=self._open_dialog)
        self.control = ft.Row([self.text, self.button])
        self._redraw()

    def _redraw(self):
        """Write each label with its date in bold, or "—" while it is not set."""
        spans = []
        for label, day, gap in zip(self._labels, (self.start.value, self.end.value), ("    ", "")):
            spans.append(ft.TextSpan(f"{label}: "))
            spans.append(ft.TextSpan(day.strftime(DATE_FORMAT) if day else "—",
                                     style=ft.TextStyle(weight=ft.FontWeight.BOLD)))
            spans.append(ft.TextSpan(gap))
        self.text.spans = spans

    def _open_dialog(self, e):
        """Open the dialog with the two dates shown, as DateFields to type or pick them.

        The start's calendar runs from `start.min_date` (by default the
        accounts' opening date) to the day before the end; the end's from the
        day after the start to `end.max_date` (by default today). OK checks
        both dates (given, not in the future, the start first) and either says
        what is wrong inside the dialog, or sets them and closes it.
        """
        t = self.t
        hint = t.get("components.date_format_hint")
        start = DateField(self.page, self._labels[0], hint)
        end = DateField(self.page, self._labels[1], hint)
        start.min_date = self.start.min_date
        start.max_date = lambda: end.value - timedelta(days=1) if end.value else _resolve(self.end.max_date)
        end.min_date = lambda: start.value + timedelta(days=1) if start.value else _resolve(self.start.min_date)
        end.max_date = self.end.max_date
        start.value, end.value = self.start.value, self.end.value
        error = ft.Text(color=ft.Colors.ERROR, size=13, visible=False)
        chain_focus([start.field, end.field])

        def on_ok(_):
            """Set the two dates, or say what is wrong with them."""
            try:
                first, last = validate_date_range(start.value, end.value)
            except ValidationError as ex:
                error.value, error.visible = error_message(t, ex), True
                self.page.update()
                return
            self.page.pop_dialog()
            self._set(first, last)

        self.page.show_dialog(ft.AlertDialog(
            title=ft.Text(t.get("components.pick_range")),
            content=ft.Column([start.control, end.control, error], tight=True, spacing=16, width=400),
            actions=[
                ft.TextButton(t.get("components.cancel"), on_click=lambda _: self.page.pop_dialog()),
                ft.FilledButton(t.get("components.confirm"), on_click=on_ok),
            ],
        ))

    def _set(self, start, end):
        """Set both dates as the user chose them, tell each date's listener once, and redraw."""
        self.start.value, self.end.value = start, end
        for listener in {self.start.on_change, self.end.on_change} - {None}:
            listener()
        self.page.update()


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


def _picked_day(picked):
    """The day a date picker reported, as a date.

    The pickers report midnight of the chosen day in UTC, which in a time zone
    behind UTC arrives as the evening before. Adding 12 hours before taking the
    date lands on the chosen day either way: 09-05-2024 22:00 -> 10-05-2024.
    """
    if isinstance(picked, datetime):
        return (picked + timedelta(hours=12)).date()
    return picked
