import pandas as pd
import numpy as np
import fetch_data as figi
from utils import buy_asset, sell_asset


def newrow_cash(df, date, cash, broker):
    op_type = "deposit" if cash > 0 else "withdrawal"
    net_final = cash

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
        "Imp. Nominale Operaz.": [cash],
        "Commissioni": [np.nan],
        "QT. Attuale Asset": [np.nan],
        "Imp. Residuo Asset": [np.nan],
        "PMPC Asset": [np.nan],
        "Imp. Effettivo Operaz.": [cash],
        "Costo Rilasciato": [np.nan],
        "Plusv. Lorda": [np.nan],
        "Minusv. Generata": [np.nan],
        "Scadenza": [np.nan],
        "Zainetto Fiscale": [float(df["Zainetto Fiscale"].iloc[-1])],
        "Plusv. Imponibile": [np.nan],
        "Imposta": [np.nan],
        "Netto": [net_final],
        "Liquidita Attuale": [ float(df["Liquidita Attuale"].iloc[-1]) + net_final ],
        "Valore Titoli": [float(df["Valore Titoli"].iloc[-1])],
        "NAV": [ float(df["NAV"].iloc[-1]) + net_final ],
        "Liq. Storica Immessa": [ float(df["Liq. Storica Immessa"].iloc[-1]) + net_final ]
    })

    df = pd.concat([df, new_row], ignore_index=True)

    return df


def newrow_etf(df, date, isin, quantity, price, ter, broker, fee, buy):

    # BUY:  price -, buy=True
    # SELL: price +, buy=False

    response = figi.lookup_by_isin(isin)
    name = figi.parse_response(response)["name"]
    asset_rows = df[df["ISIN"] == isin]

    if buy:
        results = buy_asset(df, asset_rows, quantity, price, fee)
    else:
        results = sell_asset(df, asset_rows, quantity, price, fee, date)

    new_row = pd.DataFrame({
        "Data": [date],
        "Operazione": [results["Operazione"]],
        "SIM": [broker],
        "Prodotto": ["ETF"],
        "ISIN": [isin],
        "Asset Name": [name],
        "TER": [ter],
        "Valuta": ["EUR"],
        "QT. Scambio": [quantity],
        "Prezzo": [price],
        "Imp. Nominale Operaz.": [(quantity * price)],
        "Commissioni": [fee],
        "QT. Attuale Asset": [results["QT. Attuale Asset"]],
        "Imp. Residuo Asset": [results["Imp. Residuo Asset"]],
        "PMPC Asset": [results["PMPC Asset"]],
        "Imp. Effettivo Operaz.": [(quantity * price - fee)],
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