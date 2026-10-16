# ITA 🇮🇹 (ENG below)
# Portfolio Manager

Portfolio Manager è un'applicazione per la gestione ed analisi di portafogli finanziari, **nata per risolvere un problema personale: aggregare, in un unico spazio, tutti i propri conti titoli**. Volevo qualcosa che:

- Mi evitasse il dover controllare le varie app delle banche una per una
- Potesse sostituire il classico foglio Excel, poco pratico da telefono e meno intuitivo per gli inesperti
- Offrisse una suite di analisi di portafoglio completa, aggregando i dati di tutti i miei conti
- **Considerasse la tassazione e le leggi italiane**

> *E non esiste già?*

- Esiste l'ottimo [Portfolio Performance](https://github.com/portfolio-performance/portfolio), che inizialmente ho provato ad usare, ma che purtroppo non risolve un problema enorme: **la gestione della tassazione italiana, e le logiche di funzionamento dello zainetto fiscale.**

Questa app è dunque pensata per investitori privati che desiderano tracciare in modo dettagliato le proprie operazioni, la liquidità, il calcolo delle plusvalenze/minusvalenze e la gestione dello zainetto fiscale secondo la normativa italiana, oltre a vari tools per analisi dettagliate (dettagli sotto).

Realizzata con [Flet](https://flet.dev/), è pensata principalmente per uso mobile (Android, in futuro iOS), ma supporta anche Linux, macOS, Windows.


## Funzionalità principali

- **Gestione multi-conto**: supporto a più account con alias personalizzabili
- **Operazioni su liquidità**: depositi, prelievi, dividendi, imposte
- **Operazioni su titoli**: acquisto e vendita di azioni ed ETF, con gestione valuta (EUR/USD), commissioni e TER (supporto alle obbligazioni in arrivo)
- **Panoramica del portafoglio** con posizioni aperte, P&L e prezzi in tempo reale (Yahoo Finance)
- **Watchlist** di titoli personalizzabile
- **Lista dei movimenti con esportazione CSV** delle transazioni con campi dettagliati
- **Strumenti di analisi di portafoglio e di rischio** (dettagli sotto)
- **Multilingua**: italiano e inglese

<table>
  <tr>
    <td align="center"><br><b>Home, Watchlist</b></td>
    <td align="center"><br><b>Home, Posizioni Aperte</b></td>
    <td align="center"><br><b>Home (Dark, Hidden data, ENG)</b></td>
    <td align="center"><br><b>Gestione multi-utente</b></td>
  </tr>
  <tr>
    <td align="center"><img src="./assets/readme/home-light.png" alt="image" width="200"/></td>
    <td align="center"><img src="./assets/readme/home-brokerlist.png" alt="image" width="200"/></td>
    <td align="center"><img src="./assets/readme/home-dark.png" alt="image" width="200"/></td>
    <td align="center"><img src="./assets/readme/drawer.png" alt="image" width="200"/></td>
  </tr>
  <tr>
    <td align="center"><br><b>Operazioni</b></td>
    <td align="center"><br><b>Operazioni</b></td>
    <td align="center"><br><b>Allocazione</b></td>
    <td align="center"><br><b>Allocazione</b></td>
  </tr>
  <tr>
    <td align="center"><img src="./assets/readme/operations-general.png" alt="image" width="200"/></td>
    <td align="center"><img src="./assets/readme/operations-stocks.png" alt="image" width="200"/></td>
    <td align="center"><img src="./assets/readme/alloc-class.png" alt="image" width="200"/></td>
    <td align="center"><img src="./assets/readme/alloc-sectors.png" alt="image" width="200"/></td>
  </tr>
  <tr>
    <td align="center"><br><b>Lista movimenti</b></td>
    <td align="center"><br><b>Andamento Portafoglio</b></td>
    <td align="center"><br><b>Value at Risk</b></td>
    <td align="center"><br><b>Impostazioni</b></td>
  </tr>
  <tr>
    <td align="center"><img src="./assets/readme/transac.png" alt="image" width="200"/></td>
    <td align="center"><img src="./assets/readme/statistics.png" alt="image" width="200"/></td>
    <td align="center"><img src="./assets/readme/var.png" alt="image" width="200"/></td>
    <td align="center"><img src="./assets/readme/settings.png" alt="image" width="200"/></td>
  </tr>
</table>


## Applicazione

Quattro schermate principali:

- **HOME**: Panoramica conto, posizioni aperte, watchlist
- **OPERAZIONI**: Inserimento di nuove transazioni, supporto EUR/USD. Le transazioni vengono salvate automaticamente ad ogni inserimento.
    - *Liquidità* (depositi, prelievi, dividendi, imposte)
    - *ETF Azionari, ETF Monetari* (acquisto/vendita) 
    - *Azioni* (acquisto/vendita)
    - In programma: *ETF Obbligazionari, Obbligazioni*
- **ANALISI**: strumenti per l'analisi del portafoglio. È presente un tasto Info per ogni strumento, con informazioni a riguardo.
    - *Allocazione* per asset class e settore
    - *Statistiche generali*: principali statistiche del portafoglio con grafico
    - *Correlazione*: correlazione semplice tra asset in portafoglio e correlazione rolling tra due asset selezionati
    - *Drawdown*: calcolo e grafico del drawdown del portafoglio
    - *Value at Risk*: simulazione Monte Carlo su serie storiche con intervallo di confidenza e orizzonte temporale personalizzabili
- **TRANSAZIONI**: storico delle transazioni filtrabile + esportazione in tabella CSV. È presente un tasto Info con informazioni riguardo le colonne del report CSV.


## Backups

È possibile **esportare ed importare backup** completi dell'applicazione, comprendenti tutto: ogni utente, ogni broker, ogni impostazione principale.

Essendo l'app **local-only**, questo è l'unico modo per salvare e trasferire le proprie informazioni.


## Primo avvio

**1\. Scelta della lingua**: Italiano, Inglese

**2a\. Importare dati da backup esistente**

**2b\.** Oppure, **Setup dei conti**: nuovo utente ed inserimento degli alias dei propri intermediari (es. *Fineco Principale, Fineco 2, Directa*). I conti possono essere aggiunti o rimossi successivamente dalle impostazioni. Non è possibile rinominare un conto esistente.



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

- Transaction entry is exclusively sequential (chronological)
- This software is intended for personal and educational use. It does not constitute financial advice
- The fiscal logic follows Italian regulations in force as of 2026; always verify with a professional advisor
