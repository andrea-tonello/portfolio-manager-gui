from datetime import date, datetime

from utils.constants import DATE_FORMAT

# A day as the app passes it around: a date, a datetime or a pandas Timestamp
# (both of which are dates too), or "YYYY-MM-DD" text. pd.Timestamp() accepts any of them.
DateLike = date | str


def parse_date_input(text):
    """Parse DD-MM-YYYY text to a date object, or None if invalid."""
    try:
        return datetime.strptime(text.strip(), DATE_FORMAT).date()
    except (ValueError, AttributeError):
        return None
