## [0.1.5] (XXXX-XX-XX)

### Bug Fixes

- **[LOCALE]** Fixed missing key for Charges in OperationsView
- **[UI]** Fixing watchlist items' value misalignments


### Features

- **[UI]** Changed Buy/Sell Radio buttons to a Switch
- **[UI]** Added ETF type selection Radio buttons in the ETF tab, to enable future support of Money Market ETFs and Bonds ETFs





## [0.1.4] (2026-03-18)

### Bug Fixes

- [DEAD CODE] **Removed legacy code** related to the old CLI application
- [DEAD CODE] **Removed duplicated** `_build_info_button()` and `_show_glossary()` in TransactionsView, now rendered via `views/__init__.py`
- [DEAD CODE] **Removed duplicated** `if fee < 0` check in `_submit_es()` (OperationsView)
- [DEAD CODE] **Standardized old italian-named variables to english**
- [DEAD CODE] **Removed `fetch_utils.py`**, as it was carried over from the old CLI project and it only acted as a wrapper file for `market_data.py`
- [PERFORMANCE] **Fixed repeated `config.ini` read/writes**, from 6 separated instances to a single one
- [PERFORMANCE] **Fixed SnackBar accumulation**, where `show_snack()` stacked new SnackBars to `page.overlay` without removing old ones
- [LOGIC] **CRITICAL Fixed `sell_asset()`** using non-converted price to compute the new `asset_value`. Fortunately, this only affected the `asset_value` column and did not compromise the whole Sell operation
- [LOGIC] **Changed _TAB_TO_GLOSSARY from an hardcoded mapping to a dynamic update**. Before: `_TAB_TO_GLOSSARY = {0: 2, 1: 3, 2: 4, 3: 5}`, mapping analysis tab indices to glossary page numbers. Now: dynamic index + 2 (offset)
- [UI] **Fixed "Apply" button** in TransactionsView being cutoff (mobile only)
- [UI] **Fixed "Fee currency" dropdown being wider then "Currency" dropdown** in OperationsView


### Features

- [VISUAL] Add splash screen: assets/splash.png (optional: splash_dark.png, splash_android.png, splash_ios.png)
- [VISUAL] Replaced "Home" text in AppBar with "(icon) Portfolio Manager"
- [FUNCTIONAL] **NEW Live Yahoo Finance search suggestions** when accessing Ticker text fields (for example, searching for a ticker in Watchlist). Need at least 2 characters typed for suggestions to appear
