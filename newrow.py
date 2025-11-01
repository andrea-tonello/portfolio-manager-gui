import pandas as pd
import numpy as np
from datetime import datetime

import utils.operations_account as aop
from utils.other_utils import round_half_up
from utils.fetch_utils import fetch_name


def newrow_cash(df, date, broker, cash, op_type, product, ticker, name):

    current_liq = float(df["Liquidita Attuale"].iloc[-1]) + cash

    if op_type in ["Deposito", "Prelievo"]:
        historic_liq = float(df["Liq. Storica Immessa"].iloc[-1]) + cash
    else:
        historic_liq = float(df["Liq. Storica Immessa"].iloc[-1])

    yahoo_date = datetime.strptime(date, "%d-%m-%Y")
    positions = aop.get_asset_value(df, ref_date=yahoo_date)
    asset_value = sum(pos["value"] for pos in positions)

    new_row = pd.DataFrame({
        "Data": [date],
        "Conto": [broker],
        "Operazione": [op_type],
        "Prodotto": [product],
        "Ticker": [ticker],
        "Nome Asset": [name],
        "TER": [np.nan],
        "Valuta": ["EUR"],
        "Tasso di Conv.": [np.nan],
        "QT. Scambio": [np.nan],
        "Prezzo": [np.nan],
        "Prezzo EUR": [np.nan],
        "Imp. Nominale Operaz.": [cash],
        "Commissioni": [np.nan],
        "QT. Attuale": [np.nan],
        "PMC": [np.nan],
        "Imp. Residuo Asset": [np.nan],
        "Imp. Effettivo Operaz.": [cash],
        "Costo Rilasciato": [np.nan],
        "Plusv. Lorda": [np.nan],
        "Minusv. Generata": [np.nan],
        "Scadenza": [np.nan],
        "Zainetto Fiscale": [float(df["Zainetto Fiscale"].iloc[-1])],
        "Plusv. Imponibile": [np.nan],
        "Imposta": [np.nan],
        "P&L": [cash if op_type in ["Dividendo", "Imposta"] else np.nan],
        "Liquidita Attuale": [round_half_up(current_liq)],
        "Valore Titoli": [round_half_up(asset_value)],
        "NAV": [round_half_up(asset_value + current_liq)],
        "Liq. Storica Immessa": [ round_half_up(historic_liq) ]
    })

    df = pd.concat([df, new_row], ignore_index=True)

    return df


def newrow_etf_stock(df, date, broker, currency, product, ticker, quantity, price, conv_rate, ter, fee, buy):

    # BUY:  price -, buy=True
    # SELL: price +, buy=False

    name = fetch_name(ticker)
    asset_rows = df[df["Ticker"] == ticker]
    asset_rows = asset_rows[asset_rows["Operazione"].isin(["Acquisto", "Vendita"])]     # non passare righe con dividendi

    if buy:
        results = aop.buy_asset(df, asset_rows, quantity, price, conv_rate, fee, date, product, ticker)

    else:
        results = aop.sell_asset(df, asset_rows, quantity, price, conv_rate, fee, date, product, ticker)

    price_eur = price / conv_rate

    new_row = pd.DataFrame({
        "Data": [date],
        "Conto": [broker],
        "Operazione": [results["Operazione"]],
        "Prodotto": [product],
        "Ticker": [ticker],
        "Nome Asset": [name],
        "TER": [ter],
        "Valuta": [currency],
        "Tasso di Conv.": [f"{conv_rate:.6f}"],
        "QT. Scambio": [f"+{quantity}" if buy else f"-{quantity}"],
        "Prezzo": [round_half_up(price, decimal="0.0001")],
        "Prezzo EUR": [round_half_up(price_eur, decimal="0.0001")],
        "Imp. Nominale Operaz.": [round_half_up(round_half_up(quantity * price) / conv_rate)],
        "Commissioni": [round_half_up(fee)],
        "QT. Attuale": [results["QT. Attuale"]],
        "PMC": [round_half_up(results["PMC"], decimal="0.0001")],
        "Imp. Residuo Asset": [round_half_up(results["Imp. Residuo Asset"])],
        "Imp. Effettivo Operaz.": [round_half_up(round_half_up(quantity * price) / conv_rate) - round_half_up(fee)],
        "Costo Rilasciato": [round_half_up(results["Costo Rilasciato"])],
        "Plusv. Lorda": [round_half_up(results["Plusv. Lorda"])],
        "Minusv. Generata": [round_half_up(results["Minusv. Generata"])],
        "Scadenza": [results["Scadenza"]],
        "Zainetto Fiscale": [round_half_up(results["Zainetto Fiscale"])],
        "Plusv. Imponibile": [round_half_up(results["Plusv. Imponibile"])],
        "Imposta": [round_half_up(results["Imposta"])],
        "P&L": [round_half_up(results["P&L"])],
        "Liquidita Attuale": [round_half_up(results["Liquidita Attuale"])],
        "Valore Titoli": [round_half_up(results["Valore Titoli"])],
        "NAV": [round_half_up(results["NAV"])],
        "Liq. Storica Immessa": [ round_half_up(float(df["Liq. Storica Immessa"].iloc[-1]))],
    })

    df = pd.concat([df, new_row], ignore_index=True)

    return df