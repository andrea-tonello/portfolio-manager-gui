"""
Centralised column definitions for internal DataFrame storage.

Internal storage uses English column names.
Export uses locale-specific headers resolved via the translator ("columns" keys).
"""

# Every column of an account CSV, in file order. The name shown for each (in
# the Transactions table and as the export header) is "columns.<column>" in the
# locale files, e.g. "columns.abp" -> "PMC"; glossary_columns_<language>.txt explains them.
COLUMNS = [
    "date", "account", "operation", "product", "ticker", "asset_name", "ter", "curr", "conv_rate",
    "qt_exch", "price", "price_eur", "nominal_amount", "fee", "qt_held", "abp", "residual_amount",
    "effective_amount", "released_amount", "gross_gain", "generated_loss", "expiry", "carryforward",
    "pending_fees", "taxable_gain", "tax_bracket", "tax", "pl", "cash_held", "assets_value", "nav",
    "committed_cash",
]

# Maps internal English operation values → locale keys for export.
OPERATION_LOCALE_KEYS = {
    "Deposit": "values.op_deposit",
    "Withdrawal": "values.op_withdrawal",
    "Buy": "values.op_buy",
    "Sell": "values.op_sell",
    "Dividend": "values.op_dividend",
    "Tax": "values.op_tax",
    "Split": "values.op_split",
}

# Maps internal English product values → locale keys for export.
PRODUCT_LOCALE_KEYS = {
    "Cash": "values.prod_cash",
    "Stock": "values.prod_stock",
    "ETF-S": "values.prod_stock_etf",
    "ETF-M": "values.prod_mm_etf",
    "ETF-B": "values.prod_bond_etf",
    "Dividend": "values.prod_dividend",
    "Tax": "values.prod_tax",
}


def export_headers(translator):
    """Return dict mapping internal column name → locale display name."""
    return {col: translator.get(f"columns.{col}").strip() for col in COLUMNS}


def localized_value_maps(translator):
    """Return, for each column whose values are stored in English, how to show them in the user's language.

    Example in Italian: {"operation": {"Buy": "Acquisto", ...}, "product": {"Stock": "Azioni", ...}}.
    Values not listed (e.g. a charge's own description) are shown as stored.
    """
    return {
        "operation": {k: translator.get(v).strip() for k, v in OPERATION_LOCALE_KEYS.items()},
        "product": {k: translator.get(v).strip() for k, v in PRODUCT_LOCALE_KEYS.items()},
    }


def _translate_values(df, translator):
    """Translate operation and product column values to locale strings."""
    for col, mapping in localized_value_maps(translator).items():
        if col in df.columns:
            df[col] = df[col].map(lambda x, m=mapping: m.get(x, x))
    return df


def rename_for_export(df, translator):
    """Return a copy of *df* with columns and values translated for export."""
    out = df.copy()
    _translate_values(out, translator)
    mapping = export_headers(translator)
    return out.rename(columns=mapping)
