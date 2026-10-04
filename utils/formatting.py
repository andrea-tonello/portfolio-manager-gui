"""How amounts and percentages are written on screen."""

# Shown in place of an amount while the user has hidden their values.
HIDDEN_MASK = "•" * 6

# Shown in place of an amount while it is still being fetched.
LOADING = "---"


def fmt_eur(amount, signed=False):
    """Write `amount` in euros with thousands separators; `signed` always shows + or -.

    Example: fmt_eur(1234.5) -> "1,234.50€", fmt_eur(12.3, signed=True) -> "+12.30€".
    """
    return f"{amount:+,.2f}€" if signed else f"{amount:,.2f}€"


def fmt_pct(pct):
    """Write a percentage with its sign, or a dash when there is none (None: nothing to compare with).

    Example: fmt_pct(4.9012) -> "+4.90%", fmt_pct(None) -> "—".
    """
    return "—" if pct is None else f"{pct:+.2f}%"
