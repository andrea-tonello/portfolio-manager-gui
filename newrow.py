import pandas as pd
import numpy as np

import utils.account as aop
from utils.other_utils import round_half_up
from utils.fetch_utils import fetch_name


# All 28 DataFrame columns defaulting to np.nan.
# Callers use _base_row() then .update() only the fields they need.
_COLUMNS = [
    "Data", "Conto", "Operazione", "Prodotto", "Ticker", "Nome Asset",
    "TER", "Valuta", "Tasso di Conv.", "QT. Scambio", "Prezzo", "Prezzo EUR",
    "Imp. Nominale Operaz.", "Commissioni", "QT. Attuale", "PMC",
    "Imp. Residuo Asset", "Imp. Effettivo Operaz.", "Costo Rilasciato",
    "Plusv. Lorda", "Minusv. Generata", "Scadenza", "Zainetto Fiscale",
    "Plusv. Imponibile", "Imposta", "P&L", "Liquidita Attuale",
    "Valore Titoli", "NAV", "Liq. Impegnata",
]


def _base_row():
    return {col: np.nan for col in _COLUMNS}


def _append_row(df, row):
    new_row = pd.DataFrame({k: [v] for k, v in row.items()})
    return pd.concat([df, new_row], ignore_index=True)


def newrow_cash(translator, df, date, ref_date, broker, cash, op_type, product, ticker, name):

    current_liq = float(df["Liquidita Attuale"].iloc[-1]) + cash

    if op_type in ["Deposito", "Prelievo"]:
        historic_liq = float(df["Liq. Impegnata"].iloc[-1]) + cash
    else:
        historic_liq = float(df["Liq. Impegnata"].iloc[-1])

    positions = aop.get_asset_value(translator, df, ref_date=ref_date)
    asset_value = sum(pos["value"] for pos in positions)

    row = _base_row()
    row.update({
        "Data": date,
        "Conto": broker,
        "Operazione": op_type,
        "Prodotto": product,
        "Ticker": ticker,
        "Nome Asset": name,
        "Valuta": "EUR",
        "Imp. Nominale Operaz.": cash,
        "Imp. Effettivo Operaz.": cash,
        "Zainetto Fiscale": float(df["Zainetto Fiscale"].iloc[-1]),
        "P&L": cash if op_type in ["Dividendo", "Imposta"] else np.nan,
        "Liquidita Attuale": round_half_up(current_liq),
        "Valore Titoli": round_half_up(asset_value),
        "NAV": round_half_up(asset_value + current_liq),
        "Liq. Impegnata": round_half_up(historic_liq),
    })

    return _append_row(df, row)


def newrow_etf_stock(translator, df, date, ref_date, broker, currency, product, ticker, quantity, price, conv_rate, ter, fee, buy, asset_name_override=None):

    # BUY:  price -, buy=True
    # SELL: price +, buy=False

    name = asset_name_override if asset_name_override else fetch_name(ticker)
    asset_rows = df[df["Ticker"] == ticker]
    asset_rows = asset_rows[asset_rows["Operazione"].isin(["Acquisto", "Vendita"])]

    if buy:
        results = aop.buy_asset(translator, df, asset_rows, quantity, price, conv_rate, fee, ref_date, product, ticker)
    else:
        results = aop.sell_asset(translator, df, asset_rows, quantity, price, conv_rate, fee, ref_date, product, ticker)

    price_eur = price / conv_rate

    row = _base_row()
    row.update({
        "Data": date,
        "Conto": broker,
        "Operazione": results["Operazione"],
        "Prodotto": product,
        "Ticker": ticker,
        "Nome Asset": name,
        "TER": ter,
        "Valuta": currency,
        "Tasso di Conv.": f"{conv_rate:.6f}",
        "QT. Scambio": f"+{quantity}" if buy else f"-{quantity}",
        "Prezzo": round_half_up(price, decimal="0.0001"),
        "Prezzo EUR": round_half_up(price_eur, decimal="0.0001"),
        "Imp. Nominale Operaz.": round_half_up(round_half_up(quantity * price) / conv_rate),
        "Commissioni": round_half_up(fee),
        "QT. Attuale": results["QT. Attuale"],
        "PMC": round_half_up(results["PMC"], decimal="0.0001"),
        "Imp. Residuo Asset": round_half_up(results["Imp. Residuo Asset"]),
        "Imp. Effettivo Operaz.": round_half_up(round_half_up(quantity * price) / conv_rate) - round_half_up(fee),
        "Costo Rilasciato": round_half_up(results["Costo Rilasciato"]),
        "Plusv. Lorda": round_half_up(results["Plusv. Lorda"]),
        "Minusv. Generata": round_half_up(results["Minusv. Generata"]),
        "Scadenza": results["Scadenza"],
        "Zainetto Fiscale": round_half_up(results["Zainetto Fiscale"]),
        "Plusv. Imponibile": round_half_up(results["Plusv. Imponibile"]),
        "Imposta": round_half_up(results["Imposta"]),
        "P&L": round_half_up(results["P&L"]),
        "Liquidita Attuale": round_half_up(results["Liquidita Attuale"]),
        "Valore Titoli": round_half_up(results["Valore Titoli"]),
        "NAV": round_half_up(results["NAV"]),
        "Liq. Impegnata": round_half_up(float(df["Liq. Impegnata"].iloc[-1])),
    })

    return _append_row(df, row)
