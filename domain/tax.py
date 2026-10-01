"""Italian capital gains tax rules.

For now this only holds the standard rate; buy_asset, sell_asset and
compute_carryforward move here from utils/account.py with D3 (REFACTORING.md).
"""

# Rate applied to a sale's taxable gain (gain minus any carryforward used).
# Money-market ETFs can be taxed at a different rate, typed by the user in the
# Operations form (e.g. 12.5% for those holding mainly government bonds).
DEFAULT_CAPITAL_GAINS_TAX_RATE = 0.26
