# Operations journal: plan

Branch: `dev-journal`.

**Goal.** Allow operations to be inserted at any date, not only after the last one. Along the way, allow any operation to be deleted or edited.

**How.** Store what the user did (an *operations journal*), not what it resulted in. The ledger CSVs become a by-product: they are rebuilt from the journal whenever it changes. Everything that reads `account.df` today (Home, Analysis, Transactions, about 35 places) keeps working unchanged, because the CSV keeps its format.

The phases are meant to be implemented one at a time, in order. Each one ends with the app working and the tests passing. Line numbers drift; function names are the reliable reference.

**Status**
- [x] 0. Decisions (see "Decisions" at the end)
- [x] 1. Journal model and rebuild engine (no app change)
- [x] 2. Price provider for rebuilds
- [x] 3. Persistence: new file names, journal files, `op_id` column, saving both files consistently
- [ ] 4. Migration of existing ledgers, backups, account deletion
- [ ] 5. Write path: every operation goes through the journal (same behaviour as today)
- [ ] 6. Out-of-order insertion in Operations: **the feature**
- [ ] 7. Delete any operation in Transactions
- [ ] 8. Edit any operation
- [ ] 9. Later: recalculate all history; import broker statements

---

## Background: how ledgers work today

- **Each operation adds one row** to its account's CSV, `Report <account>.csv` in the user's resources folder.
  - The same name is used for the CSV the user exports from Transactions (`account_service.report_filename`, `REPORT_PREFIX = "Report "` in `utils/constants.py`).
  - The rows are built by `newrow_cash`, `newrow_etf_stock` and `newrow_split` in `domain/newrow.py`. These call `buy_asset` / `sell_asset` in `domain/tax.py` for trades.
- **Every row is computed from the rows before it:**
  - cash held, committed cash, quantity held, average buy price (`abp`), residual amount and pending fees;
  - carryforward (the zainetto) and its expiry, taxable gain, tax and P&L;
  - a valuation on the row's own date (`assets_value`, `nav`), priced by `priced_positions` (`domain/positions.py`).
- **So no date before the last operation can be accepted.** `validate_date` (`services/validation.py`) refuses it, and the Operations date pickers start at the last operation (`_earliest_new_date` in `views/operations_view.py`).
- **The write paths all end in `AppState.commit(acc_idx, df)`**, which saves the CSV:
  - Operations: cash operations, transfers, splits, trades (`views/operations_view.py`);
  - Home: recording an unrecorded split (`views/home_view.py`);
  - Transactions: removing the last operation (`views/transactions_view.py`).
- **A transfer writes one row in each of the two accounts.** Removing it finds the other half by matching name, date and amount (`_other_side` in `services/operations_service.py`).
- **The test suite already replays ledgers step by step.** `_replay` and the scenarios `STOCKS_EUR` / `ETFS_AND_USD` in `tests/test_ledger_snapshots.py` compare the result with `tests/snapshots/*.csv`. This is the reference for "the journal rebuilds exactly what we build today".

**Inputs that a CSV row doesn't keep exactly**, which is why the journal stores the inputs itself:
- **The fee mode** ("abp", "loss" or "pending", see `buy_asset`) isn't stored at all, yet it decides abp, carryforward and pending fees.
- **The price is stored rounded** to 4 decimals (`round_half_up(signed_price, decimal="0.0001")`), while the amounts were computed from the price as typed.
- **The exchange rate is stored as text** with 6 decimals.
- **Some inputs are encoded in other columns:**
  - the quantity as "+1000" in `qt_exch`;
  - a split's ratio also in `qt_exch`;
  - a charge's description in `product`;
  - a transfer's other account in `asset_name`.

---

## Design

### Files

Per account, in the user's resources folder. Internal files have lowercase, dashed names:
- **`journal-<account>.json`:** the source of truth.
- **`report-<account>.csv`:** the ledger, rebuilt from the journal. It is a cache: it can always be regenerated.

**`Report <account>.csv` is kept only for the CSVs the user exports** from Transactions (and `Report All Accounts.csv`).

In code:
- **Constants** in `utils/constants.py`:
  - `LEDGER_PREFIX = "report-"` and `JOURNAL_PREFIX = "journal-"`;
  - `REPORT_PREFIX = "Report "` stays, for exports only.
