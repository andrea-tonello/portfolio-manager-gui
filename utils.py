import pandas as pd
import numpy as np
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from decimal import Decimal, ROUND_HALF_UP

def round_half_up(valore, decimal = "0.01"):
    if pd.isna(valore):
        return np.nan
    return float(Decimal(str(valore)).quantize(Decimal(decimal), rounding=ROUND_HALF_UP))


def broker_fee(broker: int, product: str, conv_rate: float = 1.0, trade_value: float = 0.0):

    # if EUR
    bg_etf_stock = 2.0
    
    upper_bound_fineco = min(19.0, round_half_up(trade_value * 0.0019))
    fineco = max(2.95, upper_bound_fineco)

    # if USD (BG Saxo-only)
    if conv_rate != 1.0:
        # Il controvalore è convertito con il tasso totale (quindi maggiorato di 0.25%),
        # Mentre la fee è convertita con il tasso "reale"
        conv_rate = conv_rate - conv_rate * 0.0025
        bg_etf_stock = round_half_up(1.0 * conv_rate, decimal="0.000001")

    fees = {
        "ETF":   {1: ("Fineco", fineco), 2: ("BG Saxo", bg_etf_stock)},
        "Stock": {1: ("Fineco", fineco), 2: ("BG Saxo", bg_etf_stock)},
        "Bond":  {1: ("Fineco", fineco), 2: ("BG Saxo", 7.0)},
    }

    broker_name, fee = fees.get(product, {}).get(broker, ("SIM non riconosciuto", 0))
    return broker_name, fee


def get_date(df):
    print("\nPer uscire (force exit): CTRL+C (l'operazione corrente non verrà aggiunta al report).")
    dt = input('\nInserisci data operazione GG-MM-AAAA ("t" per data odierna): ')
    if dt == "t":
        td = date.today()
        dt = td.strftime("%d-%m-%Y")

    lastdt = df["Data"].iloc[-1]
    num_date = datetime.strptime(dt, "%d-%m-%Y")
    num_lastdt = datetime.strptime(lastdt, "%d-%m-%Y")

    if num_date < num_lastdt:
        raise ValueError("La data inserita è precedente all'ultima registrata")
    
    return dt


def buy_asset(df, asset_rows, quantity, price, fee, date_str, product):
    
    date = datetime.strptime(date_str, "%d-%m-%Y")
    price_raw = price
    price_abs = abs(price)

    pmpc = 0
    current_qt = quantity

    # First ever data point for that ISIN
    if asset_rows.empty:                   
        pmpc = (price_abs * quantity + fee) / quantity

    # ISIN already logged
    else:         
        last_pmpc = asset_rows["PMPC Asset"].iloc[-1]
        last_remaining_qt = asset_rows["QT. Attuale Asset"].iloc[-1]

        old_cost = last_pmpc * last_remaining_qt
        new_cost = price_abs * quantity + fee
        current_qt = last_remaining_qt + quantity

        pmpc = ((old_cost + new_cost) / current_qt)

    importo_residuo = pmpc * current_qt

    fiscal_credit_iniziale = compute_backpack(df, date, as_of_index=len(df))
    fiscal_credit_aggiornato = fiscal_credit_iniziale

    # Minusvalenze da commissione ETF
    minusvalenza_comm = np.nan
    end_date = np.nan

    if product == "ETF":
        minusvalenza_comm = fee
        end_date = add_solar_years(date)
        fiscal_credit_aggiornato += minusvalenza_comm
        
    
    current_liq = float(df["Liquidita Attuale"].iloc[-1]) + (quantity * price_raw - fee)
    asset_value = float(df["Valore Titoli"].iloc[-1]) + (price_abs * current_qt)

    return {
        "Operazione": "buy",
        "QT. Attuale Asset": current_qt,
        "PMPC Asset": pmpc,
        "Imp. Residuo Asset": importo_residuo,
        "Costo Rilasciato": np.nan,
        "Plusv. Lorda": np.nan,
        "Minusv. Generata": minusvalenza_comm,
        "Scadenza": end_date,
        "Zainetto Fiscale": fiscal_credit_aggiornato,
        "Plusv. Imponibile": np.nan,
        "Imposta": np.nan,
        "Netto": np.nan,
        "Liquidita Attuale": current_liq,
        "Valore Titoli": asset_value,
        "NAV": current_liq + asset_value
    }


"""
Idea per gestire le scadenze delle minus:
 - compute_backpack: 
   - legge tutta la cronologia fino alla data di una nuova operazione, 
   - somma tutte le minusvalenze non ancora scadute e 
   - sottrae tutte le plusvalenze che le hanno già utilizzate.
"""

def add_solar_years(data_generazione):

    data_scadenza = data_generazione + relativedelta(years=4)
    end_date = datetime(data_scadenza.year, 12, 31)
    return end_date.strftime("%d-%m-%Y")


