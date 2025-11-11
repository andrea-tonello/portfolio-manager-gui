# Portfolio Manager

Portfolio Manager è un software CLI pensato per la gestione ed analisi di portafogli finanziari (azionario ed ETF), per investitori privati che desiderano tracciare in modo dettagliato le operazioni, la liquidità, il calcolo delle plusvalenze/minusvalenze e la gestione dello zainetto fiscale secondo la normativa italiana.

Sono inoltre disponibili numerosi strumenti di analisi del rischio: VaR (Monte Carlo), analisi volatilità/Sharpe ratio, analisi della correlazione, drawdown.

## Funzionalità principali

- Interfaccia da riga di comando per l'inserimento guidato di nuove operazioni: acquisto, vendita, deposito e prelievo di liquidità, dividendi, imposte
- Calcolo di:
  - Prezzo Medio di Carico
  - Plusvalenze e minusvalenze
  - Zainetto fiscale
  - Scadenza delle minusvalenze secondo la normativa italiana
  - NAV, liquidità attuale e storica
- Salvataggio in tabelle CSV di transazioni e storico del portafoglio
- Tools per analisi di portafoglio, con statistiche e grafici



| Menù Principale                                                      | Statistiche generali del portafoglio                                  |
| -                                                                    | -                                                                     |
| <img src="./media/screenshots/menu.png" alt="image" width="500"/>    | <img src="./media/screenshots/stats.png" alt="image" width="500"/>    |
|**Correlazione semplice tra asset in portafoglio**                    |**Correlazione rolling tra due asset**                                 |
|<img src="./media/screenshots/corr.png" alt="image" width="500"/>     |<img src="./media/screenshots/corr-roll.png" alt="image" width="500"/> |
| **Drawdown**                                                         | **Value at Risk**                                                     |
|<img src="./media/screenshots/drawdown.png" alt="image" width="500"/> | <img src="./media/screenshots/var.png" alt="image" width="500"/>      |


## Utilizzo
***Primo avvio***

Al primo avvio è richiesto il setup dei propri intermediari. Scegliere gli alias che si preferiscono.
Ad esempio, con due conti Fineco e uno Directa: *Fineco Principale, Fineco 2, Directa*. Gli intermediari potranno inoltre essere aggiunti o rimossi successivamente, 
ma è da tenere a mente che le modifiche non saranno retroattive (non si possono "rinominare" degli account già salvati; in quel caso, sarà necessario inserire nuovamente tutte le transazioni).

***Utilizzo***

All'avvio del programma verrà sempre richiesto il conto su cui operare. Ad ogni conto è associato un report, ovvero una tabella CSV con le operazioni effettuate. I report sono salvati nella cartella "reports", assieme ad un report di Template.

<img src="./media/screenshots/report.png" alt="Report Example"/>

*Esempio di un report per il conto "Fineco".*

Successivamente verrà presentato il Menu Principale con le seguenti opzioni:

0. Cambia conto: ri-seleziona il conto su cui operare
1. Operazioni su liquidità: Depositi, Prelievi, Dividendi, Imposte varie (es. Imposta di Bollo)
2. Operazioni su ETF: Acquisto, Vendita
3. Operazioni su Azioni: Acquisto, Vendita
4. Operazioni su Obbligazioni: ***non ancora implementate***
5. Ultimi movimenti: visualizzazione delle ultime dieci righe del report
6. Analisi portafoglio:
    - Statistiche generali (NAV, P&L, rendimento, volatilità...)
    - Analisi correlazione
    - Analisi Drawdown
    - VaR
7. (Re)inizializzazione degli intermediari (come spiegato precedentemente)
8. Esporta in csv: salva le modifiche eseguite fino a quel momento
9. Rimuovi ultima riga del report
10. Glossario con:
    - Descrizioni delle colonne dei report
    - Definizioni ed interpretazioni degli strumenti statistici
11. Esci dal programma

Le opzioni di analisi producono grafici da poter salvare su disco. L'opzione 6.1 produce inoltre, nella cartella "reports", uno storico del valore di tutto il portafoglio.

<img src="./media/screenshots/report-historical.png" alt="Example of Historical performance of the portfolio"/>

*Esempio dello Storico Portafoglio, comprensivo di tutti i conti salvati.*

Da qualsiasi schermata, è possibile annullare l'operazione corrente e tornare al Menu Principale con CTRL+C / CMD+C.
Come già specificato, le modifiche (comprese la rimozione di righe) sono confermate (salvate) solo manualmente con l'opzione apposita.


## Download / Installazione
#### Download diretto
1. Su questa pagina, clicca su "Release" e scarica il programma per il tuo sistema operativo in una cartella dedicata.
#### Installazione manuale
1. Clona la repository
2. Installa i pacchetti (testato con Python 3.13)
  - `uv`: esegui semplicemente `uv sync` per creare l'enviroment specificato in `pyproject.toml`
  - `pip`: in un environment, installa:
```sh
pip install pandas numpy python-dateutil yfinance seaborn matplotlib scipy
```
3. Esegui `main.py`


## Note

- Il software è pensato per uso personale e didattico. Non costituisce consulenza finanziaria.
- La logica fiscale implementata segue la normativa italiana vigente al 2025, ma si consiglia di verificare sempre con un consulente.
