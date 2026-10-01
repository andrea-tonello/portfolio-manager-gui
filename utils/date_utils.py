from datetime import datetime
from dateutil.relativedelta import relativedelta
import pandas as pd

from domain.errors import ValidationError
from utils.constants import DATE_FORMAT


def parse_date_input(text):
    """Parse DD-MM-YYYY text to a date object, or None if invalid."""
    try:
        return datetime.strptime(text.strip(), DATE_FORMAT).date()
    except (ValueError, AttributeError):
        return None


def get_pf_date(df_copy, dt, ref_date):
    df_copy["date"] = pd.to_datetime(df_copy["date"], dayfirst=True, errors="coerce")
    ref_date = pd.Timestamp(ref_date)
    df_valid = df_copy[df_copy["date"] <= ref_date]
    if df_valid.empty:
        raise ValidationError("misc_errors.nodates", dt=dt)
    try:
        first_date = df_valid["date"][1]
    except KeyError:
        first_date = None
    return df_valid, first_date


def add_solar_years(loss_date):
    four_years_later = loss_date + relativedelta(years=4)
    expiry = datetime(four_years_later.year, 12, 31)
    return expiry.strftime(DATE_FORMAT)
