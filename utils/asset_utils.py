import pandas as pd
import numpy as np
from datetime import datetime
import yfinance as yf
import warnings

from utils.other_utils import round_half_up
from utils.date_utils import add_solar_years
from utils.fetch_utils import fetch_exchange_rate

warnings.simplefilter(action='ignore', category=Warning)


def broker_fee(broker: int, product: str, conv_rate: float = 1.0, trade_value: float = 0.0):

    # if EUR
    bg_etf_stock = 2.0
    
    upper_bound_fineco = min(19.0, round_half_up(trade_value * 0.0019))
    fineco = max(2.95, upper_bound_fineco)

    # if USD (BG Saxo-only)
    if conv_rate != 1.0:
        bg_etf_stock = round_half_up(1.0 / conv_rate, decimal="0.000001")

    fees = {
        "ETF":   {1: ("Fineco", fineco), 2: ("BG Saxo", bg_etf_stock)},
        "Azioni": {1: ("Fineco", fineco), 2: ("BG Saxo", bg_etf_stock)},
        "Obbligazioni":  {1: ("Fineco", fineco), 2: ("BG Saxo", 7.0)},
    }

    broker_name, fee = fees.get(product, {}).get(broker, ("SIM non riconosciuto", 0))
    return broker_name, fee


def get_asset_value(df, current_ticker=None, ref_date=None):

    df_copy = df.copy()
    df_copy["Data"] = pd.to_datetime(df_copy["Data"], format="%d-%m-%Y")
    df_filtered = df_copy[df_copy["Data"] <= ref_date]

    # Rimuove le righe dove la colonna Ticker non ha un valore ed il Ticker corrente
    df_filtered = df_filtered.dropna(subset=['Ticker'])
    if current_ticker:
        df_filtered = df_filtered[df_filtered["Ticker"] != current_ticker]

    # Tieni solo le righe con buy e sell (per evitare ticker su dividendi)
    df_filtered = df_filtered[df_filtered["Operazione"].isin(["Acquisto", "Vendita"])]

    # Prendi l'ultima riga per ogni asset unico
    total_assets = df_filtered.groupby("Ticker").last().reset_index()

    # Filtra solo quelli con quantità > 0
    total_assets = total_assets.loc[total_assets["QT. Attuale"] > 0, ["Ticker", "QT. Attuale", "Valuta"]]

    if total_assets.empty:
        return []

    # Converte in lista di dict
    positions = []
    tickers = []
    for _, row in total_assets.iterrows():
        positions.append({
            "ticker": row["Ticker"],
            "quantity": row["QT. Attuale"],
            "exchange_rate": 1.0 if row["Valuta"] == "EUR" else fetch_exchange_rate(ref_date.strftime("%Y-%m-%d")),
            "price": np.nan,
            "value": np.nan
        })
        tickers.append(row["Ticker"])

    # Scarica dati da qualche giorno prima per gestire weekend/festività
    start_date = pd.to_datetime(ref_date) - pd.Timedelta(days=10)
    end_date = pd.to_datetime(ref_date) + pd.Timedelta(days=1)
    
    print("\nAggiornamento del valore dei titoli in possesso da Yahoo Finance...")
    data = yf.download(tickers, start=start_date, end=end_date)["Close"]
    
    # Prendi l'ultima riga disponibile fino a ref_date. 
    # Se però questa riga contiene una cella nan, scartala
    data_ref = (
        data.loc[data.index <= pd.to_datetime(ref_date)]  # fino a ref_date
            .dropna(how="any")                            # elimina righe con almeno un NaN
            .iloc[-1]                                     # prendi l’ultima riga valida
    )

    for item in positions:
        ticker = item["ticker"]
        price = data_ref[ticker] * item["exchange_rate"]
        item["price"] = price
        item["value"] = item["quantity"] * price

    return positions



def buy_asset(df, asset_rows, quantity, price, conv_rate, fee, date_str, product, ticker):
    
    date = datetime.strptime(date_str, "%d-%m-%Y")
    price_raw = price / conv_rate
    price_abs = abs(price) / conv_rate

    pmpc = 0
    current_qt = quantity

    # First ever data point for that ISIN
    if asset_rows.empty:                   
        pmpc = (price_abs * quantity + fee) / quantity

    # Ticker already logged
    else:         
        last_pmpc = asset_rows["PMC"].iloc[-1]
        last_remaining_qt = asset_rows["QT. Attuale"].iloc[-1]

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

    current_liq = float(df["Liquidita Attuale"].iloc[-1]) + (round_half_up((round_half_up(quantity * price) / conv_rate)) - fee)

    yahoo_date = datetime.strptime(date_str, "%d-%m-%Y")
    positions = get_asset_value(df, current_ticker=ticker, ref_date=yahoo_date)
    asset_value = sum(pos["value"] for pos in positions) + (current_qt * price_abs)

    return {
        "Operazione": "Acquisto",
        "QT. Attuale": current_qt,
        "PMC": pmpc,
        "Imp. Residuo Asset": importo_residuo,
        "Costo Rilasciato": np.nan,
        "Plusv. Lorda": np.nan,
        "Minusv. Generata": minusvalenza_comm,
        "Scadenza": end_date,
        "Zainetto Fiscale": fiscal_credit_aggiornato,
        "Plusv. Imponibile": np.nan,
        "Imposta": np.nan,
        "P&L": np.nan,
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


def sell_asset(df, asset_rows, quantity, price, conv_rate, fee, date_str, product, ticker, tax_rate=0.26):
    
    if asset_rows.empty:
        raise ValueError("Nessun titolo da vendere: portafoglio vuoto")
    
    date = datetime.strptime(date_str, "%d-%m-%Y")
    
    last_pmpc = asset_rows["PMC"].iloc[-1]
    last_remaining_qt = asset_rows["QT. Attuale"].iloc[-1]
    
    if quantity > last_remaining_qt:
        raise ValueError("Quantità venduta superiore a quella disponibile")

    importo_effettivo = ((quantity * price) / conv_rate) - fee                                          # per calcolo interno
    importo_effettivo_arrotondato = round_half_up((quantity * price) / conv_rate - round_half_up(fee))  # per calcolo liquidità
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

    current_liq = float(df["Liquidita Attuale"].iloc[-1]) + importo_effettivo_arrotondato - imposta

    yahoo_date = datetime.strptime(date_str, "%d-%m-%Y")
    positions = get_asset_value(df, current_ticker=ticker, ref_date=yahoo_date)

    asset_value = sum(pos["value"] for pos in positions) + (current_qt * price)

    return {
        "Operazione": "Vendita",
        "QT. Attuale": current_qt,
        "PMC": pmpc_residuo,
        "Imp. Residuo Asset": importo_residuo,
        "Costo Rilasciato": costo_rilasciato,
        "Plusv. Lorda": plusvalenza_lorda if plusvalenza_lorda > 0 else np.nan,
        "Minusv. Generata": np.nan if minusvalenza_generata == 0 else minusvalenza_generata,
        "Scadenza": end_date,
        "Zainetto Fiscale": fiscal_credit_aggiornato,
        "Plusv. Imponibile": plusvalenza_imponibile if plusvalenza_lorda > 0 else np.nan,
        "Imposta": imposta,
        "P&L": plusvalenza_netta if plusvalenza_lorda > 0 else plusvalenza_lorda,
        "Liquidita Attuale": current_liq,
        "Valore Titoli": asset_value,
        "NAV": current_liq + asset_value
    }


