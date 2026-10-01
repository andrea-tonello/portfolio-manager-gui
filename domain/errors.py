"""Errors the user should see, carrying a locale key instead of finished text.

Domain and service code doesn't know the user's language. It raises one of
these with the key of the message in assets/i18n/<language>.json and the values
to fill in; the screen that catches it translates it with
components.snack.error_message.

Example: ValidationError("operations.split.ticker_notheld", ticker="AAA.MI")
is shown as 'You do not currently hold AAA.MI' in English and
'Non possiedi attualmente AAA.MI' in Italian.
"""


class ValidationError(Exception):
    """An operation was refused because of the user's input or the account's state.

    `key` is the message's locale key, `params` the values for its {placeholders}.
    """

    def __init__(self, key: str, **params):
        """Store the locale key and the placeholder values for the screen to translate."""
        super().__init__(key)
        self.key = key
        self.params = params


class TickerNotFound(ValidationError):
    """Yahoo Finance doesn't know `ticker` (mistyped, delisted, or wrong exchange suffix)."""

    def __init__(self, ticker: str):
        """Point at the "ticker not recognized" message, naming the ticker."""
        super().__init__("operations.stock.ticker_notfound", ticker=ticker)
