"""Tests for components/date_field.py: the date input used by Operations and Analysis.

A DateField is a text field where the date can be typed as DD-MM-YYYY, plus a
calendar button that opens Flet's date picker. `value` is the date typed or
picked, or None while the text isn't a valid date. A start/end range
(DateRange) is shown as text, with one button opening a dialog to change both
dates, and period shortcuts (1M ... MAX) fill the range with a period ending today.
"""

from datetime import date, datetime
from types import SimpleNamespace

import flet as ft
import pytest

from components.date_field import DateField, DateRange, PeriodShortcuts, period_start
from domain.ledger import LEDGER_START_DATE


def _type(field, text):
    """Type `text` into the DateField's text box, as the user would."""
    field.field.value = text
    field.field.on_change(SimpleNamespace(control=field.field))


def _open_picker(field, page):
    """Tap the calendar button and return the date picker it opens."""
    field.button.on_click(None)
    picker = page.dialogs[-1]
    assert isinstance(picker, ft.DatePicker)
    return picker


def _pick(picker, picked):
    """Choose `picked` in an open date picker, as Flet reports it."""
    picker.value = picked
    picker.on_change(SimpleNamespace(control=picker))


@pytest.fixture
def field(page):
    """A DateField on the fake page."""
    return DateField(page, "Date", "DD-MM-YYYY")


@pytest.mark.parametrize("text, expected", [
    ("10-05-2024", date(2024, 5, 10)),
    (" 10-05-2024 ", date(2024, 5, 10)),
    ("10-05-20", None),        # incomplete year
    ("31-02-2024", None),      # no such day
    ("", None),
])
def test_typing_sets_the_value_once_the_text_is_a_valid_date(field, text, expected):
    """Typed text becomes the value when it is a complete DD-MM-YYYY date, otherwise the value is None."""
    _type(field, text)

    assert field.value == expected


@pytest.mark.parametrize("keys, shown, expected", [
    ("02102026", "02-10-2026", date(2026, 10, 2)),
    ("021", "02-1", None),
    ("02-10-2026", "02-10-2026", date(2026, 10, 2)),   # dashes typed by hand
    ("2-1-2026", "02-01-2026", date(2026, 1, 2)),      # one-digit day and month
    ("0210202699", "02-10-2026", date(2026, 10, 2)),   # digits past the date
])
def test_dashes_are_added_while_typing(field, keys, shown, expected):
    """Typed one key at a time, the digits get their dashes: 02102026 shows 02-10-2026."""
    for key in keys:
        _type(field, (field.field.value or "") + key)

    assert (field.field.value, field.value) == (shown, expected)


@pytest.mark.parametrize("picked", [
    datetime(2024, 5, 10, 0, 0),
    datetime(2024, 5, 9, 22, 0),   # the picker's midnight UTC, seen from a time zone behind UTC
    date(2024, 5, 10),
], ids=["midnight", "evening-before", "plain-date"])
def test_picking_a_date_sets_the_value_and_shows_it(field, page, picked):
    """The picked day becomes the value and is written in the text box, even when the picker reports the evening before."""
    _pick(_open_picker(field, page), picked)

    assert field.value == date(2024, 5, 10)
    assert field.field.value == "10-05-2024"


def test_the_picker_allows_dates_from_the_ledger_start_to_today(field, page):
    """By default nothing before the accounts' opening date or after today can be picked."""
    picker = _open_picker(field, page)

    assert picker.first_date == LEDGER_START_DATE
    assert picker.last_date.date() == date.today()


def test_the_picker_opens_on_the_date_shown_moved_inside_its_limits(field, page):
    """It opens on the date in the field; one outside the limits opens on the nearest limit, as Flutter requires.

    With limits that cross (the earliest allowed after the latest), it narrows
    to the latest day alone instead of failing to open.
    """
    field.value = date(2024, 3, 10)
    assert _open_picker(field, page).value == datetime(2024, 3, 10)

    field.max_date = date(2024, 2, 1)
    assert _open_picker(field, page).value == datetime(2024, 2, 1)

    field.min_date = date(2024, 5, 1)
    picker = _open_picker(field, page)
    assert (picker.first_date, picker.last_date, picker.value) == (datetime(2024, 2, 1),) * 3


# ── A start/end range shown as text, changed in a dialog ─────────────

def _range_dialog(dates, page):
    """Tap the range's button; return the dialog it opens, and its start and end rows as (text box, calendar button)."""
    dates.button.on_click(None)
    dialog = page.dialogs[-1]
    assert isinstance(dialog, ft.AlertDialog)
    start_row, end_row, _ = dialog.content.controls
    return dialog, start_row.controls, end_row.controls


def _type_in(box, text):
    """Type `text` into a dialog's text box, as the user would."""
    box.value = text
    box.on_change(SimpleNamespace(control=box))


def _ok(dialog):
    """Press the dialog's OK."""
    dialog.actions[1].on_click(None)


def _save_range(dates, page, start, end):
    """Open the range's dialog, type `start` and `end` (DD-MM-YYYY) and press OK."""
    dialog, (start_box, _), (end_box, _) = _range_dialog(dates, page)
    _type_in(start_box, start)
    _type_in(end_box, end)
    _ok(dialog)


def _text(dates):
    """The range's text as it reads on screen."""
    return "".join(span.text for span in dates.text.spans)


def test_the_range_reads_as_text_with_a_dash_for_a_date_not_set(page, translator):
    """Each label is followed by its date as DD-MM-YYYY, or by "—" until the date is set; the end goes below the start."""
    dates = DateRange(page, translator, "Dal", "Al")
    assert _text(dates) == "Dal: —\nAl: —"

    dates.start.value, dates.end.value = date(2025, 3, 4), date(2026, 10, 26)

    assert _text(dates) == "Dal: 04-03-2025\nAl: 26-10-2026"