- **Functions** in `services/account_service.py`:
  - `ledger_filename` / `ledger_path` for the internal CSV;
  - `journal_filename` / `journal_path`;
  - `export_filename` (today's `report_filename`, renamed) for exports.

  `create_defaults`, `load_single_account`, `delete_account_files` and the backup checks move to the internal names.
- **Existing data:** when an account's internal CSV still has the old name (`Report <account>.csv` in the resources folder) and no `report-<account>.csv` exists, it is renamed. `account_service.prepare_files` does this at the start of `AppState.load_all_accounts`, before creating missing ledgers. That covers existing installs and old backups.

### Journal format

```json
{
  "version": 1,
  "operations": [
    {"id": "3f2a…", "seq": 1, "date": "2025-03-04", "kind": "deposit", "amount": 10000.0},
    {"id": "8c1d…", "seq": 2, "date": "2025-03-05", "kind": "buy", "ticker": "ISP.MI",
     "asset_name": "Intesa Sanpaolo", "product": "Stock", "currency": "EUR", "conv_rate": 1.0,
     "quantity": 1000, "price": 3.9, "fee": 2.95, "fee_mode": "abp", "tax_rate": 0.26, "ter": null},
    {"id": "b0e7…", "seq": 3, "date": "2025-06-10", "kind": "transfer_out", "amount": 100.0,
     "counterpart": "BG Saxo", "transfer_id": "51aa…"}
  ]
}
```

**Common fields**
- **`id`:** a uuid4 hex, fixed for life. It identifies the operation for delete and edit.
- **`seq`:** an integer, the order of entry. It orders operations on the same date. A new operation gets the account's highest `seq` + 1.
- **`date`:** ISO `YYYY-MM-DD`. The CSV keeps its `DD-MM-YYYY`.
- **`kind`:** one of the kinds below.

**Fields by kind.** Amounts are always positive in the journal; the sign is applied when the row is built, as today.

| kind | fields | builds the row with |
|---|---|---|
| `deposit` | `amount` | `newrow_cash(..., +amount, Op.DEPOSIT, Product.CASH, nan, nan)` |
| `withdrawal` | `amount` | `newrow_cash(..., -amount, Op.WITHDRAWAL, ...)` |
| `transfer_out` | `amount`, `counterpart`, `transfer_id` | `newrow_cash(..., -amount, Op.TRANSFER_OUT, Product.CASH, nan, counterpart)` |
| `transfer_in` | `amount`, `counterpart`, `transfer_id` | `newrow_cash(..., +amount, Op.TRANSFER_IN, ...)` |
| `dividend` | `ticker`, `asset_name`, `amount` | `newrow_cash(..., +amount, Op.DIVIDEND, Product.DIVIDEND, ticker, asset_name)` |
| `charge` | `amount`, `description` (or null) | `newrow_cash(..., -amount, Op.TAX, description or Product.TAX, nan, nan)` |
| `buy` / `sell` | `ticker`, `asset_name`, `product`, `currency`, `conv_rate`, `quantity`, `price`, `fee`, `fee_mode`, `tax_rate`, `ter` | `newrow_etf_stock(..., is_buy=kind == "buy", ...)` |
| `split` | `ticker`, `ratio` | `newrow_split(...)` |

- **Values are stored exactly as entered:** price and exchange rate unrounded, fee in EUR as `parse_trade` returns it.
- **`ter`** stays as the text the CSV uses ("0.20%") or null.
- **Reserved for phase 9, not used before:** optional `source` and `external_id` (an imported statement and the broker's own transaction id).

**Order.** Operations are applied sorted by `(date, seq)`. A new operation on a day that already has some goes after them (decision 4). Today's CSVs already store same-day operations in entry order, so nothing changes there.

### The ledger as a cache

- **Every operation builds exactly one row in its account** (a transfer: one in each). So row `k + 1` of the ledger (after the opening row) belongs to the `k`-th operation in `(date, seq)` order.
- **Two new CSV columns record which operation built the row, as it was then:**
  - `op_id`: its id. Transactions uses it for delete and edit;
  - `op_hash`: its `fingerprint`, a short hash of all its values, which changes when it is edited.

  Together they tell which rows are still what the journal builds (`rows_up_to_date`).
  - They're internal: not shown in the Transactions table or exported.
  - So they are *not* in `utils/columns.py`'s `COLUMNS`, which drives both. They have their own constants there: `OP_ID`, `OP_HASH`, `INTERNAL_COLUMNS`. `load_single_account` reads them with the ledger.

### Rebuilding

A new module, **`domain/journal.py`** (no files; the prices come from one download per rebuild):
- **The schema:**
  - `Kind` (a StrEnum of the kinds above) and `KIND_FIELDS` (each kind's fields);
  - `Operation`, a frozen dataclass: id, seq, date, kind, and every kind's fields defaulting to None. It refuses (ValueError) a missing field of its kind, a field of another kind, and values its row couldn't be built from: amount, quantity, price, conv_rate or ratio not above 0, a negative fee, a tax_rate outside 0–1, an unknown fee_mode;
  - `new_id`, `sort_key`, `operation_to_dict` / `operation_from_dict`.
- **`apply(df, op, broker, prices=None) -> df`:** calls the `newrow_*` builder as in the table and returns `df` with one more row, carrying `op_id`.
- **`rebuild(broker, operations, ledger=None, from_index=0, prices=None) -> df`:**
  - sorts the operations;
  - keeps the opening row plus the first `from_index` rows of `ledger` unchanged (without `ledger`, starts from `opening_ledger(broker)`, shared with `create_defaults`);
  - applies the rest in order.

  An operation added in the past only rebuilds from its own position.
- **Checks while rebuilding:** any `ValidationError` raised by `apply` is re-raised as `OperationRefused(operation, reason)`, naming the operation. The checks are the domain ones that exist today:
  - a sale exceeding the quantity held (`sell_asset`);
  - a split of a ticker not held (`newrow_split`);
  - a transfer out exceeding the cash held. Today only `parse_transfer` checks this, at input time; `apply` checks it too.

  Each of these kinds has its message, `journal.refused.<kind>`, e.g. "La vendita di AAA.MI del 03-06-2024 non sarebbe più possibile: {reason}". `components.snack.error_message` translates the `reason` inside it. When the refused operation is the one being recorded, the caller (`record`, phase 3) shows the `reason` alone. Withdrawals and buys aren't checked against cash today, and stay unchecked (decision 5).

A service, **`services/journal_service.py`**, does the journal file format and the use cases:
- **The file format:**
  - `journal_to_json(operations)` writes `{"version": 1, "operations": [...]}`, indented, in order of entry;
  - `journal_from_json(text)` and `read_journal(path)` raise ValueError for another version, an invalid operation, or a repeated id.
- **The use cases.** Each returns `Changes = {acc_idx: (journal, ledger)}` and saves nothing: the caller passes it to `AppState.commit_changes`.
  - **`record(accounts, account, kind, day, **fields)`:**
    - gives the operation a new id and the next `seq`;
    - a transfer out (fields `amount`, `counterpart`) also gets a `transfer_id`, and adds its transfer-in half to the counterpart's journal.
  - **`delete(accounts, account, op_id)`:** a transfer's other half, found by `transfer_id` in any other account, goes too.
  - **`edit(accounts, account, op_id, **new_fields)`:**
    - keeps `id` and `seq`;
    - refuses changing `kind`, `counterpart` or `transfer_id` (delete and record instead);
    - a transfer's new date and amount go to its other half.
- **How much is rebuilt:** each ledger keeps the rows whose `op_id` and `op_hash` still match the start of the new journal, in order (`rows_up_to_date`). That stops at an operation added, deleted or edited. A ledger out of step with its journal (e.g. one whose rebuild failed offline at load) is rebuilt from where they differ, never trusted further.
- **Order:** the account acted on is rebuilt first. For a transfer, that is the sender, which can be short of cash; the receiver's rebuild is skipped when the sender's is refused.
- **Errors:** when rebuilding refuses the operation being recorded or edited, its own error is raised ("Quantity sold (30) exceeds…"). `OperationRefused` is raised only when a later operation is refused.

### Prices for a rebuild

**The problem:** `priced_positions` downloads closes (raw and adjusted) for every row, plus the USD→EUR rate for USD assets. A rebuild of 200 rows that way would mean hundreds of requests.

**The fix:** a small **`PriceBook`** in `services/market_data.py`:
- **`PriceBook.download(tickers_with_currency, start, end)`:**
  - one `download_close` for all the tickers (raw) and one for their adjusted closes;
  - one for the USD→EUR series, only when a currency isn't EUR. That is the same rule `priced_positions` uses to convert.
  - It covers `LOOKBACK` (10 days) before `start` to the day after `end`.
- **Lookups:**
  - `close`, `previous_close` and `usd_eur` (to 6 decimals) take the last value on or before day D, at most `LOOKBACK` older. Otherwise they raise `LookupError`, rather than using an old price (a ticker no longer quoted, a day outside the book).
  - `name` gives Yahoo's name.
  - Each ticker's series is cleaned once, and lookups use `searchsorted`.
- **`rebuild`** downloads a book when it isn't given `prices`. The book covers the assets the rebuilt rows can hold: those held where the rebuild starts, plus those bought or sold after. A sale in USD of an asset bought in EUR therefore brings the rates in.

It is threaded as an optional `prices=None` argument through `priced_positions`, `newrow_*`, `buy_asset`, `sell_asset` and `apply`. When it's None, `priced_positions` downloads a book for its own day, so recording and rebuilding value rows the same way.
- **Home and Analysis:** the USD→EUR rate now comes from the daily series: one request per valuation instead of one per USD asset. Today's daily bar matches the 1-minute rate.
- **Removed:** `fetch_exchange_rate`, which nothing uses any more.
- **VaR snapshot:** updated. Its fake market has a varying rate in the downloaded series but had a constant one in `fetch_exchange_rate`.

Checked on live Yahoo data:
- ISP.MI, AAPL and VWCE.DE closes and the USD→EUR rate, on six days of 2025–2026 including summer Fridays, are identical from a book and from the per-row downloads.
- Today's USD→EUR from the daily series equals the 1-minute chart's.

This keeps everything explicit and testable, rather than hiding a cache inside `market_data`.

Rows after the point of a change get today's Yahoo prices, so their `assets_value` / `nav` may differ slightly from what they showed before (decision 7).

### Saving both files consistently

**`AppState.commit_changes(changes)`** saves through `account_service.save_accounts(folder, {name: (journal, ledger)})`, then updates the accounts in memory. A save covers every file of every account it changes, all or none:
1. **Write:** every file is written in full to `<file>.tmp`, flushed to disk. All the text is made before any file is written. If a write fails (e.g. a full disk), every temporary file is deleted and the error raised: nothing changed, in memory either.
2. **Decide:** a marker, `pending-save.json`, is written listing the files. From then on the save is decided.
3. **Replace:** each file replaces its old one, then the marker is deleted.
   - If the app stops here, `finish_interrupted_save` completes the renames at the next load. So a transfer is never in one account only.
   - A file that can't be replaced yet (e.g. a ledger open in Excel, on Windows) stays listed in the marker and is retried before the next save or load. The save still counts as done, so memory takes it.

`finish_interrupted_save` also deletes temporary files of a save that stopped before deciding.

**`AppState.commit(acc_idx, df)`**, today's, stays only for accounts without a journal (not migrated). It refuses an account that has one, because its ledger saved alone would be rebuilt from the journal at the next load. Phase 5 removes it.

**Loading** (`AppState.load_all_accounts`):
1. **`account_service.prepare_files`:** finishes an interrupted save, renames ledgers saved under the old name, and creates missing ledgers. This replaces `ensure_defaults`.
2. **`load_single_account`, for each account:**
   - It rebuilds the ledger (and saves it) when it doesn't match its journal: missing, or not one row per operation with matching `op_id` and `op_hash`. No file dates are compared, so a restored backup or a wrong clock never triggers a rebuild.
   - If the rebuild fails (no prices offline, a refused operation), the CSV on file is used. The next operation recorded rebuilds every row that doesn't match, and the next load tries again.
   - If only saving fails, the rebuilt ledger is used.
3. **An account that can't be loaded** is left out and logged. That covers a missing ledger, or a journal that can't be read (e.g. written by a newer version). It must not be changed without its journal.

`add_broker` loads only the new account and `remove_broker` drops only the removed one, so neither reloads (or rebuilds) the others.

### Migration of existing ledgers

Every account is migrated; no old in-order code path is kept (decision 3).

`services/journal_service.migrate_account(ledger_df, accounts)` turns each row after the opening row into an operation, in the CSV's order (`seq` = position):

- **Deposit / Withdrawal / Dividend / Tax rows:** straightforward (table above, reversed). The charge description comes from `product`, unless it is `Product.TAX`.
- **Transfer In / Out rows:**
  - **Pairing:** each pair gets a shared `transfer_id`, using today's matching rule (`_other_side`'s conditions) across all accounts of the user.
  - **Half without a partner** (the account was deleted): it gets a `transfer_id` of its own.
- **Buy / Sell rows:**
  - **Fields from columns:** quantity from `qt_exch`, price = `abs(price)`, `conv_rate = float(conv_rate)`, `tax_rate = tax_bracket / 100`. The price comes back rounded to 4 decimals: lossy, but it's all there is. A price that rounds to 0 (under 0.00005) can't make an `Operation`, which refuses values its row couldn't be built from: the migration reports that row.
  - **The fee mode is found by trial:**
    - stocks are always "abp";
    - for ETFs, rebuild that one row with each mode ("abp", "loss", "pending") and keep the one that reproduces the stored `abp`, `generated_loss`, `carryforward` and `pending_fees`.
- **Split rows:** `ratio = float(qt_exch)`.

**Check:** rebuild from the new journal and compare with the original CSV. Every column must match, except the valuations (`assets_value`, `nav`), which depend on Yahoo's data today.
- **If they match:** save the journal and the rebuilt CSV (now with `op_id`).
- **If they don't** (decision 2):
  - Show the differences for that account: the first rows and columns that differ, and by how much (e.g. "riga del 05-03-2025, importo effettivo: -3901.25 → -3901.26").
  - The user accepts the rebuilt values.
  - Before the CSV is replaced, the original is kept next to it as `report-<account>.before-journal.csv`, as a safety copy.

**When:** at startup, for every account with a CSV but no journal, in the background with a spinner. It runs once. After a backup restore it runs again if the backup had no journals.

### Backups and accounts

- **`export_backup`** zips the whole config folder: journals are included with no change.
- **`validate_backup`:**
  - **File names:** each account must have `report-<account>.csv`, or the old `Report <account>.csv` (an old backup; it is renamed at load).
  - **Journals** are optional (old backups). When present, each must be valid JSON with a supported `version` (new `settings.backup.*` messages).
- **Account deletion** (`AppState.remove_broker` → `account_service.delete_account_files`):
  - deletes `report-<account>.csv` and `journal-<account>.json`;
  - also deletes the old-name CSV and the `before-journal` copy, if present.
- **No account rename exists today.** If one is added, its two files are renamed, and the `counterpart` of transfers in other journals with them.

### User interface

- **Operations (phase 6):**
  - The earliest date allowed becomes the first possible day (`LEDGER_START_DATE`), not the last operation. Future dates stay refused.
  - When the date comes before the last operation, a confirmation names the count and what changes: "Questa operazione precede 12 operazioni successive, che verranno ricalcolate (imposte, zainetto e valori di mercato compresi)".
  - A refusal shows the message naming the later operation that would break.
  - Transfers: the recipient's last-operation check (`date_recipient` in `parse_transfer`) goes too.
- **Transactions (phases 7–8):**
  - Tapping a row offers Delete (and later Edit). The row's operation is found by `op_id`.
  - Deleting a transfer asks once and deletes both halves, as removing does today.
  - "Remove last operation" stays, as a shortcut for deleting the newest row (decision 6).
  - Exports keep the name `Report <account>.csv`.
- **Home:** recording an unrecorded split goes through `record` (phase 5). The split's own date is now allowed even if later operations exist.
- **Long rebuilds** run in the background with the existing spinner (`run_in_background`).

---

## Phases

### Phase 1: journal model and rebuild engine (done)
- `domain/journal.py`: schema, `apply`, `rebuild`, `OperationRefused` with its `journal.refused.*` messages. For now, prices go through today's `priced_positions` (Yahoo, or the fake market in tests).
- `tests/test_journal.py`:
  - **Round trip:** each snapshot scenario (`STOCKS_EUR`, `ETFS_AND_USD`), written as a JSON journal and read back, rebuilds the same CSV text as recording its steps (ignoring `op_id`), and each row's `op_id` names its operation.
  - **Entered late:** one operation entered after all the others (the highest `seq`, its own date), rebuilt with `from_index` from the ledger of the others, gives the same ledger. Cases: STOCKS_EUR's first deposit (every row's cash changes); ETFS_AND_USD's EEE.MI sale (its fee loss lowers the later UUU sale's tax).
  - **Refusal:** a sale added before a later sale that then exceeds the quantity is refused, naming the later sale; a withdrawal added before a transfer out that then exceeds the cash is refused, naming the transfer.
