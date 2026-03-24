## [0.1.7] (2026-03-24)

### Bug Fixes

- **[LOGIC] CRITICAL** Android: fixed ZIP corruption error on import




## [0.1.6] (2026-03-23)

### Bug Fixes

- **[PERFORMANCE]** Reduced assets size
- **[SANITIZATION]** Added asset class checks for Tickers. For example, trying to add an AAPL operation in the ETF tab will now result in an error, since Apple is a stock
- **[UI]** Made the Ticker suggestion field dynamic in height

### Features

- Added GPLv3 license
- Filled Privacy Policy popup
- Filled Contacts popup
- Made the Haptic Feedback interface a reusable component in AppState, now accessible to each view




## [0.1.5] (2026-03-20)

### Bug Fixes

- **[LOCALE]** Fixed missing key for Charges in OperationsView
- **[UI]** Fixed watchlist items value misalignment

### Features

- **[FUNCTIONAL] NEW** Added Import Data and Export Data buttons in the Settings menu. The data includes every application setting and every account-related data, acting as an overall snapshot. This was added as a way to manage backups
- **[UI]** Added ETF type selection Radio buttons in the ETF tab, to enable future support for Money Market ETFs and Bonds ETFs
- **[UI]** Replaced Buy/Sell Radio buttons with a custom Switch




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
