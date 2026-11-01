"""The version of the rules that compute a ledger's rows from its journal: taxes, Tax Carryforward, average buy price, P&L.

A ledger is only rebuilt from where its journal changes, so rows computed
by an older version of these rules keep their values. Whenever a change to
the rules (domain/newrow.py, domain/tax.py, domain/positions.py, apply in
domain/journal.py) gives a row different values for the same operations:

1. raise RULES_VERSION by one;
2. add to RULES_CHANGES the locale key of a sentence saying what changed,
   with its text in every language under "rules".

At its next start the app then offers each user whose accounts were last
recalculated with an older version to recalculate their history, listing
those sentences (components/recalculation.py). Changes that only move
market values (assets_value, nav) don't need a new version.

Example: a fix to when the Tax Carryforward expires -> RULES_VERSION = 2,
RULES_CHANGES = {2: "rules.v2"}, and in en.json "rules": {"v2": "The Tax
Carryforward now expires on 31 December of the fourth year after the loss."}.
"""

# The rules this version of the app computes rows with. 1 is the version before this number existed.
RULES_VERSION = 1

# What each version changed, as the locale key of a sentence for the user: {version: key}.
RULES_CHANGES: dict[int, str] = {}
