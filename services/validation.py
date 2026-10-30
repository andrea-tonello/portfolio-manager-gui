"""Checks on what the user typed or picked in a form, shared by the screens.

Each function returns the clean value, or raises ValidationError with the
locale key of the message to show (see domain/errors.py). A screen runs its
checks in the order of its fields, so the user is told about the first problem.
"""

from datetime import date

from domain.errors import ValidationError
from domain.ledger import LEDGER_START_DATE
from utils.constants import DATE_FORMAT


def parse_positive(text: str | None, error_key: str, *, integer: bool = False, allow_zero: bool = False,
                   empty: float | None = None) -> int | float:
    """Return the number typed in `text`, which must be above zero (or zero too, with `allow_zero`).

    Raises ValidationError(error_key) for text that isn't a number, or is too
    small. Blank text gives `empty` when one is given (an optional field), and
    is refused otherwise.

    Examples: parse_positive("5", key, integer=True) -> 5;
    parse_positive("", key, allow_zero=True, empty=0.0) -> 0.0;
    parse_positive("0", key) and parse_positive("5.5", key, integer=True) raise.
    """
    text = (text or "").strip()
    if not text and empty is not None:
        return empty
    try:
        value = int(text) if integer else float(text)
    except ValueError:
        raise ValidationError(error_key) from None
    if value < 0 or (value == 0 and not allow_zero):
        raise ValidationError(error_key)
    return value


def validate_date(day: date | None) -> date:
    """Return `day`, the date of a new operation, if it is given, not in the future and not before 01-01-2000.

    It can come before operations already recorded: they are then rebuilt
    after it (journal_service.record). Every account opens on 01-01-2000
    (LEDGER_START_DATE), so no operation can come before that.

    Example: 31-12-1999 raises ValidationError("misc_errors.date_too_early", date="01-01-2000").
    """
    if day is None:
        raise ValidationError("misc_errors.nodate")
    if day > date.today():
        raise ValidationError("misc_errors.date_future")
    if day < LEDGER_START_DATE.date():
        raise ValidationError("misc_errors.date_too_early", date=LEDGER_START_DATE.strftime(DATE_FORMAT))
    return day


def validate_date_range(start: date | None, end: date | None) -> tuple[date, date]:
    """Return (start, end) if both are given, neither is in the future, and start comes before end."""
    if start is None or end is None:
        raise ValidationError("misc_errors.nodate")
    if start > date.today() or end > date.today():
        raise ValidationError("misc_errors.date_future")
    if start >= end:
        raise ValidationError("misc_errors.date_start_end")
    return start, end
