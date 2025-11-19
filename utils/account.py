import os
import sys
import pandas as pd
import numpy as np
import yfinance as yf
import warnings

from utils.other_utils import wrong_input, round_half_up, round_down
from utils.date_utils import add_solar_years
from utils.fetch_utils import fetch_exchange_rate
warnings.simplefilter(action='ignore', category=Warning)


def load_account(translator, brokers, save_folder, report_default, active_only=True):
    """
    *Given*:
    - dict `brokers`: **Key** = int: account index, starting from 1. **Value** = str: name of the account
    - str `save_folder`: folder where to read the reports from
    - str `report_default`: default prefix for report name
    - bool `active_only`: if True, returns data only for the active account, otherwise for every account

    *Returns*:
    - list of dict `accounts_selected`, one dict per account. Each dict has **keys**: acc_idx, df, file, path, len_df_init, edited_flag
      - int `acc_idx`: index of the account (starting from 1)
      - pd.DataFrame `df`: table (report) of the account
      - str `file`: file name of the account
      - str `path`: full path of the account file
      - int `len_df_init`: length of the report (rows) at loading time. Useful only to track changes on the active account
      - bool `edited_flag`: initial flag to track file changes (set to False). Again, useful only to track changes on the active account
    """

    accounts_selected = []

    if active_only:
        print(translator.get("account.selection"))
        for key, value in brokers.items():
            print(f"    {key}. {value}")
        account = input(f"\n > ")
        try:
            account = int(account)
            if account not in list( range(1, len(brokers)+1) ):
                raise ValueError
        except ValueError:
            print(translator.get("account.selection_error"))
            input(translator.get("redirect.invalid_choice") + "\n")
            return accounts_selected, False

        filename = report_default + brokers[account] + ".csv"
        path = os.path.join(save_folder, filename)
        try:
            df = pd.read_csv(path)
        except FileNotFoundError:
            print(translator.get("account.filenotfound_error", filename=filename))
            sys.exit(translator.get("redirect.exit"))

        len_df_init = len(df)
        edited_flag = False
        accounts_selected.append({
            "acc_idx": account,
            "df": df,
            "file": filename,
            "path": path,
            "len_df_init": len_df_init,
            "edited_flag": edited_flag
        })
        
    else:
        for account in list( range(1, len(brokers)+1) ):
            filename = report_default + brokers[account] + ".csv"
            path = os.path.join(save_folder, filename)
            try:
                df = pd.read_csv(path)
            except FileNotFoundError:
                print(translator.get("account.filenotfound_error", filename=filename))
                sys.exit(translator.get("redirect.exit"))

            len_df_init = len(df)
            edited_flag = False
            accounts_selected.append({
                "acc_idx": account,
                "df": df,
                "file": filename,
                "path": path,
                "len_df_init": len_df_init,
                "edited_flag": edited_flag
            })
    return accounts_selected, True


def format_accounts(df, acc_idx, all_accounts, non_active_only=False):
    """
    *Given*:
    - pd.DataFrame `df`: table (report) of the account which is currently active
    - int `acc_idx`: index of the account which is currently active (indexing starts with 1)
    - list of dict `all_accounts`: output of `load_account()` function with parameter `select_one=False`
    - bool `non_active_only`: if True, only return information about every account but the active one 

    *Returns*:
    - list of tuples `data`: [(acc_idx1, df1), (acc_idx2, df2), ...] 
    """
    non_active_accounts = [acc for acc in all_accounts if acc["acc_idx"] != acc_idx]
    data = [(acc["acc_idx"], acc["df"]) for acc in non_active_accounts]

    if non_active_only:
        # [(1, df1), (2, df2),...]
        data = sorted(data, key=lambda x: x[0])
    else:
        data.append((acc_idx, df))
        data = sorted(data, key=lambda x: x[0])
    data = [list(t) for t in data]
    return data