- Test helpers: the `deposit` / `buy` / … helpers of `test_ledger_snapshots.py` return a `Step`. It is called as before, and its `fields` give the same operation for the journal, so scenarios are defined once.
- **Done when:** the round trip is byte-identical on both scenarios.

### Phase 2: price provider (done)
- `PriceBook`, threaded through as described.
- **Tests:**
  - A rebuild of each scenario downloads its tickers once (raw and adjusted), plus the USD→EUR rates once for ETFS_AND_USD. The ledger is the same as recording the steps one by one. From the last STOCKS_EUR operation, only BBB.MI (still held) is downloaded.
  - A sale in USD of an asset bought in EUR rebuilds like recording it.
  - `PriceBook` lookups (in `test_market_data.py`): each day's own last close and rate, the split-adjusted previous close, and `LookupError` without a price in the last 10 days.

### Phase 3: persistence (done)
- **File names:**
  - the new constants and `account_service` functions;
  - `create_defaults` / `load_single_account` / `delete_account_files` on `report-<account>.csv`;
  - an old `Report <account>.csv` is renamed in `prepare_files` only, before it creates missing ledgers;
  - Transactions exports, both of an account and of all of them, are named with `export_filename`, still `Report <name>.csv`. `rename_for_export` keeps only `COLUMNS`, leaving the internal columns out;
  - `validate_backup` accepts both CSV names;
  - `delete_account_files` deletes the ledger and the journal.

  The tests that build paths with `REPORT_PREFIX` (`test_create_defaults.py`, `_replay` in `test_ledger_snapshots.py`, `test_app_state.py`, the `state` fixture) moved to the internal name.
