"""
Centralised column definitions for internal DataFrame storage.

Internal storage uses English column names.
Export uses locale-specific headers resolved via the translator (glossary keys).
"""

# Every column of an account CSV, in file order, with the glossary key of the
# name shown for it (in the Transactions table and as the export header).
COLUMN_TITLE_KEYS = {
    "date": "glossary.page_1.date_title",
    "account": "glossary.page_1.account_title",
    "operation": "glossary.page_1.operation_title",
    "product": "glossary.page_1.product_title",
    "ticker": "glossary.page_1.ticker_title",
    "asset_name": "glossary.page_1.asset_name_title",
    "ter": "glossary.page_1.ter_title",
    "curr": "glossary.page_1.currency_title",
    "conv_rate": "glossary.page_1.exch_rate_title",
    "qt_exch": "glossary.page_1.qt_exch_title",
    "price": "glossary.page_1.price_title",
    "price_eur": "glossary.page_1.eur_price_title",
    "nominal_amount": "glossary.page_1.nominal_value_title",
    "fee": "glossary.page_1.fees_title",
    "qt_held": "glossary.page_1.qt_held_title",
    "abp": "glossary.page_1.avg_price_title",
    "residual_amount": "glossary.page_1.avg_value_title",
    "effective_amount": "glossary.page_1.eff_value_title",
    "released_amount": "glossary.page_1.released_value_title",
    "gross_gain": "glossary.page_1.gross_cap_gain_title",
    "generated_loss": "glossary.page_1.cap_loss_title",
    "expiry": "glossary.page_1.exp_date_title",
    "carryforward": "glossary.page_1.backpack_title",
    "taxable_gain": "glossary.page_1.cap_gain_tax_title",
    "tax_bracket": "glossary.page_1.tax_bracket_title",
    "tax": "glossary.page_1.tax_amount_title",
    "pl": "glossary.page_1.pl_title",
    "cash_held": "glossary.page_1.cash_held_title",
    "assets_value": "glossary.page_1.assets_value_title",
    "nav": "glossary.page_1.nav_title",
    "committed_cash": "glossary.page_1.historic_cash_title",
}

# The internal column names, in file order.
COLUMNS = list(COLUMN_TITLE_KEYS)

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
    return {col: translator.get(key).strip() for col, key in COLUMN_TITLE_KEYS.items()}


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
