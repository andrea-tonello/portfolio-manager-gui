# Rendicontazione Portafoglio Finanziario
### TODO
- [x] Obbligo fee manuale
- [x] Gestione conti (README):
  - [x] Selezione degli intermediari
  - [x] brokers.json in cartella config (tenerla "dentro" su pyinstaller)
  - [x] Separazione degli intermediari
  - [x] Crea i defaults se non presenti
- [x] Usa yfinance per exchange rates
- [x] Sistema il check delle modifiche
- [ ] Sezione "Informazioni" (README):
  - [x] Descrizione colonne
  - [ ] Descrizione statistiche/altro
- [ ] Analisi portafoglio: (README)
  - [x] Statistiche separate tra conti + totale
  - [ ] Utile / Rendimento
  - [x] Correlazione 
  - [x] Drawdown
  - [x] VaR
  - [ ] Sharpe
- [ ] Fetch del TER
- [ ] Casistiche di errore

### TODO avanzati
- [ ] Inserimento non sequenziale (per limitare le chiamate a yfinance, prova a prendere tutto in bulk e poi calcolare riga per riga)

Questo progetto è uno script/software per la **rendicontazione di portafogli finanziari** (azionario ed ETF), pensato per investitori privati che desiderano tracciare in modo dettagliato le operazioni, la liquidità, il calcolo delle plusvalenze/minusvalenze e la gestione dello zainetto fiscale secondo la normativa italiana.

## Funzionalità principali

- **Importazione automatica** delle operazioni da file CSV.
- **Gestione di operazioni** di acquisto, vendita, deposito e prelievo di liquidità.
- **Calcolo automatico** di:
  - Prezzo Medio Ponderato di Carico (PMPC)
  - Plusvalenze e minusvalenze
  - Zainetto fiscale (credito fiscale da minusvalenze)
  - Scadenza delle minusvalenze secondo la normativa italiana
  - NAV, liquidità attuale e storica
- **Recupero automatico** delle informazioni sugli strumenti tramite ISIN (nome, TER, ecc.).
- **Interfaccia testuale** per l'inserimento guidato di nuove operazioni.

## Struttura

- `main.ipynb`: notebook principale per l'esecuzione e l'interazione con il portafoglio.
- `newrow.py`: funzioni per aggiungere nuove righe/operazioni al portafoglio.
- `utils.py`: funzioni di utilità per calcoli fiscali, gestione delle date, recupero dati, ecc.
- `fetch_data.py`: scraping e integrazione con l'API OpenFIGI per recuperare informazioni sugli strumenti tramite ISIN.

## Download / Installazione
#### Download diretto
1. Su questa pagina, clicca su "Release" e scarica il programma per il tuo sistema operativo in una cartella dedicata.
#### Installazione manuale
1. Clona la repository
2. Installa i pacchetti (Python 3.8+):
    - [pandas](https://pandas.pydata.org/)
    - [numpy](https://numpy.org/)
    - [python-dateutil](https://dateutil.readthedocs.io/)
    - [yfinance](https://ranaroussi.github.io/yfinance/)
```sh
pip install pandas numpy python-dateutil yfinance
```
3. Runna `python main.py`


## Utilizzo
All'avvio del programma verrà sempre richiesto se caricare il file di default "report.csv", oppure caricare un report secondario/con un altro nome. ***Si consiglia di usare direttamente questo file se si intende avere solo una tabella unica***.

Nel caso si volesse comunque usare un altro report, magari secondario, bisognerà specificare il nome del file. Il file ***deve essere già presente nella cartella*** "reports" e deve seguire il formato delle colonne di report.csv. A tal proposito, viene
fornito un file report-template.csv da copia-incollare già pronto.

Al primo avvio è richiesto il setup dei propri intermediari. Scegliere gli alias che si preferiscono.
Ad esempio, con due conti Fineco e uno Directa: *Fineco Principale, Fineco 2, Directa*. Gli intermediari potranno inoltre essere cambiati successivamente, 
ma è da tenere a mente che le modifiche non saranno retroattive
(se sul report caricato sono già presenti transazioni su "Fineco 2", rinominarlo in "Fineco Secondario" non aggiornerà i dati già presenti).

Successivamente verrà presentato il Menu Principale con le seguenti opzioni:
1. Operazioni su liquidità: Depositi, Prelievi, Dividendi, Imposte varie (es. Imposta di Bollo)
2. Operazioni su ETF: Acquisto, Vendita
3. Operazioni su Azioni: Acquisto, Vendita
4. Operazioni su Obbligazioni: ***non ancora implementate***.
5. Resoconto in data gg-mm-yyyy: ultime dieci righe del report, P&L totale, Liquidità storica del conto; Valore titoli, Net Asset Value e Posizioni al giorno gg-mm-yyyy.
6. (Re)inizializzazione degli intermediari (come spiegato precedentemente)
7. Esporta in csv: salva le modifiche eseguite fino a quel momento.
8. Rimuovi ultima riga del report
9. Glossario con le descrizioni delle entries dei report
10. Esci dal programma

Da qualsiasi schermata, è possibile annullare l'operazione corrente e tornare al Menu Principale con CTRL+C / CMD+C.
Come già specificato, le modifiche (comprese la rimozione di righe) sono confermate (salvate) solo manualmente con l'opzione apposita.



## Note

- Il software è pensato per uso personale e didattico. Non costituisce consulenza finanziaria.
- La logica fiscale implementata segue la normativa italiana vigente al 2024, ma si consiglia di verificare sempre con un consulente.
