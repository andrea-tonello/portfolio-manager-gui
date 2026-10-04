"""Tests for components/date_field.py: the date input used by Operations and Analysis.

A DateField is a text field where the date can be typed as DD-MM-YYYY, plus a
calendar button that opens Flet's date picker. `value` is the date typed or
picked, or None while the text isn't a valid date.
"""

from datetime import date, datetime
from types import SimpleNamespace

import flet as ft
import pytest

from components.date_field import DateField, date_range_fields
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


def test_setting_the_value_shows_it_in_the_field(field):
    """Assigning `value` also updates the text, so what is shown always matches."""
    field.value = date(2024, 1, 31)

    assert field.field.value == "31-01-2024"


def test_a_start_end_pair_keeps_the_end_after_the_start(page):
    """In a start/end pair, each picker stops a day short of the other date, so the start always comes first."""
    start, end = date_range_fields(page, "From", "To", "DD-MM-YYYY")
    start.value = date(2024, 3, 1)
    end.value = date(2024, 6, 30)

    assert _open_picker(start, page).last_date == datetime(2024, 6, 29)
    assert _open_picker(end, page).first_date == datetime(2024, 3, 2)


def test_a_pair_with_no_dates_yet_uses_the_default_limits(page):
    """Until the other date is set, each picker of the pair allows the full range."""
    start, end = date_range_fields(page, "From", "To", "DD-MM-YYYY")

    assert _open_picker(start, page).last_date.date() == date.today()
    assert _open_picker(end, page).first_date == LEDGER_START_DATE