def test_the_dialog_types_dates_as_everywhere_and_ok_sets_them(page, translator):
    """It opens on the dates shown; digits typed get their dashes; OK sets both dates and closes it.

    It counts as dates set by hand: the period shortcut, which no longer
    describes them, is unselected.
    """
    dates = DateRange(page, translator, "Start", "End")
    periods = PeriodShortcuts(translator, dates.start, dates.end, first_day=date(2025, 3, 4))
    dialog, (start_box, _), (end_box, _) = _range_dialog(dates, page)
    assert (start_box.value, end_box.value) == ("04-03-2025", date.today().strftime("%d-%m-%Y"))

    _type_in(start_box, "02062025")
    _type_in(end_box, "01092025")
    assert (start_box.value, end_box.value) == ("02-06-2025", "01-09-2025")
    _ok(dialog)

    assert (dates.start.value, dates.end.value) == (date(2025, 6, 2), date(2025, 9, 1))
    assert _text(dates) == "Start: 02-06-2025\nEnd: 01-09-2025"
    assert periods.buttons.selected == [] and dialog not in page.dialogs


def test_ok_with_the_start_after_the_end_says_so_and_changes_nothing(page, translator):
    """The dialog stays open with the message, and the range keeps its dates."""
    dates = DateRange(page, translator, "Start", "End")
    dates.start.value, dates.end.value = date(2025, 6, 2), date(2025, 9, 1)
    dialog, (start_box, _), _ = _range_dialog(dates, page)

    _type_in(start_box, "02-10-2025")
    _ok(dialog)

    error = dialog.content.controls[-1]
    assert (error.visible, error.value) == (True, "Start date must be before end date")
    assert dialog in page.dialogs and dates.start.value == date(2025, 6, 2)


def test_each_calendar_in_the_dialog_keeps_the_start_before_the_end(page, translator):
    """The start's calendar runs from its limit (here 04-03-2025) to the day before the end; the end's from the day
    after the start to today."""
    dates = DateRange(page, translator, "Start", "End")
    dates.start.min_date = date(2025, 3, 4)
    dates.start.value, dates.end.value = date(2025, 6, 2), date(2025, 9, 1)
    _, (_, start_calendar), (_, end_calendar) = _range_dialog(dates, page)

    start_calendar.on_click(None)
    assert (page.dialogs[-1].first_date, page.dialogs[-1].last_date) == (datetime(2025, 3, 4), datetime(2025, 8, 31))
    end_calendar.on_click(None)
    assert (page.dialogs[-1].first_date, page.dialogs[-1].last_date.date()) == (datetime(2025, 6, 3), date.today())


# ── Period shortcuts ─────────────────────────────────────────────────

@pytest.mark.parametrize("period, today, first_day, expected", [
    ("1m", date(2026, 3, 31), date(2020, 1, 2), date(2026, 2, 28)),   # February is shorter: its last day
    ("1m", date(2028, 3, 31), date(2020, 1, 2), date(2028, 2, 29)),   # ... 29 days in a leap year
    ("3m", date(2026, 5, 31), date(2020, 1, 2), date(2026, 2, 28)),
    ("6m", date(2026, 1, 15), date(2020, 1, 2), date(2025, 7, 15)),   # back across the new year
    ("1y", date(2028, 2, 29), date(2020, 1, 2), date(2027, 2, 28)),   # no 29 February the year before
    ("3y", date(2026, 10, 24), date(2020, 1, 2), date(2023, 10, 24)),
    ("ytd", date(2026, 10, 24), date(2020, 1, 2), date(2026, 1, 1)),
    ("max", date(2026, 10, 24), date(2020, 1, 2), date(2020, 1, 2)),
    ("3y", date(2026, 10, 24), date(2025, 3, 4), date(2025, 3, 4)),   # longer than the history
    ("ytd", date(2026, 10, 24), date(2026, 5, 4), date(2026, 5, 4)),  # first operation this year
    ("3y", date(2026, 10, 24), None, date(2023, 10, 24)),             # first operation unknown
])
def test_each_period_starts_that_far_back_from_today(period, today, first_day, expected):
    """A period goes back that many months to the same day, or the month's last day when it is shorter.

    YTD starts on 1 January, MAX on the first operation. A period reaching back
    before the first operation starts on it instead, when it is known.
    """
    assert period_start(period, today, first_day) == expected


def test_a_period_shortcut_fills_the_dates_and_a_range_picked_by_hand_unselects_it(page, translator):
    """MAX is selected and filled at first; 3M sets the start 3 months back and the end to today.

    Picking a range unselects 3M and keeps the dates picked: the button no
    longer describes them. Tapping 3M again fills them with it again.
    """
    dates = DateRange(page, translator, "From", "To")
    start, end = dates.start, dates.end
    periods = PeriodShortcuts(translator, start, end, first_day=date(2025, 3, 4))
    today = date.today()
    assert (periods.buttons.selected, start.value, end.value) == (["max"], date(2025, 3, 4), today)

    periods.buttons.selected = ["3m"]
    periods.buttons.on_change(None)
    assert (start.value, end.value) == (period_start("3m", today, None), today)

    _save_range(dates, page, "01-01-2026", "01-02-2026")
    assert (periods.buttons.selected, start.value) == ([], date(2026, 1, 1))

    periods.buttons.selected = ["3m"]
    periods.buttons.on_change(None)
    assert start.value == period_start("3m", today, None)
