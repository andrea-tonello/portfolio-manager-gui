# Rendicontazione Portafoglio Finanziario
### TODO in ordine di priorità
- [ ] Opzione fee manuale
- [ ] Selezione degli Intermediari
- [ ] Calcolo separato NAV

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

## Struttura del progetto

- `main.ipynb`: notebook principale per l'esecuzione e l'interazione con il portafoglio.
- `newrow.py`: funzioni per aggiungere nuove righe/operazioni al portafoglio.
- `utils.py`: funzioni di utilità per calcoli fiscali, gestione delle date, recupero dati, ecc.
- `fetch_data.py`: scraping e integrazione con l'API OpenFIGI per recuperare informazioni sugli strumenti tramite ISIN.

## Requisiti

- Python 3.8+
- [pandas](https://pandas.pydata.org/)
- [numpy](https://numpy.org/)
- [requests](https://requests.readthedocs.io/)
- [python-dateutil](https://dateutil.readthedocs.io/)

Installa i pacchetti necessari con:

```sh
pip install pandas numpy requests python-dateutil
```

## Utilizzo

1. **Prepara il file `report.csv`** con la struttura delle colonne prevista (vedi esempio incluso).
2. **Avvia il notebook** `main.ipynb` in Jupyter o Visual Studio Code.
3. **Segui il menu interattivo** per inserire nuove operazioni (liquidità, ETF, azioni).
4. **Salva le modifiche** su sul file o creane uno nuovo.

## Note

- Il software è pensato per uso personale e didattico. Non costituisce consulenza finanziaria.
- La logica fiscale implementata segue la normativa italiana vigente al 2024, ma si consiglia di verificare sempre con un consulente.

## Esempio di struttura CSV

Vedi il file `report.csv` per un esempio di struttura e dati. Il file `report-template.csv` contiene un template per iniziare "da zero".
