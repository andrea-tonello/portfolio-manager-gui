## [0.2.6] (2026-04-13)

### Bug Fixes

- **[UI]** Fixed Bonds ETFs switch being cut off-screen by long locales

### Features

- **[LOGIC]** The user is now required to specify how transaction fees are managed for ETFs (added to ABP or treated as capital loss and added to the Tax Carryforward)
- **[UX]** Added a cancel (x) button for the user onboarding procedure



## [0.2.5] (2026-04-10)

### Bug Fixes

- **[PERFORMANCE]** Fixed table performance in TransactionsView by adding pages

### Features

- **[FEATURE] NEW** Added support for Money Market ETFs




## [0.2.4] (2026-04-10)

### Bug Fixes

- **[UI]** Better shadow effects for all container-like buttons, FilledTonalButtons, ElevatedButtons
- **[LOCALE]** NavigationBar locales now update in real time 

### Features

- **[UX] NEW** Added a lateral navigation drawer to quickly access important settings
- **[UX] NEW** Added multi-user support




## [0.2.3] (2026-04-06)

### Bug Fixes

- **[UI]** Fixed inconsistent height in some AlertDialogs with big screens
- **[UI]** Fixed NavigationBar not updating correctly after a successful backup Import
- **[LOCALE]** Updated column descriptions
- **[LOCALE]** Fixed some capitalization errors in privacy policy

### Features

- **[UI]** Reworked Open Positions and Watchlist display in HomeView. Now they get two separate section instead of being stacked vertically.




## [0.2.2] (2026-03-31)

### Bug Fixes

- **[UI]** HomeView: better tablet scaling, fixed Open Positions' entries alignment
- **[UI]** OperationsView: better tablet scaling
- **[UI]** AnalysisView: better tablet scaling, Info button is now dynamic based on screen size
- **[UI]** TransactionsView: better tablet scaling, centered table, Info button is now dynamic based on screen size
- **[UI]** SettingsView: better tablet scaling, fixed github png not displaying correctly on tablets

### Features




## [0.2.1] (2026-03-30)

### Bug Fixes

### Features

- **[UI] NEW** Added animated transitions between pages
- **[UX] NEW** TransactionsView: added column-filtering options for the Data Table 
- **[UI]** Every Dropdown's expanded menu has now the appropriate border radius
- **[UI]** Revised filtering/export options in TransactionViews




## [0.2.0] (2026-03-27)

### Bug Fixes

- **[UI]** Reduced spacing between Radio entries to declutter
- **[UI]** Reorganized OperationsView fields + fixed their alignment for larger screens
- **[UI]** Fixed ProgressRing being cut off-screen in OperationsView, AnalysisView
- **[UI]** Fixed clipping in upper part of the screen when confirming computations in AnalysisView

### Features

- **[DATA]** Preferences are now saved between app updates, using `FLET_APP_STORAGE_DATA` 




## [0.1.9] (2026-03-26)

### Bug Fixes

- **[SANITIZATION]** Enabled auto-capitalization in Ticker fields
- **[SANITIZATION]** Sanitized on-screen keyboard keys with respect to field type (e.g., in a date field only 0-9 and "-" are enabled, "/", ":" are disabled)
- **[UX]** The NavigationBar now disappears when the on-screen keyboard is open, decluttering the view when typing
- **[CRASH]** Fixed unhandled exception regarding haptic feedback

### Features

- **[UX]** Tapping the "done" button on the on-screen keyboard now brings you to the next relevant text field automatically



## [0.1.8] (2026-03-25)

### Bug Fixes

- **[UI]** Fixed cropping issues with splash screen and icons

### Features

- **[UX]** Now, table filtering preferences are saved between sessions in TransactionView 
- **[UX] NEW** HomeView, Watchlist: watchlist entries are now reorganizable
- **[UX] NEW** HomeView, Watchlist and Open Position list: by long-pressing on the Ticker chip, the full name of the product is now shown inside a tooltip
- **[UI] NEW** HomeView, Watchlist: on tablets, the full name of the product is now shown next to the Ticker chip




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