- `services/journal_service.py`: the file format, `record`, `delete`, `edit`.
- `Account.journal` (None: not migrated). The `op_id` and `op_hash` columns are read with the ledger.
- `Operation` also checks its values' types: an id that is text, a whole-number `seq`, a day, numbers or text in the other fields (no numpy integers, which the file can't store). A damaged journal file is refused when read, not later when used.
- `AppState.commit_changes` with `save_accounts` (all or none, with a marker); `prepare_files` and the startup consistency check.
- `create_defaults` creates no journal yet: a new account with an empty journal would make the old write path (`commit`) refuse it. New accounts get their journal with phase 4–5.
- **Tests:**
  - `test_account_files.py`:
    - an old-named CSV is renamed before an empty one could hide it;
    - the files round-trip without a rebuild or leftover temporary files;
    - a missing CSV, one built from other operations, or one built before an operation was edited is rebuilt and saved at load, and the next load keeps it;
    - a transfer whose save stopped after deciding is in both accounts at the next load;
    - a save failing while writing changes no file;
    - a ledger that can't be replaced yet is replaced before the next save;
    - an account whose journal can't be read is left out, its files untouched.
  - `test_errors.py`: backups with either CSV name validate.
  - `test_transactions_view.py`: the export is named `Report <account>.csv`, without `op_id`.
  - `test_journal_service.py`:
    - an operation recorded in the past takes its place (same ledger as a full rebuild);
    - a refused operation raises its own error, one breaking a later sale raises `OperationRefused` naming it, and neither changes the account in memory;
    - transfers are recorded in both journals and deleted from both by `transfer_id`;
    - editing a transfer changes both halves;
    - a ledger whose rows were built before an operation was edited is rebuilt from that row when the next operation is recorded;
    - a damaged journal file (another version, a text `seq`, a number id, repeated ids, no date) is refused when read.

