from datetime import datetime
from dateutil.relativedelta import relativedelta
import pandas as pd

from utils.constants import DATE_FORMAT


def get_pf_date(translator, df_copy, dt, ref_date):
    df_copy["Data"] = pd.to_datetime(df_copy["Data"], dayfirst=True, errors="coerce")
    ref_date = pd.Timestamp(ref_date)
    df_valid = df_copy[df_copy["Data"] <= ref_date]
    if df_valid.empty:
        raise ValueError(translator.get("dates.error_nodates", dt=dt))
    try:
        first_date = df_valid["Data"][1]
    except KeyError:
        first_date = None
    return df_valid, first_date


def add_solar_years(data_generazione):
    data_scadenza = data_generazione + relativedelta(years=4)
    end_date = datetime(data_scadenza.year, 12, 31)
    return end_date.strftime(DATE_FORMAT)