def compute_backpack(df, data_operazione, as_of_index=None):
    """
    Calcola lo zainetto disponibile alla data_operazione considerando
    l'ordine reale delle operazioni (se più operazioni nello stesso giorno
    si rispetta l'ordine di indice).
    - df: dataframe completo
    - data_operazione: datetime della data di riferimento
    - as_of_index: se fornito, considera solo le righe con index < as_of_index
      (utile se il dataframe contiene già la riga corrente e si vuole considerare
       solo la cronologia precedente).
    Ritorna float (credito residuo non negativo).
    """
    history = df.copy()
    history['Data_dt'] = pd.to_datetime(history['Data'], format="%d-%m-%Y")
    # consideriamo solo righe fino alla data_operazione inclusa
    history = history[history['Data_dt'] <= data_operazione].copy()
    if as_of_index is not None:
        history = history.loc[history.index < as_of_index]

    # ordiniamo per data e per indice per rispettare l'ordine reale
    history = history.sort_values(by=['Data_dt']).assign(_orig_index=history.index)
    history = history.sort_values(by=['Data_dt', '_orig_index'])

    # Lista di minus attive: ciascuna è dict {'amount', 'expiry'}
    active_minuses = []

    for _, r in history.iterrows():
        current_date = r['Data_dt']
        # rimuovo minus scadute rispetto alla data corrente
        active_minuses = [m for m in active_minuses if m['expiry'] >= current_date]

        # se la riga ha una minus generata, la aggiungo con la sua scadenza
        if pd.notna(r.get('Minusv. Generata')) and r['Minusv. Generata'] > 0:
            scad = r.get('Scadenza', np.nan)
            if pd.isna(scad):
                expiry_dt = current_date
            else:
                expiry_dt = pd.to_datetime(scad, format="%d-%m-%Y", errors='coerce')
            active_minuses.append({'amount': float(r['Minusv. Generata']), 'expiry': expiry_dt})

        # se la riga ha una plus lorda > 0, la uso per consumare il credito attivo (FIFO)
        if pd.notna(r.get('Plusv. Lorda')) and r['Plusv. Lorda'] > 0:
            to_consume = float(r['Plusv. Lorda'])
            i = 0
            while to_consume > 0 and i < len(active_minuses):
                avail = active_minuses[i]['amount']
                used = min(avail, to_consume)
                active_minuses[i]['amount'] -= used
                to_consume -= used
                if active_minuses[i]['amount'] == 0:
                    i += 1
            # ripulisci elementi a zero
            active_minuses = [m for m in active_minuses if m['amount'] > 0]

    # rimuovo eventuali minus scadute rispetto alla data_operazione
    active_minuses = [m for m in active_minuses if m['expiry'] >= data_operazione]
    total = sum(m['amount'] for m in active_minuses)
    return max(0.0, total)


def sell_asset(df, asset_rows, quantity, price, fee, date_str, product, tax_rate=0.26):
    
    if asset_rows.empty:
        raise ValueError("Nessun titolo da vendere: portafoglio vuoto")
    
    date = datetime.strptime(date_str, "%d-%m-%Y")
    
    last_pmpc = asset_rows["PMPC Asset"].iloc[-1]
    last_remaining_qt = asset_rows["QT. Attuale Asset"].iloc[-1]
    
    if quantity > last_remaining_qt:
        raise ValueError("Quantità venduta superiore a quella disponibile")

    importo_effettivo = quantity * price - fee
    costo_rilasciato = quantity * last_pmpc
    
    plusvalenza_lorda = importo_effettivo - costo_rilasciato
    
    fiscal_credit_iniziale = compute_backpack(df, date, as_of_index=len(df))
    fiscal_credit_aggiornato = fiscal_credit_iniziale
    plusvalenza_imponibile = 0
    minusvalenza_generata = 0
    minusvalenza_comm = np.nan
    imposta = 0
    end_date = np.nan

    if plusvalenza_lorda > 0:
        plusvalenza_da_compensare = plusvalenza_lorda
        if fiscal_credit_iniziale > 0 and product != "ETF":
            credito_utilizzato = min(plusvalenza_da_compensare, fiscal_credit_iniziale)
            plusvalenza_da_compensare -= credito_utilizzato
            fiscal_credit_aggiornato -= credito_utilizzato
        
        plusvalenza_imponibile = plusvalenza_da_compensare
        imposta = plusvalenza_imponibile * tax_rate
    else:
        minusvalenza_generata = abs(plusvalenza_lorda)
        fiscal_credit_aggiornato += minusvalenza_generata
        end_date = add_solar_years(date)

    plusvalenza_netta = plusvalenza_lorda - imposta

    current_qt = last_remaining_qt - quantity
    importo_residuo = last_pmpc * current_qt
    pmpc_residuo = last_pmpc if current_qt > 0 else 0.0

    # Minusvalenze da commissione ETF
    if product == "ETF":
        minusvalenza_comm = fee
        fiscal_credit_aggiornato += minusvalenza_comm
        end_date = add_solar_years(date)
        minusvalenza_generata += minusvalenza_comm

    current_liq = float(df["Liquidita Attuale"].iloc[-1]) + importo_effettivo - imposta
    asset_value = float(df["Valore Titoli"].iloc[-1]) - (costo_rilasciato)

    return {
        "Operazione": "sell",
        "QT. Attuale Asset": current_qt,
        "PMPC Asset": pmpc_residuo,
        "Imp. Residuo Asset": importo_residuo,
        "Costo Rilasciato": costo_rilasciato,
        "Plusv. Lorda": plusvalenza_lorda if plusvalenza_lorda > 0 else 0,
        "Minusv. Generata": np.nan if minusvalenza_generata == 0 else minusvalenza_generata,
        "Scadenza": end_date,
        "Zainetto Fiscale": fiscal_credit_aggiornato,
        "Plusv. Imponibile": plusvalenza_imponibile if plusvalenza_lorda > 0 else np.nan,
        "Imposta": imposta,
        "Netto": plusvalenza_netta if plusvalenza_lorda > 0 else plusvalenza_lorda,
        "Liquidita Attuale": current_liq,
        "Valore Titoli": asset_value,
        "NAV": current_liq + asset_value
    }


