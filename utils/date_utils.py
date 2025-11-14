from datetime import date, datetime
from dateutil.relativedelta import relativedelta
import pandas as pd

def get_date(df=None):
    
    try:
        dt = input('    > ')
        td = date.today()

        if dt in ["t", "T"]:
            dt = td.strftime("%d-%m-%Y")

        ref_date = datetime.strptime(dt, "%d-%m-%Y")
        if ref_date.date() > td:
            raise ValueError("Impossibile inserire date future.")

        if df is not None and not df.empty:
            lastdt = df["Data"].iloc[-1]
            num_lastdt = datetime.strptime(lastdt, "%d-%m-%Y")
            if ref_date < num_lastdt:
                raise ValueError("La data inserita è precedente all'ultima registrata")
        
        return dt, ref_date
    
    except ValueError as e:
        print("\nERRORE NELLA DATA:")
        print(f"{e}\n")
        input("Premi Invio per tornare al Menu Principale...")
        raise KeyboardInterrupt
    

def get_pf_date(df_copy, dt, ref_date):

    ### CALCOLO LIQUIDITA PER DATA X: 
    # SE DATA X È PRESENTE NEL df USA QUELLA 
    # ALTRIMENTI PESCA LA PRIMA DATA PRECEDENTE DISPONIBILE
    df_copy["Data"] = pd.to_datetime(df_copy["Data"], dayfirst=True, errors="coerce")
    df_valid = df_copy[df_copy["Data"] <= ref_date]
    if df_valid.empty:
        raise ValueError(f"Nessuna data disponibile nel DataFrame precedente a {dt}")
    try:
        first_date = df_valid["Data"][1]
    except KeyError:
        first_date = None
    return df_valid, first_date
        


def add_solar_years(data_generazione):

    data_scadenza = data_generazione + relativedelta(years=4)
    end_date = datetime(data_scadenza.year, 12, 31)
    return end_date.strftime("%d-%m-%Y")