def get_tickers(translator, data):
    """
    *Given*:
    - list of tuples `data`: a list output by the `format_account()` function, consisting of [(acc_idx1, df1), (acc_idx2, df2), ...] 

    *Returns*:
    - list of tuples `total_tickers`: all tickers ever transacted (across every account) and their currencies [("ticker", "currency")]
    - list of tuples `active_tickers`: tickers that have open positions (across every account) and their currencies[("ticker", "currency")]
    """
    total_tickers = []
    active_tickers = []
    for account in data:
        total_assets, active_assets = get_asset_value(translator, account[1], just_assets=True)

        total_ticker_list = total_assets[["Ticker", "Valuta"]].dropna(subset=["Ticker", "Valuta"]).drop_duplicates().apply(tuple, axis=1).tolist()
        active_ticker_list = active_assets[["Ticker", "Valuta"]].dropna(subset=["Ticker", "Valuta"]).drop_duplicates().apply(tuple, axis=1).tolist()

        total_tickers.extend(total_ticker_list)
        active_tickers.extend(active_ticker_list)

    return list(set(total_tickers)), list(set(active_tickers))


def portfolio_history(translator, start_ref_date, end_ref_date, data):

    total_tickers, _ = get_tickers(translator, data)
    all_dfs = []

    for account in data:
        df_copy = account[1].copy()
        df_copy["Data"] = pd.to_datetime(df_copy["Data"], dayfirst=True, errors="coerce")
        df_copy = df_copy[["Data", "Conto", "Ticker", "Valuta", "QT. Attuale", "Liquidita Attuale", "Liq. Impegnata"]]
        all_dfs.append(df_copy)

# 1)
    final_df = pd.concat(all_dfs, ignore_index=True)
    final_df = final_df.sort_values(by="Data", ascending=True, kind="mergesort")
    final_df = final_df.iloc[len(data):]
    final_df = final_df.reset_index(drop=True)

  # 1.1) Total liquidity across accounts
    accounts = final_df['Conto'].unique()
    liq_cols = []
    liq_hist_cols = []
    for acc in accounts:
        col_name = f'liq_running_{acc}'
        col_name_hist = f'liq_hist_{acc}'

        final_df[col_name] = final_df.where(final_df["Conto"] == acc)["Liquidita Attuale"]
        final_df[col_name] = final_df[col_name].ffill()
        final_df[col_name_hist] = final_df.where(final_df["Conto"] == acc)["Liq. Impegnata"]
        final_df[col_name_hist] = final_df[col_name_hist].ffill()

        liq_cols.append(col_name)
        liq_hist_cols.append(col_name_hist)

    final_df[liq_cols] = final_df[liq_cols].fillna(0)
    final_df['Liquidita Totale'] = final_df[liq_cols].sum(axis=1)
    final_df[liq_hist_cols] = final_df[liq_hist_cols].fillna(0)
    final_df['Liq. Impegnata Totale'] = final_df[liq_hist_cols].sum(axis=1)
    final_df = final_df.drop(columns=liq_cols+liq_hist_cols)

  # 1.2) Total quantities (assets) across accounts
    pairs = final_df.dropna(subset=['Ticker'])[['Conto', 'Ticker']].drop_duplicates().values
    state_cols = []
    ticker_to_cols_map = {}

    # Crea una colonna di stato "running" per ogni coppia (Conto, Ticker)
    for conto, ticker in pairs:
        col_name = f'state_qty_{conto}_{ticker}'
        state_cols.append(col_name)
        # Mappa il ticker alla sua colonna di stato
        if ticker not in ticker_to_cols_map:
            ticker_to_cols_map[ticker] = []
        ticker_to_cols_map[ticker].append(col_name)
        # Crea la colonna di stato:
        # Prende il valore 'QT. Attuale' solo per la riga esatta
        mask = (final_df['Conto'] == conto) & (final_df['Ticker'] == ticker)
        final_df[col_name] = final_df.where(mask)['QT. Attuale']
        # Propaga l'ultimo valore valido (ffill)
        final_df[col_name] = final_df[col_name].ffill()

    final_df[state_cols] = final_df[state_cols].fillna(0)
    final_df['QT. Totale'] = np.nan

    # Calcola il totale sommando le colonne di stato appropriate per ogni riga
    for ticker, cols_to_sum in ticker_to_cols_map.items():
        ticker_rows_mask = (final_df['Ticker'] == ticker) & (final_df['QT. Attuale'].notna())
        final_df.loc[ticker_rows_mask, 'QT. Totale'] = final_df[cols_to_sum].sum(axis=1)
    final_df = final_df.drop(columns=state_cols)

    final_df = final_df.drop(columns=["Conto", "QT. Attuale", "Liquidita Attuale", "Liq. Impegnata"])