**Phases 4 and 5 go out together.** Once phase 4 migrates the accounts, they all have a journal, and only phase 5's write path can record in them. Until phase 5 is done, the migration is built and tested but not run at startup.

**Running this branch on real data** renames each `Report <account>.csv` to `report-<account>.csv`. A version of the app from before it would no longer find them. Use a copy of the data, or a separate folder (`FLET_APP_STORAGE_DATA`), until the branch is released.

### Phase 4: migration, backups, accounts
- `migrate_account`, with the fee mode found by trial and the transfer pairing.
- The startup migration: spinner, the differences dialog with acceptance, the `before-journal` copy.
- Journal checks in `validate_backup`; account deletion of all the account's files.
- **Tests:**
  - each snapshot CSV migrates to a journal that rebuilds it identically (with the fee mode found for every ETF row of `ETFS_AND_USD`);
  - a CSV whose price had more than 4 decimals reports its difference;
  - transfers are paired across two accounts;
  - an old backup without journals still validates and migrates.
- **Manually:** migrate a copy of your real data (the `portfolio_backup_*` folders) and read the differences.
- **About 250–350 lines.**

### Phase 5: write path through the journal
- `operations_view` (cash, transfer, split, trade), `home_view` (split) and `transactions_view` (remove last) call `record(accounts, account, kind, day, **fields)` / `delete` instead of `execute_*`, then `AppState.commit_changes`. Dates are still checked as today.
- `AppState.commit(acc_idx, df)` is removed. `create_defaults` also creates an empty journal for a new account.
- The `execute_*` functions remain only as `apply`'s building blocks, or are removed.
- **Tests:** the existing Operations, transfer and transactions tests pass. Their assertions are on the resulting ledgers, which don't change.
- **The app behaves exactly as today.** About 100–150 lines changed.

