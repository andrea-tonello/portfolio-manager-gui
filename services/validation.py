"""Checks on what the user typed or picked in a form, shared by the screens.

Each function returns the clean value, or raises ValidationError with the
locale key of the message to show (see domain/errors.py). A screen runs its
checks in the order of its fields, so the user is told about the first problem.
"""

from datetime import date

import pandas as pd

from domain.errors import ValidationError


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


def validate_date(day: date | None, *, ledger_df: pd.DataFrame | None = None) -> date:
    """Return `day` if it is given and not in the future.

    With `ledger_df` (an account's ledger) it also must not be earlier than the
    last operation recorded there, since each new row builds on the totals of
    the row before it. The same day is fine.

    Example: with the last operation on 02-09-2024, 01-09-2024 raises
    ValidationError("misc_errors.date_sequential") and 02-09-2024 is accepted.
    """
    if day is None:
        raise ValidationError("misc_errors.nodate")
    if day > date.today():
        raise ValidationError("misc_errors.date_future")
    if ledger_df is not None:
        dates = pd.to_datetime(ledger_df["date"], dayfirst=True, errors="coerce").dropna()
        if not dates.empty and day < dates.max().date():
            raise ValidationError("misc_errors.date_sequential")
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
