from datetime import datetime

from utils.constants import DATE_FORMAT


def parse_date_input(text):
    """Parse DD-MM-YYYY text to a date object, or None if invalid."""
    try:
        return datetime.strptime(text.strip(), DATE_FORMAT).date()
    except (ValueError, AttributeError):
        return None