### Phase 6: out-of-order insertion
- Relaxed date check and pickers, the confirmation with the count, the refusal message. Locale keys: `journal.*` (the refusal messages, `journal.refused.*`, exist since phase 1).
- **Tests:**
  - a deposit inserted before a trade changes the later rows' cash;
  - a sale inserted early makes a later one impossible: refused, files untouched;
  - a transfer dated in the past rebuilds both accounts.
- **About 100 lines.**

### Phase 7: delete any operation
- Transactions: a tap on a row → Delete, with confirmation (transfers: both halves). "Remove last operation" deletes the newest row through the same code.
- **Test:** deleting a middle deposit rebuilds the later rows. If that makes a later sale impossible, it is refused.
- **About 100–150 lines**, mostly UI.

### Phase 8: edit any operation
- The Operations forms, pre-filled from the operation, saving through `edit`.
- **About 150–250 lines**, mostly UI.

### Phase 9: later
- **Recalculate history:** a Settings action that rebuilds every ledger from its journal after a rule change. It replaces "Re-record every transaction" in TODO.md.
- **Broker statement import:** parse a statement into operations with `source` / `external_id`; skip the ones already in the journal; rebuild once.

---

## Decisions

All decided; each is referred to by its number above.

1. **Journal format:** JSON, as above. It keeps the types, and each kind keeps only its own fields.
2. **Migration mismatch:** when an account's rebuilt ledger doesn't match its CSV (e.g. a price typed with more than 4 decimals moves an amount by a cent):
   - the differences are shown;
   - the user accepts the rebuilt values;
   - the original CSV is kept as `report-<account>.before-journal.csv`.
