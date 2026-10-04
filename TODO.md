
## NEXT SPRINT



## BACKLOG

- Auto "-" inserted when typing dates
- Set some defaults dates for every tool in AnalysisView

- "+" add-user button should be colored/colored+text, not icon-only
- "+" watchlist button follows the ticker search dropdown (should stay near the textfield instead)
- "+ Add Transaction" button should be dynamic (Aggiungi Aquisto, Aggiungi Vendita, Aggiungi Deposito, ...)

- HAMBURGER MENU-RELATED
  - Layout
      - User - add-user popup sh
     - Divider
      - Settings
      - Privacy
      - Contacts
      - Open Source
     - App logo
      - Portfolio Manager vX.X.X

  - Home's title is now (icon) Portfolio manager



- NEW USER SETUP SCREEN
    - Align vertically language, username and accounts screens
    - Data import option on app first-ever boot
    - [TABLET] New-account wizard: reduce textfields width
    - New-account wizard: the "+ Add" button for the accounts should be right to the textfield, not below it 

- red cash balance in Home View if cash is negative
- focus_chain does not work when going from TER to Tax Bracket

- LIMIT POPUPS VERTICALLY
    - "?" Fee Management popup
    - Contacts popup
    - Reset application popup
- XEON tickers appears when Stocks ETFs is selected
- Allocation analysis: XEON is in portfolio, but no "Money Market ETF" appears in the pie chart
- [TABLET] Reduce account dropdown width in each of the 4 main views

- Update README images
- [INVESTIGATE] Can app size be brought further down?
- [INVESTIGATE] Can Flet 1.0.3 avoid the focus_chain component (moving between keyboard inputs)?
- [INVESTIGATE] Does Flet 1.0.3 have better support for floating buttons?
- [INVESTIGATE] When the user changes an exported file's name, the snackbar still shows the default filename
- [POSSIBLE FUTURE REFACTOR] New components/buttons.py with the current action_card.py + other shared button styles (e.g. generalize analysis_view.py/calculate_button)



## AFTER REFACTOR IS COMPLETE:

- Re-record every transaction



## BACKLOG-BIG

- Region allocation
- Sector allocation
- Auto updates
- Non-chronological insertions
- Bonds
- Bonds ETFs
- Markdown for TransactionView
- Markdown for AnalysisView
- iOS UI
    - NavigationBar