import pandas as pd
import numpy as np
import fetch_data as figi
from utils import buy_asset, sell_asset, round_half_up

def fancy_df(df):

    df_fancy = df.copy()
    exclude_cols = ["Data", "Operazione", "SIM", "Prodotto",
                    "ISIN", "Asset Name", "TER", "Valuta",
                    "QT. Scambio", "Prezzo", "Prezzo EUR"]
    
    cols_to_round = df_fancy.columns.difference(exclude_cols)
    df_fancy[cols_to_round] = df_fancy[cols_to_round].apply(lambda col: col.map(round_half_up))
    
    return df_fancy


def newrow_cash(df, date, cash, broker):
    op_type = "deposit" if cash > 0 else "withdrawal"

    new_row = pd.DataFrame({
        "Data": [date],
        "Operazione": [op_type],
        "SIM": [broker],
        "Prodotto": [np.nan],
        "ISIN": [np.nan],
        "Asset Name": [np.nan],
        "TER": [np.nan],
        "Valuta": ["EUR"],
        "QT. Scambio": [np.nan],
        "Prezzo": [np.nan],
        "Prezzo EUR": [np.nan],
        "Imp. Nominale Operaz.": [cash],
        "Commissioni": [np.nan],
        "QT. Attuale Asset": [np.nan],
        "PMPC Asset": [np.nan],
        "Imp. Residuo Asset": [np.nan],
        "Imp. Effettivo Operaz.": [cash],
        "Costo Rilasciato": [np.nan],
        "Plusv. Lorda": [np.nan],
        "Minusv. Generata": [np.nan],
        "Scadenza": [np.nan],
        "Zainetto Fiscale": [float(df["Zainetto Fiscale"].iloc[-1])],
        "Plusv. Imponibile": [np.nan],
        "Imposta": [np.nan],
        "Netto": [np.nan],
        "Liquidita Attuale": [ float(df["Liquidita Attuale"].iloc[-1]) + cash ],
        "Valore Titoli": [float(df["Valore Titoli"].iloc[-1])],
        "NAV": [ float(df["NAV"].iloc[-1]) + cash ],
        "Liq. Storica Immessa": [ float(df["Liq. Storica Immessa"].iloc[-1]) + cash ]
    })

    df = pd.concat([df, new_row], ignore_index=True)

    return df


def newrow_etf_stock(df, date, currency, product, isin, quantity, price_og, price, ter, broker, fee, buy):

    # BUY:  price -, buy=True
    # SELL: price +, buy=False

    response = figi.lookup_by_isin(isin)
    name = figi.parse_response(response)["name"]
    asset_rows = df[df["ISIN"] == isin]

    if buy:
        results = buy_asset(df, asset_rows, quantity, price, fee, date, product)
    else:
        results = sell_asset(df, asset_rows, quantity, price, fee, date, product)

    new_row = pd.DataFrame({
        "Data": [date],
        "Operazione": [results["Operazione"]],
        "SIM": [broker],
        "Prodotto": [product],
        "ISIN": [isin],
        "Asset Name": [name],
        "TER": [ter],
        "Valuta": [currency],
        "QT. Scambio": [f"+{quantity}" if buy else f"-{quantity}"],
        "Prezzo": [round_half_up(price_og, decimal="0.0001")],
        "Prezzo EUR": [round_half_up(price, decimal="0.0001")],
        "Imp. Nominale Operaz.": [quantity * price],
        "Commissioni": [fee],
        "QT. Attuale Asset": [results["QT. Attuale Asset"]],
        "PMPC Asset": [results["PMPC Asset"]],
        "Imp. Residuo Asset": [results["Imp. Residuo Asset"]],
        "Imp. Effettivo Operaz.": [quantity * price - fee],
        "Costo Rilasciato": [results["Costo Rilasciato"]],
        "Plusv. Lorda": [results["Plusv. Lorda"]],
        "Minusv. Generata": [results["Minusv. Generata"]],
        "Scadenza": [results["Scadenza"]],
        "Zainetto Fiscale": [results["Zainetto Fiscale"]],
        "Plusv. Imponibile": [results["Plusv. Imponibile"]],
        "Imposta": [results["Imposta"]],
        "Netto": [results["Netto"]],
        "Liquidita Attuale": [results["Liquidita Attuale"]],
        "Valore Titoli": [results["Valore Titoli"]],
        "NAV": [results["NAV"]],
        "Liq. Storica Immessa": [ float(df["Liq. Storica Immessa"].iloc[-1])],
    })

    df = pd.concat([df, new_row], ignore_index=True)

    return df

"""
Esempio su plusvalenza e fee:
  Acquisto 100 azioni a 10 € = 1.000 €
  fee acquisto = 5 €
  -> Costo totale di carico = 1.005 €
  Rivendo a 12 € = 1.200 €
  fee vendita = 5 €
  Incasso netto = 1.195 €

Plusvalenza imponibile = 1.195 - 1.005 = 190 €
L'imposta sostitutiva del 26% si applica quindi su 190 €, non sui 200 € “lordi”.

Calcolo della Minusvalenza
  Acquisto 100 azioni a 10 € = 1.000 €
  fee acquisto = 5 €
  -> Costo totale di carico = 1.005 €
  Rivendo a 8 € = 800 €
  fee vendita = 5 €
  Incasso netto = 795 €

Minusvalenza = Incasso netto - Costo totale di carico
Minusvalenza = 795 € - 1.005 € = -210 €


La normativa italiana prevede che il prezzo medio ponderato di carico (PMPC) 
si calcoli comprensivo delle fee di acquisto e che anche il ricavo di vendita 
si consideri al netto delle fee di vendita.
"""