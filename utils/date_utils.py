from datetime import date, datetime
from dateutil.relativedelta import relativedelta

def get_date(df, sequential_only=True):
    try:
        dt = input('  - Data operazione GG-MM-AAAA ("t" per data odierna) > ')
        td = date.today()

        if dt == "t":
            dt = td.strftime("%d-%m-%Y")

        lastdt = df["Data"].iloc[-1]
        num_date = datetime.strptime(dt, "%d-%m-%Y")
        num_lastdt = datetime.strptime(lastdt, "%d-%m-%Y")

        if num_date.date() > td:
            raise ValueError("Impossibile inserire date future.")

        if sequential_only and num_date < num_lastdt:
            raise ValueError("La data inserita è precedente all'ultima registrata")
        
        return dt
    
    except ValueError as e:
        print("\nERRORE NELLA DATA:")
        print(f"{e}\n")
        input("Premi Invio per tornare al Menu Principale...")
        raise KeyboardInterrupt
    

def add_solar_years(data_generazione):

    data_scadenza = data_generazione + relativedelta(years=4)
    end_date = datetime(data_scadenza.year, 12, 31)
    return end_date.strftime("%d-%m-%Y")