3. **Migration is required.** With decision 2 every account can be migrated, so there's no old in-order code path to maintain.
4. **Same-day position:** a new operation goes after the existing ones on that day.
5. **Cash checks while rebuilding:** today's rules. Only transfers check the cash held; withdrawals and buys don't.
6. **"Remove last operation" in Transactions** stays, as a shortcut for deleting the newest row.
7. **Valuations of rebuilt rows:** rows after a change are re-priced with today's Yahoo data, and the phase-6 confirmation says so.

## Risks

- **Migration fidelity on real data.** Covered by:
  - the rebuild-and-compare check;
  - the differences dialog;
  - the `before-journal` copy of every replaced CSV.
- **A rebuild changes history.** Later sales' taxes and carryforward are recalculated with the new order. That is correct (it matches what really happened), and the confirmation says so.
- **Two files per account.** The journal is the truth, the CSV a cache that's checked at load. The saves use temporary files and renames.
- **Renaming the internal CSVs.** Old names are renamed at load, and old backups validate with either name. The rename is tested in phase 3, before any journal exists.
- **Long rebuilds on a phone.** They're limited by `from_index` (only rows after the change) and by the price provider (one download per ticker). They run in the background.
- **Offline.** A rebuild needs prices, as recording an operation does today. Without a connection it fails, and nothing is saved.