# 2)
    try:

        # CLEAN/REDO EXCHANGE RATE CHECKS
        prices_df = pd.DataFrame([])

        only_tickers = [t[0] for t in total_tickers]
        print(translator.get("yf.download_historic"))
        prices_df_raw = yf.download(only_tickers, start=start_ref_date, end=end_ref_date, progress=False)
        exch_df = yf.download("USDEUR=X",start=start_ref_date, end=end_ref_date, progress=False)
        
        if not prices_df_raw.empty:
            prices_df = prices_df_raw["Close"]
            exch_df = exch_df["Close"]

            common_dates = prices_df.index.intersection(exch_df.index)
            prices_df = prices_df.loc[common_dates]
            exch_df = exch_df.loc[common_dates]

            # Gestisce il caso di un singolo ticker (restituisce una Serie)
            if isinstance(prices_df, pd.Series):
                prices_df = prices_df.to_frame(name=only_tickers[0] if len(only_tickers) == 1 else "Close")
                
            prices_df = prices_df.dropna()
            exch_df = exch_df.dropna()
            target_index = prices_df.index
            
            if target_index.empty:
                print(translator.get("yf.error_empty_df_na"))
                # Creiamo un indice vuoto per evitare errori successivi
                target_index = pd.date_range(start=start_ref_date, end=end_ref_date)
        else:
            print(translator.get("yf.error_empty_df"))
            target_index = pd.date_range(start=start_ref_date, end=end_ref_date)

    except Exception as e:
        print(translator.get("yf.error_empty_df"))
        target_index = pd.date_range(start=start_ref_date, end=end_ref_date)

    try:
        portfolio_data = final_df.copy()
        portfolio_data.drop(columns=["Valuta"])
        portfolio_data = portfolio_data.sort_values(by='Data', kind="mergesort")

        # Isola i dati sulla liquidità e rimuovi duplicati sulla data, mantenendo l'ultimo record del giorno
        liquidity_sparse = portfolio_data.dropna(subset=['Liquidita Totale'])
        liquidity_sparse = liquidity_sparse.drop_duplicates(subset=['Data'], keep='last')
        liquidity_sparse = liquidity_sparse.set_index('Data')[['Liquidita Totale']]
        liquidity_sparse = liquidity_sparse.rename(columns={'Liquidita Totale': 'Liquidita'})

        immessa_sparse = portfolio_data.dropna(subset=['Liq. Impegnata Totale'])
        immessa_sparse = immessa_sparse.drop_duplicates(subset=['Data'], keep='last')
        immessa_sparse = immessa_sparse.set_index('Data')[['Liq. Impegnata Totale']]
        immessa_sparse = immessa_sparse.rename(columns={'Liq. Impegnata Totale': 'Liquidita Impegnata'})

        # Isola i dati delle quantità dei ticker
        quantities_sparse = portfolio_data.dropna(subset=['Ticker', 'QT. Totale'])
        quantities_sparse = quantities_sparse.drop_duplicates(subset=['Data', 'Ticker'], keep='last')
        
        # Esegui il pivot per avere i ticker come colonne
        quantities_wide_sparse = quantities_sparse.pivot(index='Data', columns='Ticker', values='QT. Totale')

        # Combina i dati di quantità e liquidità per data
        combined_sparse_data = pd.concat([quantities_wide_sparse, liquidity_sparse, immessa_sparse], axis=1)

        for ticker in only_tickers:
            if ticker not in combined_sparse_data.columns:
                combined_sparse_data[ticker] = np.nan

        # Assicura che le colonne Liquidita esistano se non c'erano dati 
        if 'Liquidita' not in combined_sparse_data.columns:
            combined_sparse_data['Liquidita'] = np.nan
        if 'Liquidita Impegnata' not in combined_sparse_data.columns:
            combined_sparse_data['Liquidita Impegnata'] = np.nan

        final_columns = only_tickers + ['Liquidita', 'Liquidita Impegnata']
        combined_sparse_data = combined_sparse_data[final_columns]

        # --- Allineamento all'indice di prices_df ---

        if not target_index.empty:
            # Combina l'indice target (da prices_df) e l'indice dei dati (da portfolio_df)
            # Questo assicura che il forward fill copra correttamente gli intervalli
            combined_index = target_index.union(combined_sparse_data.index).sort_values()

            # Reindicizza ai giorni combinati ed esegui il forward fill (ffill)
            # Questo "porta avanti" l'ultimo valore noto per ogni colonna
            quantities_df_filled = combined_sparse_data.reindex(combined_index).ffill()

            # Seleziona solo le date di prices_df
            portfolio_history_df = quantities_df_filled.loc[target_index]

            # Riempi i NaN dei ticker con 0
            # (per i ticker mai posseduti o per date antecedenti la prima transazione)
            portfolio_history_df[only_tickers] = portfolio_history_df[only_tickers].fillna(0)
            
            # (Opzionale: riempi Liquidita NaN con 0 se preferito, altrimenti ffill dovrebbe averla gestita)
            # portfolio_history_df['Liquidita'] = portfolio_history_df['Liquidita'].fillna(0)
            # portfolio_history_df['Liquidita Impegnata'] = portfolio_history_df['Liquidita Impegnata'].fillna(0)

            # --- Aggiunta Valore Titoli e NAV ---
            if not prices_df.empty:
                if isinstance(prices_df, pd.Series):
                    prices_df_for_calc = prices_df.to_frame(name=only_tickers[0])
                else:
                    # Assicurati che le colonne siano solo i ticker
                    prices_df_for_calc = prices_df[only_tickers]
                
                quantities_for_calc = portfolio_history_df[only_tickers]

                # adjust prices for exchange rate
                for ticker, currency in total_tickers:
                    if currency == "USD":
                        prices_df_for_calc[ticker] = prices_df_for_calc[ticker] * exch_df["USDEUR=X"]
                portfolio_history_df['Valore Titoli'] = (prices_df_for_calc * quantities_for_calc).sum(axis=1)
            else:
                portfolio_history_df['Valore Titoli'] = 0.0
                portfolio_history_df.index.rename("Date", inplace=True)
            
            portfolio_history_df['NAV'] = portfolio_history_df['Valore Titoli'] + portfolio_history_df['Liquidita']
            portfolio_history_df["Cash Flow"] = portfolio_history_df["Liquidita Impegnata"].diff()

            previous_nav = portfolio_history_df['NAV'].shift(1)
            portfolio_history_df["TWRR Giornaliero"] = (
                portfolio_history_df['NAV'] - previous_nav - portfolio_history_df['Cash Flow']
            ) / previous_nav

            portfolio_history_df = portfolio_history_df.iloc[1:]
            portfolio_history_df["TWRR Cumulativo"] = (1 + portfolio_history_df["TWRR Giornaliero"]).cumprod() - 1
            portfolio_history_df = portfolio_history_df.reset_index()

        else:
            final_columns_complete = ["Date"] + total_tickers + ["Liquidita", "Liquidita Impegnata", "Valore Titoli", "NAV", "TWRR Giornaliero", "TWRR Cumulativo"]
            portfolio_history_df = pd.DataFrame(columns=final_columns_complete)
        return portfolio_history_df
        
    except Exception as e:
        print(translator.get("yf.error_generic", e=e))


