from datetime import date, datetime
from dateutil.relativedelta import relativedelta
import pandas as pd

from utils.constants import DATE_FORMAT

def get_date(translator, df=None):
    try:
        dt = input('    > ')
        td = date.today()

        if dt in ["t", "T"]:
            dt = td.strftime(DATE_FORMAT)

        ref_date = datetime.strptime(dt, DATE_FORMAT)
        if ref_date.date() > td:
            raise ValueError(translator.get("dates.error_future"))

        if df is not None and not df.empty:
            lastdt = df["Data"].iloc[-1]
            num_lastdt = datetime.strptime(lastdt, DATE_FORMAT)
            if ref_date < num_lastdt:
                raise ValueError(translator.get("dates.error_sequential"))
        
        return dt, ref_date
    
    except ValueError as e:
        print(translator.get("dates.error"))
        print(f"{e}")
        input(translator.get("redirect.continue_home"))
        raise KeyboardInterrupt
    

def get_pf_date(translator, df_copy, dt, ref_date):
    ### CALCOLO LIQUIDITA PER DATA X: 
    # SE DATA X È PRESENTE NEL df USA QUELLA 
    # ALTRIMENTI PESCA LA PRIMA DATA PRECEDENTE DISPONIBILE
    df_copy["Data"] = pd.to_datetime(df_copy["Data"], dayfirst=True, errors="coerce")
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