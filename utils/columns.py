"""
Centralised column definitions for internal DataFrame storage.

Internal storage uses English column names.
Export uses locale-specific headers resolved via the translator (glossary keys).
Legacy CSVs with Italian column names are auto-migrated on load.
"""

# Ordered list of the 29 internal column names.
COLUMNS = [
    "date", "account", "operation", "product", "ticker", "asset_name",
    "ter", "curr", "conv_rate", "qt_exch", "price", "price_eur",
    "nominal_amount", "fee", "qt_held", "abp", "residual_amount",
    "effective_amount", "released_amount", "gross_gain", "generated_loss",
    "expiry", "carryforward", "taxable_gain", "tax_bracket", "tax", "pl",
    "cash_held", "assets_value", "nav", "committed_cash",
]

# Glossary keys in the same order as COLUMNS (used for export headers).
GLOSSARY_KEYS = [
    "glossary.page_1.date_title",
    "glossary.page_1.account_title",
    "glossary.page_1.operation_title",
    "glossary.page_1.product_title",
    "glossary.page_1.ticker_title",
    "glossary.page_1.asset_name_title",
    "glossary.page_1.ter_title",
    "glossary.page_1.currency_title",
    "glossary.page_1.exch_rate_title",
    "glossary.page_1.qt_exch_title",
    "glossary.page_1.price_title",
    "glossary.page_1.eur_price_title",
    "glossary.page_1.nominal_value_title",
    "glossary.page_1.fees_title",
    "glossary.page_1.qt_held_title",
    "glossary.page_1.avg_price_title",
    "glossary.page_1.avg_value_title",
    "glossary.page_1.eff_value_title",
    "glossary.page_1.released_value_title",
    "glossary.page_1.gross_cap_gain_title",
    "glossary.page_1.cap_loss_title",
    "glossary.page_1.exp_date_title",
    "glossary.page_1.backpack_title",
    "glossary.page_1.cap_gain_tax_title",
    "glossary.page_1.tax_bracket_title",
    "glossary.page_1.tax_amount_title",
    "glossary.page_1.pl_title",
    "glossary.page_1.cash_held_title",
    "glossary.page_1.assets_value_title",
    "glossary.page_1.nav_title",
    "glossary.page_1.historic_cash_title",
]

# Maps old Italian column names → new English internal names.
OLD_TO_NEW = {
    "Data": "date",
    "Conto": "account",
    "Operazione": "operation",
    "Prodotto": "product",
    "Ticker": "ticker",
    "Nome Asset": "asset_name",
    "TER": "ter",
    "Valuta": "curr",
    "Tasso di Conv.": "conv_rate",
    "QT. Scambio": "qt_exch",
    "Prezzo": "price",
    "Prezzo EUR": "price_eur",
    "Imp. Nominale Operaz.": "nominal_amount",
    "Commissioni": "fee",
    "QT. Attuale": "qt_held",
    "PMC": "abp",
    "Imp. Residuo Asset": "residual_amount",
    "Imp. Effettivo Operaz.": "effective_amount",
    "Costo Rilasciato": "released_amount",
    "Plusv. Lorda": "gross_gain",
    "Minusv. Generata": "generated_loss",
    "Scadenza": "expiry",
    "Zainetto Fiscale": "carryforward",
    "Plusv. Imponibile": "taxable_gain",
    "Aliquota Fiscale": "tax_bracket",
    "Imposta": "tax",
    "P&L": "pl",
    "Liquidita Attuale": "cash_held",
    "Valore Titoli": "assets_value",
    "NAV": "nav",
    "Liq. Impegnata": "committed_cash",
}


# Maps old Italian operation values → new English internal values.
OLD_OPERATIONS = {
    "Deposito": "Deposit",
    "Prelievo": "Withdrawal",
    "Acquisto": "Buy",
    "Vendita": "Sell",
    "Dividendo": "Dividend",
    "Imposta": "Tax",
}

# Maps old Italian product values → new English internal values.
OLD_PRODUCTS = {
    "Contanti": "Cash",
    "Azioni": "Stock",
    "Dividendo": "Dividend",
    "Imposta": "Tax",
    # "ETF" stays "ETF"
}

# Maps internal English operation values → locale keys for export.
OPERATION_LOCALE_KEYS = {
    "Deposit": "values.op_deposit",
    "Withdrawal": "values.op_withdrawal",
    "Buy": "values.op_buy",
    "Sell": "values.op_sell",
    "Dividend": "values.op_dividend",
    "Tax": "values.op_tax",
}

# Maps internal English product values → locale keys for export.
PRODUCT_LOCALE_KEYS = {
    "Cash": "values.prod_cash",
    "ETF": "values.prod_etf",
    "Stock": "values.prod_stock",
    "Dividend": "values.prod_dividend",
    "Tax": "values.prod_tax",
}


def export_headers(translator):
    """Return dict mapping internal column name → locale display name."""
    return {
        col: translator.get(key).strip()
        for col, key in zip(COLUMNS, GLOSSARY_KEYS)
    }


def _translate_values(df, translator):
    """Translate operation and product column values to locale strings."""
    if "operation" in df.columns:
        op_map = {k: translator.get(v).strip() for k, v in OPERATION_LOCALE_KEYS.items()}
        df["operation"] = df["operation"].map(lambda x: op_map.get(x, x))
    if "product" in df.columns:
        prod_map = {k: translator.get(v).strip() for k, v in PRODUCT_LOCALE_KEYS.items()}
        df["product"] = df["product"].map(lambda x: prod_map.get(x, x))
    return df


def rename_for_export(df, translator):
    """Return a copy of *df* with columns and values translated for export."""
    out = df.copy()
    _translate_values(out, translator)
    mapping = export_headers(translator)
    return out.rename(columns=mapping)


def rename_from_legacy(df):
    """Rename old Italian columns and values to new English names (in-place).

    Returns True if migration was performed, False otherwise.
    """
    migrated = False
    current_cols = set(df.columns)
    if current_cols & set(OLD_TO_NEW.keys()):
        df.rename(columns=OLD_TO_NEW, inplace=True)
        migrated = True

    # Migrate operation values
    op_col = "operation" if "operation" in df.columns else None
    if op_col:
        mask = df[op_col].isin(OLD_OPERATIONS.keys())
        if mask.any():
            df[op_col] = df[op_col].map(lambda x: OLD_OPERATIONS.get(x, x))
            migrated = True

    # Migrate product values
    prod_col = "product" if "product" in df.columns else None
    if prod_col:
        mask = df[prod_col].isin(OLD_PRODUCTS.keys())
        if mask.any():
            df[prod_col] = df[prod_col].map(lambda x: OLD_PRODUCTS.get(x, x))
            migrated = True

    return migrated