def aggregate_positions(total_positions):
    """
    Takes as input a "positions" dictionary created by get_asset_value() and returns aggregated data. Let's say I have 
    - {"ticker": "AMZ", "value": 1000.00} on account1
    - {"ticker": "AMZ", "quantity": 454.31} on account2

    The result will be {"ticker": "AMZ", "value": 1454.31} 
    """
    aggr_positions_dict = {}
    for pos in total_positions:
        ticker = pos["ticker"]
        value = pos["value"]
        aggr_positions_dict[ticker] = aggr_positions_dict.get(ticker, 0) + value

    aggr_positions = []
    for ticker, value_sum in aggr_positions_dict.items():
        new_pos = {"ticker": ticker, "value": value_sum}
        aggr_positions.append(new_pos)

    return aggr_positions


def get_asset_value(translator, df, current_ticker=None, ref_date=None, just_assets=False, suppress_progress=False):

    df_copy = df.copy()
    df_copy["Data"] = pd.to_datetime(df_copy["Data"], format="%d-%m-%Y")
    if ref_date:
        df_copy = df_copy[df_copy["Data"] <= ref_date]

    # Rimuove le righe dove la colonna Ticker non ha un valore ed il Ticker corrente
    df_filtered = df_copy.dropna(subset=["Ticker"])
    if current_ticker:
        df_filtered = df_filtered[df_filtered["Ticker"] != current_ticker]

    # Tieni solo le righe con buy e sell (per evitare ticker su dividendi)
    df_filtered = df_filtered[df_filtered["Operazione"].isin(["Acquisto", "Vendita"])]
    # Prendi l'ultima riga per ogni asset unico
    total_assets = df_filtered.groupby("Ticker").last().reset_index()
    # Filtra solo quelli con quantità > 0
    total_active_assets = total_assets.loc[total_assets["QT. Attuale"] > 0, ["Ticker", "QT. Attuale", "Valuta", "PMC"]]

    if just_assets:
        return total_assets, total_active_assets

    if total_active_assets.empty:
        return []

    if not suppress_progress:
        print(translator.get("yf.download_current"))

    positions = []
    tickers = []
    for _, row in total_active_assets.iterrows():
        positions.append({
            "ticker": row["Ticker"],
            "quantity": row["QT. Attuale"],
            "exchange_rate": 1.0 if row["Valuta"] == "EUR" else fetch_exchange_rate(ref_date.strftime("%Y-%m-%d")),
            "price": np.nan,
            "value": np.nan,
            "pmc": row["PMC"]
        })
        tickers.append(row["Ticker"])

    # Download data up to 10 days prior to avoid problems with weekends/holidays
    start_date = pd.to_datetime(ref_date) - pd.Timedelta(days=10)
    end_date = pd.to_datetime(ref_date) + pd.Timedelta(days=1)

    data = yf.download(tickers, start=start_date, end=end_date, progress=False)["Close"]
    data_ref = (
        data.loc[data.index <= pd.to_datetime(ref_date)]  # grab the last available row up until ref_date
            .dropna(how="any")                            # delete rows which have at least 1 NaN
            .iloc[-1]                                     # keep just the last valid data
    )

    for item in positions:
        ticker = item["ticker"]
        price = data_ref[ticker] * item["exchange_rate"]
        item["price"] = price
        item["value"] = item["quantity"] * price

    return positions


