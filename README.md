# ITA 🇮🇹 (ENG below)
# Portfolio Manager

Portfolio Manager è un'applicazione GUI multipiattaforma per la gestione ed analisi di portafogli finanziari (azioni ed ETF), pensata per investitori privati che desiderano tracciare in modo dettagliato le proprie operazioni, la liquidità, il calcolo delle plusvalenze/minusvalenze e la gestione dello zainetto fiscale secondo la normativa italiana.

Sono inoltre disponibili strumenti di analisi: VaR (Monte Carlo), volatilità/Sharpe ratio, correlazione, drawdown, XIRR e TWRR.

Realizzata con [Flet](https://flet.dev/), è pensata principalmente per uso mobile (Android, iOS), ma supporta anche Linux, macOS, Windows.


## Funzionalità principali

- **Gestione multi-conto**: supporto a più account con alias personalizzabili
- **Operazioni su liquidità**: depositi, prelievi, dividendi, imposte e commissioni
- **Operazioni su titoli**: acquisto e vendita di azioni ed ETF, con gestione valuta (EUR/USD), commissioni e TER
- **Calcolo automatico di**:
  - Prezzo Medio di Carico (PMC)
  - Plusvalenze e minusvalenze realizzate e non
  - Zainetto fiscale con scadenza delle minusvalenze
  - NAV, liquidità corrente e storica
- **Panoramica del portafoglio** con posizioni aperte, P&L e prezzi in tempo reale (Yahoo Finance)
- **Watchlist** di titoli personalizzabile
- **Esportazione CSV** delle transazioni con intestazioni localizzate
- **Strumenti di analisi del rischio** (dettagli sotto)
- **Multilingua**: italiano e inglese

| Home                                                                    | Home (Dark theme, Hidden data, English)                                | Settings                                                                |
| -                                                                       | -                                                                      | -                                                                       |
| <img src="./media/screenshots/home-light.png" alt="image" width="300"/> | <img src="./media/screenshots/home-dark.png" alt="image" width="300"/> | <img src="./media/screenshots/settings.png" alt="image" width="300"/>   |
| **Operations**                                                          | **Transactions**                                                       | **Statistics**                                                          |
| <img src="./media/screenshots/operations.png" alt="image" width="300"/> | <img src="./media/screenshots/trans.png" alt="image" width="300"/>     | <img src="./media/screenshots/statistics.png" alt="image" width="300"/> |
| **Correlation**                                                         | **Drawdown**                                                           | **Value at Risk**                                                       |
| <img src="./media/screenshots/corr.png" alt="image" width="300"/>       | <img src="./media/screenshots/drawdown.png" alt="image" width="300"/>  | <img src="./media/screenshots/var.png" alt="image" width="300"/>        |


## Applicazione

Quattro schermate principali:

- **HOME**: Panoramica conto, posizioni aperte, watchlist
- **OPERAZIONI**: Inserimento di nuove transazioni, supporto EUR/USD
    - *Liquidità* (depositi, prelievi, dividendi, imposte)
    - *ETF Azionari* (acquisto/vendita) 
    - *Azioni* (acquisto/vendita)
    - In programma: *ETF Monetari / Obbligazionari, Obbligazioni*
- **ANALISI**: strumenti per l'analisi del portafoglio. È presente un tasto Info per ogni strumento, con informazioni a riguardo.
    - *Statistiche generali*: principali statistiche del portafoglio con grafico
    - *Correlazione*: correlazione semplice tra asset in portafoglio e correlazione rolling tra due asset selezionati
    - *Drawdown*: calcolo e grafico del drawdown del portafoglio
    - *Value at Risk*: simulazione Monte Carlo su serie storiche con intervallo di confidenza e orizzonte temporale personalizzabili
- **TRANSAZIONI**: storico delle transazioni filtrabile + esportazione in tabella CSV. È presente un tasto Info con informazioni riguardo le colonne del report CSV.


## Primo avvio

1. **Scelta della lingua**: Italiano, Inglese
2. **Setup dei conti**: inserimento degli alias dei propri intermediari (es. *Fineco Principale, Fineco 2, Directa*). I conti possono essere aggiunti o rimossi successivamente dalle impostazioni. Non è possibile rinominare un conto esistente.

Le transazioni vengono salvate automaticamente ad ogni inserimento.


## Installazione
### Download diretto
1. Nella sezione "Releases", scarica il programma per il tuo sistema operativo.

### Installazione manuale
1. Clona la repository
2. Installa i pacchetti (richiesto Python >= 3.11, testato con 3.13):
    - `uv`: esegui `uv sync`
    - `pip`:
```sh
pip install flet flet-charts pandas numpy yfinance python-dateutil
```
3. (Opzionale) Per testare l'applicazione: 
  - `uv`: `uv run flet run main.py`
  - `pip`: `python main.py` oppure `flet run`

4. Build dell'applicazione:
  - `uv`: `uv run flet build <target> --project "Portfolio Manager"`
  - `pip`: `flet build <target> --project "Portfolio Manager"`
  - `<target>` == `apk`, `ios`, `linux`, `macos`, `windows`



## Note

- Gli split azionari **non** sono attualmente gestiti
- L'inserimento delle transazioni è esclusivamente sequenziale (cronologico)
- Il software è pensato per uso personale e didattico. Non costituisce consulenza finanziaria
- La logica fiscale segue la normativa italiana vigente al 2026; si consiglia sempre la verifica con un consulente

---

# ENG 🇬🇧 🇺🇸
# Portfolio Manager

Portfolio Manager is a cross-platform GUI application for managing and analyzing financial portfolios (stocks and ETFs). It is designed for private investors who wish to track their operations, liquidity, capital gains/losses, and manage tax loss carryforwards (*zainetto fiscale*) according to Italian regulations.

It also includes several analysis tools: VaR (Monte Carlo), volatility/Sharpe ratio, correlation, drawdown, XIRR and TWRR.

Built with [Flet](https://flet.dev/), it is mobile-focused (Android, iOS) but it also supporsts Linux, macOS, Windows

## Main Features

- **Multi-account management**: support for multiple brokers with custom aliases
- **Cash operations**: deposits, withdrawals, dividends, taxes and charges
- **Securities operations**: buy and sell stocks and ETFs, with currency handling (EUR/USD), fees and TER
- **Automatic calculation of**:
  - Average Buy Price (ABP)
  - Realized and unrealized capital gains/losses
  - Tax loss Carryforward with expiry tracking
  - NAV, current and historical liquidity
- **Portfolio overview** with open positions, P&L and live prices (Yahoo Finance)
- **Customizable watchlist**
- **CSV export** of transactions with localized column headers
- **Risk analysis tools** (details below)
- **Multilingual**: English and Italian


## Application

Four main tabs:

- **HOME**: Account(s) overview, open positions, watchlist
- **OPERATIONS**: Guided entry of new transactions, EUR/USD support
    - *Cash operations* (deposits, withdrawals, dividends, taxes) 
    - *ETFs (equity)* (buy/sell)
    - *Stocks* (buy/sell)
    - Next priority: support for *Money Market ETFs, Bond ETFs, Bonds*
- **ANALYSIS**: tools for portfolio analysis. There is an Info button for each tool, describing its usage.
    - *Statistics*: general portfolio statistics with graph
    - *Correlation*: simple correlation between held assets, rolling correlation between two specified assets
    - *Drawdown*: graph showcasing the portfolio's drawdown
    - *Value at Risk*: Monte Carlo simulations on historical data, with customizable confidence interval and horizon
- **TRANSACTIONS**: filterable transaction history + CSV export option. There is an Info button describing in detail each column of the CSV report.


## First Launch

1. **Language selection**: English, Italian
2. **Account setup**: enter aliases for your brokers (e.g., *Fineco Main, Fineco 2, Directa*). Accounts can be added or removed later from Settings. Existing accounts cannot be renamed.

Transactions are saved automatically as they are entered.


## Installation
### Direct Download
1. In the "Releases" section, download the program for your operating system.

### Manual Installation
1. Clone the repository
2. Install packages (requires Python >= 3.11, tested with 3.13):
  - `uv`: run `uv sync`
  - `pip`:
```sh
pip install flet flet-charts pandas numpy yfinance python-dateutil
```
3. (Optional) To test the application:
  - `uv`: `uv run flet run main.py`
  - `pip`: `python main.py` or `flet run`
4. App building:
  - `uv`: `uv run flet build <target> --project "Portfolio Manager"`
  - `pip`: `flet build <target> --project "Portfolio Manager"`
  - `<target>` == `apk`, `ios`, `linux`, `macos`, `windows`


## Notes

- Stock splits are **not** currently handled
- Transaction entry is exclusively sequential (chronological)
- This software is intended for personal and educational use. It does not constitute financial advice
- The fiscal logic follows Italian regulations in force as of 2026; always verify with a professional advisor