def buy_asset(translator, df, asset_rows, quantity, price, conv_rate, fee, ref_date, product, ticker):
    
    price_abs = abs(price) / conv_rate
    fee = round_half_up(fee)
    pmpc = 0
    current_qt = quantity

    # First ever data point for "ticker"
    if asset_rows.empty:                   
        pmpc = (price_abs * quantity + fee) / quantity

    # "ticker" already logged
    else:         
        last_pmpc = asset_rows["PMC"].iloc[-1]
        last_remaining_qt = asset_rows["QT. Attuale"].iloc[-1]

        old_cost = last_pmpc * last_remaining_qt
        new_cost = price_abs * quantity + fee
        current_qt = last_remaining_qt + quantity

        pmpc = ((old_cost + new_cost) / current_qt)

    importo_residuo = pmpc * current_qt

    fiscal_credit_iniziale = compute_backpack(df, ref_date, as_of_index=len(df))
    fiscal_credit_aggiornato = fiscal_credit_iniziale

    # Minusvalenze generated by ETF fee
    minusvalenza_comm = np.nan
    end_date = np.nan

    if product == "ETF":
        minusvalenza_comm = fee
        end_date = add_solar_years(ref_date)
        fiscal_credit_aggiornato += minusvalenza_comm

    current_liq = float(df["Liquidita Attuale"].iloc[-1]) + round_half_up(round_half_up(quantity * price) / conv_rate) - fee
    positions = get_asset_value(translator, df, current_ticker=ticker, ref_date=ref_date)
    asset_value = sum(pos["value"] for pos in positions) + (current_qt * price_abs)
    
    return {
        "Operazione": "Acquisto",
        "QT. Attuale": current_qt,
        "PMC": pmpc,
        "Imp. Residuo Asset": importo_residuo,
        "Costo Rilasciato": np.nan,
        "Plusv. Lorda": np.nan,
        "Minusv. Generata": minusvalenza_comm,
        "Scadenza": end_date,
        "Zainetto Fiscale": fiscal_credit_aggiornato,
        "Plusv. Imponibile": np.nan,
        "Imposta": np.nan,
        "P&L": np.nan,
        "Liquidita Attuale": current_liq,
        "Valore Titoli": asset_value,
        "NAV": current_liq + asset_value
    }


def compute_backpack(df, data_operazione, as_of_index=None):
    """
    Calcola lo zainetto disponibile alla data_operazione considerando
    l'ordine reale delle operazioni (se più operazioni nello stesso giorno
    si rispetta l'ordine di indice).
    - df: dataframe completo
    - data_operazione: datetime della data di riferimento
    - as_of_index: se fornito, considera solo le righe con index < as_of_index
      (utile se il dataframe contiene già la riga corrente e si vuole considerare
       solo la cronologia precedente).
    Ritorna float (credito residuo non negativo).
    """
    history = df.copy()
    history['Data_dt'] = pd.to_datetime(history['Data'], format="%d-%m-%Y")
    # consideriamo solo righe fino alla data_operazione inclusa
    history = history[history['Data_dt'] <= data_operazione].copy()
    if as_of_index is not None:
        history = history.loc[history.index < as_of_index]

    # ordiniamo per data e per indice per rispettare l'ordine reale
    history = history.sort_values(by=['Data_dt']).assign(_orig_index=history.index)
    history = history.sort_values(by=['Data_dt', '_orig_index'])

    # Lista di minus attive: ciascuna è dict {'amount', 'expiry'}
    active_minuses = []

    for _, r in history.iterrows():
        current_date = r['Data_dt']
        # rimuovo minus scadute rispetto alla data corrente
        active_minuses = [m for m in active_minuses if m['expiry'] >= current_date]

        # se la riga ha una minus generata, la aggiungo con la sua scadenza
        if pd.notna(r.get('Minusv. Generata')) and r['Minusv. Generata'] > 0:
            scad = r.get('Scadenza', np.nan)
            if pd.isna(scad):
                expiry_dt = current_date
            else:
                expiry_dt = pd.to_datetime(scad, format="%d-%m-%Y", errors='coerce')
            active_minuses.append({'amount': float(r['Minusv. Generata']), 'expiry': expiry_dt})

        # se la riga ha una plus lorda > 0, la uso per consumare il credito attivo (FIFO)
        if pd.notna(r.get('Plusv. Lorda')) and r['Plusv. Lorda'] > 0:
            to_consume = float(r['Plusv. Lorda'])
            i = 0
            while to_consume > 0 and i < len(active_minuses):
                avail = active_minuses[i]['amount']
                used = min(avail, to_consume)
                active_minuses[i]['amount'] -= used
                to_consume -= used
                if active_minuses[i]['amount'] == 0:
                    i += 1
            # ripulisci elementi a zero
            active_minuses = [m for m in active_minuses if m['amount'] > 0]

    # rimuovo eventuali minus scadute rispetto alla data_operazione
    active_minuses = [m for m in active_minuses if m['expiry'] >= data_operazione]
    total = sum(m['amount'] for m in active_minuses)
    return max(0.0, total)


def sell_asset(translator, df, asset_rows, quantity, price, conv_rate, fee, ref_date, product, ticker, tax_rate=0.26):
    
    try:
        if asset_rows.empty:
            raise ValueError
    except ValueError:
        wrong_input(translator.get("stock.sell_noitems"))
    
    fee = round_half_up(fee)
    last_pmpc = asset_rows["PMC"].iloc[-1]
    last_remaining_qt = asset_rows["QT. Attuale"].iloc[-1]
    
    try:
        if quantity > last_remaining_qt:
            raise ValueError
    except ValueError:
        wrong_input(translator.get("stock.sell_noqt", quantity=quantity, last_remaining_qt=last_remaining_qt))

    importo_effettivo = round_half_up((round_half_up(quantity * price)) / conv_rate) - fee 
    costo_rilasciato = quantity * last_pmpc
    
    plusvalenza_lorda = importo_effettivo - costo_rilasciato        
    
    fiscal_credit_iniziale = compute_backpack(df, ref_date, as_of_index=len(df))
    fiscal_credit_aggiornato = fiscal_credit_iniziale
    plusvalenza_imponibile = 0
    minusvalenza_generata = 0
    minusvalenza_comm = np.nan
    imposta = 0
    end_date = np.nan

    if plusvalenza_lorda > 0:
        plusvalenza_da_compensare = plusvalenza_lorda
        if fiscal_credit_iniziale > 0 and product != "ETF":
            credito_utilizzato = min(plusvalenza_da_compensare, fiscal_credit_iniziale)
            plusvalenza_da_compensare -= credito_utilizzato
            fiscal_credit_aggiornato -= credito_utilizzato
        
        plusvalenza_imponibile = plusvalenza_da_compensare
        imposta = plusvalenza_imponibile * tax_rate
    else:
        # temporary "fix" for BG Saxo (?)
        plusvalenza_lorda = round_down(plusvalenza_lorda)
        
        minusvalenza_generata = abs(plusvalenza_lorda)
        fiscal_credit_aggiornato += minusvalenza_generata
        end_date = add_solar_years(ref_date)

    plusvalenza_netta = plusvalenza_lorda - imposta

    current_qt = last_remaining_qt - quantity
    importo_residuo = last_pmpc * current_qt
    pmpc_residuo = last_pmpc if current_qt > 0 else 0.0

    # Minusvalenze da commissione ETF
    if product == "ETF":
        minusvalenza_comm = fee
        fiscal_credit_aggiornato += minusvalenza_comm
        end_date = add_solar_years(ref_date)
        minusvalenza_generata += minusvalenza_comm

    current_liq = float(df["Liquidita Attuale"].iloc[-1]) + importo_effettivo - round_half_up(imposta)
    positions = get_asset_value(translator, df, current_ticker=ticker, ref_date=ref_date)
    asset_value = sum(pos["value"] for pos in positions) + (current_qt * price)

    return {
        "Operazione": "Vendita",
        "QT. Attuale": current_qt,
        "PMC": pmpc_residuo,
        "Imp. Residuo Asset": importo_residuo,
        "Costo Rilasciato": costo_rilasciato,
        "Plusv. Lorda": plusvalenza_lorda if plusvalenza_lorda > 0 else np.nan,
        "Minusv. Generata": np.nan if minusvalenza_generata == 0 else minusvalenza_generata,
        "Scadenza": end_date,
        "Zainetto Fiscale": fiscal_credit_aggiornato,
        "Plusv. Imponibile": plusvalenza_imponibile if plusvalenza_lorda > 0 else np.nan,
        "Imposta": imposta,
        "P&L": plusvalenza_netta if plusvalenza_lorda > 0 else plusvalenza_lorda,
        "Liquidita Attuale": current_liq,
        "Valore Titoli": asset_value,
        "NAV": current_liq + asset_value
    }


