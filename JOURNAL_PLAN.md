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
- [x] 4. Migration of existing ledgers, backups, account deletion
- [x] 5. Write path: every operation goes through the journal (same behaviour as today)
- [x] 6. Out-of-order insertion in Operations: **the feature**
- [x] 7. Delete any operation in Transactions
- [x] 8. Edit any operation
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
  - one `download_closes` for all the tickers: one chart per ticker gives both its closes and its adjusted closes;
  - one for the USD→EUR series, only when a currency isn't EUR. That is the same rule `priced_positions` uses to convert.
  - It covers `LOOKBACK` (10 days) before `start` to the day after `end`.
- **Lookups:**
  - `close`, `previous_close` and `usd_eur` (to 6 decimals) take the last value on or before day D, at most `LOOKBACK` older. Otherwise they raise `LookupError`, rather than using an old price (a ticker no longer quoted, a day outside the book).
  - **Except in a book given `known` prices** (a rebuild's, which must not stop for one missing price):
    - `close` then falls back to the latest price on or before D, Yahoo's or a known one, however old. The known prices are the trade prices of the journal (`journal.trade_prices`), or of the ledger being migrated. Only with no price at all does it raise. A known price from before a split would value the asset wrongly after it, but only as a last resort.
    - **Only when Yahoo answers.** If no ticker gets a close and not even the USD→EUR rate comes back, Yahoo can't be reached (e.g. offline), and `download` raises `PricesUnavailable` ("Prices couldn't be downloaded (are you offline?)…"). Otherwise every row rebuilt offline would be valued at an old trade price, and look up to date for good.
  - `name` gives Yahoo's name.
  - Each ticker's series is cleaned once, and lookups use `searchsorted`.
- **`rebuild`** downloads a book, with the journal's trade prices as known prices, when it isn't given `prices`. The book covers the assets the rebuilt rows can hold: those held where the rebuild starts, plus those bought or sold after. A sale in USD of an asset bought in EUR therefore brings the rates in.

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

**`services/migration_service.migrate(accounts) -> {acc_idx: Migration}`** handles every account without a journal and saves nothing. A `Migration` holds the account's journal, its rebuilt ledger, and the `Difference`s found. Each row after the opening row becomes an operation, in the CSV's order (`seq` = position):

- **Deposit / Withdrawal / Dividend / Tax rows:** straightforward (table above, reversed). The charge description comes from `product`, unless it is `Product.TAX`.
- **Transfer In / Out rows:**
  - **Pairing:** each pair gets a shared `transfer_id`, using today's matching rule (`_other_side`'s conditions) across the accounts being migrated. Equal transfers on one day pair in order.
  - **A half already in a journal** whose own other half isn't there (that account was migrated first) gives its `transfer_id` to the matching half being migrated.
  - **Half without a partner** (the account was deleted): it gets a `transfer_id` of its own.
- **Buy / Sell rows:**
  - **Fields from columns:**
    - quantity from `qt_exch`, `conv_rate = float(conv_rate)`, `tax_rate = tax_bracket / 100`;
    - empty cells get the value they meant: `tax_bracket` 26, `conv_rate` 1, `fee` 0, currency EUR;
    - **the price:** `abs(price)` is rounded to 4 decimals. When it doesn't give the stored `nominal_amount`, the amount divided by the shares does (in USD, the amount before conversion, to the cent): that one is used. 1,000 shares at 100.12345 come back at 100.12345, not 100.1235, so a later transfer of all the cash left still fits.
  - **The fee mode is found by trial:**
    - stocks are always "abp";
    - for ETFs, each mode the trade can have (buys "abp", "loss", "pending"; sales "abp", "loss", since "pending" works as "abp" on a sale) goes through `buy_asset` / `sell_asset` on the CSV's rows before it (not a whole row);
    - the one reproducing the most of the stored `abp`, `generated_loss`, `carryforward` and `pending_fees` is kept, the likelier on a tie (with no fee, all match).
- **Split rows:** `qt_exch` keeps the ratio to 6 significant digits ("0.333333" for 1:3, which would leave 9.99999 shares of 30 and refuse a later sale of 10). So the ratio is the first that gives the stored `qt_held` from the shares held before: the nearest fraction of small numbers (1/3), the shares after over before, or `qt_exch`.
- **A row dated before the row above it:** only a split found on Yahoo, which Home recorded after the last operation with its own date. `_late_date` places it:
  - **Normally, on its own date,** before the later operations. Home then finds it near Yahoo's date and doesn't offer it again; moved to a later date, it would be offered and recorded twice.
  - **If its ticker wasn't held yet then** (a split of the day before the first buy): on the day of the first buy, still within a day of Yahoo's.
  - **If rebuilding then refuses an operation** (e.g. a reverse split leaving too few shares for a sale recorded before it): the account is converted again with every such row keeping its place, on the date of the row above, as it was recorded.

  A changed date shows as a difference.
- **Any row that can't become an operation, or be rebuilt** (an unknown operation, a later operation refused), raises `MigrationError` naming the account, the row's date and why. It fails that account alone: `migrate` returns `(migrations, failures)`, and the other accounts are migrated (their transfers to it join its halves when it is migrated later).

One `PriceBook` for all the accounts' assets and history serves the trials and the rebuilds. Its known prices are the accounts' own trade prices, so an asset Yahoo no longer has (delisted, renamed) is valued at the latest price known (see "Prices for a rebuild") instead of blocking the migration. Offline, the book raises `PricesUnavailable` and nothing is migrated.

**Check:** rebuild from the new journal and compare with the original CSV. Every column must match, except the valuations (`assets_value`, `nav`), which depend on Yahoo's data today.
- Each rebuilt row is compared with the row its operation came from (by `op_id` and `seq`), wherever the rebuild placed it.
- Numbers match to a millionth, so 10 read back matches "+10" as written.

An empty `pending_fees` or `tax_bracket` cell (rows written before those columns existed) matches the rebuilt row's 0 or 26. That is what it meant, and those were the only differences in the user's real data.
- **If they match:** save the journals and the rebuilt CSVs (now with `op_id` and `op_hash`).
- **If they don't** (decision 2):
  - A dialog lists the differences for each account, at most 10 then "…and N more". Each line reads like "05-03-2025 · Buy ISP.MI · Eff. Value: -3901.25 → -3901.26", with the column's name and the operation in the user's language.
  - The user continues (the only button; the dialog can't be dismissed), and the rebuilt values are kept.
- **Either way, `AppState.commit_migration` saves:**
  - It first checks that each account still has the ledger its migration was worked out from (`Migration.source`). If one changed meanwhile, it saves nothing and returns False, and the migration is worked out again.
  - It then copies each migrated account's CSV, as it is now, to `before-journal-<account>.csv`. The name can't be an account's ledger, which starts with `report-`. The copy is written under a temporary name first and replaces any copy from an earlier attempt that saved nothing.
  - Finally it saves every account in one `save_accounts` call: all or none.

Saves, and finishing or cleaning one up, share a lock (`account_service._save_lock`), so a save from the migration's thread and one from the screen never delete each other's temporary files.

**When:** at startup, for every account with a CSV but no journal: `AppController.restart` calls `components/journal_migration.migrate_accounts(app, then=show Home)` before Home is shown.
- **Before Home:** nothing else can open a dialog over it or record an operation meanwhile; Home's split prompt and the update notice come after. The dialogs are closed by reference, never with `page.pop_dialog()`, which closes whichever was opened last.
- **While it works:** a modal dialog with a spinner says the accounts are being updated.
- **If it fails,** Home is shown and the next start tries again for the accounts left. After a backup restore it runs again if the backup had no journals.
  - **No prices (offline):** nothing is saved, and a message says so ("are you offline?").
  - **An account's `MigrationError`,** which comes back at every start: the other accounts are saved, then a dialog names that account, the operation's date and why, asking to report it.
- **Since phase 5 it always runs.** Until it succeeds, an account without a journal refuses changes (`journal.not_migrated`).

### Backups and accounts

- **`export_backup`** zips the whole config folder: journals are included with no change.
- **`validate_backup`:**
  - **File names:** each account must have `report-<account>.csv`, or the old `Report <account>.csv` (an old backup; it is renamed at load).
  - **Journals** are optional (old backups). When present, each must be one `journal_from_json` reads, or the backup is refused with `settings.backup.invalid_journal` ("…the backup may come from a newer version of the app").
- **Account deletion** (`AppState.remove_broker` → `account_service.delete_account_files`):
  - deletes `report-<account>.csv`, `journal-<account>.json` and the `before-journal` copy, if present;
  - no old-name CSV is left by then: `prepare_files` renamed it at load.
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

**Phases 4 and 5 go out together.** Once phase 4 migrates the accounts, they all have a journal, and only phase 5's write path can record in them. Until phase 5 was done, the migration was built and tested but not run at startup.

**Running this branch on real data** renames each `Report <account>.csv` to `report-<account>.csv`. A version of the app from before it would no longer find them. Use a copy of the data, or a separate folder (`FLET_APP_STORAGE_DATA`), until the branch is released.

### Phase 4: migration, backups, accounts (done)
- `services/migration_service.py`: `migrate`, with the fee mode found by trial and the transfer pairing.
- `components/journal_migration.py`: the startup migration (spinner, the differences dialog, the failure message) and `AppState.commit_migration` with the `before-journal` copy. It is called from `AppController.restart`, behind `MIGRATE_TO_JOURNAL`, which stayed off until phase 5 removed it.
- `validate_backup`: a journal present must be readable (`settings.backup.invalid_journal`). `delete_account_files` also deletes the `before-journal` copy.
- **Tests** (`test_migration.py`, `test_errors.py`, `test_market_data.py`):
  - each snapshot scenario, recorded row by row and read back from its file, migrates to the very operations it was recorded from, with the "loss" / "abp" fee modes of `ETFS_AND_USD`, and rebuilds the same CSV;
  - recovered values:
    - a price with more than 4 decimals comes back as typed, so a later transfer of all the cash still fits;
    - a 1:3 split comes back as 1/3, so a later sale of all the shares still fits;
  - a split recorded after a later-dated buy keeps its place, its new date the only difference;
  - an asset Yahoo no longer has is valued at its trade price, not blocking the migration. A rebuild's `PriceBook` falls back to the latest price known, Yahoo's or a trade's;
  - transfer pairing:
    - across two accounts, equal ones on one day one to one;
    - a half whose account was deleted gets its own id;
    - a half joins its other half already in a journal;
  - an account changed meanwhile isn't saved over;
  - the differences dialog lists the changed values ("…and N more" on its own line), and continuing saves the journal, the rebuilt ledger and the `before-journal` copy, then shows Home;
  - the working dialog closes even with another dialog opened above it;
  - failures:
    - an operation that can't be converted is named in a dialog, not blamed on the connection;
    - a failed (offline) migration saves nothing and says so;
  - a backup with an unreadable journal is refused. One without journals still validates (phase 3's test).
- **Done manually** on copies of the three `portfolio_backup_*.zip` (live Yahoo prices):
  - every account migrates with no differences, once the empty `pending_fees` / `tax_bracket` cells count as what they meant;
  - the ETF fee modes found: "loss", "pending" and "abp" buys, "loss" sales;
  - through `AppState`, the files are saved with their `before-journal` copies, a fresh start loads them without rebuilding, and a backup with journals validates;
  - the oldest backup's last NAV moves slightly (6271.08 → 6274.34): a valuation, re-priced (decision 7).

### Phase 5: write path through the journal (done)
- **The screens record through the journal.** Each calls `journal_service.record(accounts, account, kind, day, **fields)` or `delete`, then `AppState.commit_changes`:
  - `operations_view`: cash operations, transfers, splits and trades. A dividend's and a trade's asset name is still asked of Yahoo;
  - `home_view`: a split found on Yahoo;
  - `transactions_view`: remove last, which deletes the operation entered last (`journal_service.last_entered`, the highest `seq`), whatever its date. A split found on Yahoo goes on its own past date, and is still the one "remove last" undoes. A second tap while a removal is saving is ignored.

  Dates are still checked as today.
- **`operations_service` only parses forms now:**
  - the `execute_*` functions, `remove_last_operation` and `_other_side` are gone;
  - `parse_cash_amount` returns the amount positive, since the kind gives the sign;
  - `parse_split_ratio` keeps the 0.001–1000 check;
  - `TradeInput.ter` is None when not given.
- **`Operation` checks the currency** (EUR or USD), as `execute_etf_stock` did.
- **`AppState.commit(acc_idx, df)` is removed.**
- **`create_defaults` gives a new account an empty journal.** It never does for an existing ledger without one, since loading would rebuild that ledger from the empty journal, losing it: the migration gives it its journal. With a journal but no ledger, it creates only the ledger.
- **The migration always runs:** the `MIGRATE_TO_JOURNAL` flag is gone, and `restart` migrates whenever an account has no journal.
- **An account whose migration hasn't succeeded** (e.g. the app started offline) refuses changes with `journal.not_migrated`: "… hasn't been updated to the new format yet … The app tries again each time it starts".
- **A transfer whose other account isn't usable** is refused with `journal.partner_unavailable` rather than removed from one account only:
  - the other account isn't migrated (`_other_half`);
  - or it couldn't be loaded (Transactions checks the configured accounts).
- **Splits found on Yahoo** go through `operations_service.check_split_ratio` (0.001–1000), as the form's do.
- **The dividend's ticker** is read when the form is submitted, not later in the background.
- **`create_defaults`** writes a new account's two files on its own, not through `save_accounts`, so another account's stuck save can't stop it. `prepare_files` goes on with the other accounts when one fails.
- **Recording offline** in an account holding assets fails with `PricesUnavailable`, as it did before the journal, instead of saving rows valued at old trade prices (see "Prices for a rebuild").
- **Behaviour that changed, for the better:**
  - **Removing a transfer** whose other half has newer operations in its account is no longer refused (`transactions.transfer_newer_ops` is gone). Both halves go, and the other account's later rows are rebuilt.
  - **A split found on Yahoo** goes on its own date, before any later operation, which is rebuilt. Before, it went after the last operation, out of date order.
- **Tests:**
  - the existing ones, moved to the journal:
    - `test_transfer.py` records and undoes through `record` / `delete`;
    - `test_buy_sell.py` and `test_general_form.py` check the operation each form records (kind, day, fields);
    - `test_split_validation.py` checks `parse_split_ratio`;
    - `conftest.state` holds a journal;
    - `set_operations(state, idx, steps)` replaces `state.commit(idx, ledger)`;
    - `test_migration.py` turns the account back into one from before the journal where it needs one;
  - new ones:
    - `restart` migrates an old-named CSV before Home;
    - `create_defaults` creates an empty journal for a new account, none next to an existing ledger, and keeps a journal whose ledger is missing;
    - an account not migrated can't change;
    - a transfer is undone from both accounts though the other has newer operations;
    - a split found on Yahoo goes on its own date;
  - after the review:
    - a split recorded late keeps its own date (Home doesn't offer it again), or goes on its first buy's day, or keeps its place when its date is refused;
    - one account that can't be migrated doesn't hold back the others;
    - recording offline is refused instead of valued at old trade prices;
    - a transfer whose other account isn't migrated isn't removed by half;
    - "remove last" undoes the operation entered last;
    - a Yahoo split with a wrong ratio is refused;
    - a new account is created though another account's save is stuck.
- **Checked in the app** (web, on a copy of `portfolio_backup_23-10-2026.zip`):
  - the first start migrates silently (no differences) and writes the journals and `before-journal` copies;
  - a deposit and a transfer Fineco → BG Saxo are recorded in the journals (the transfer's halves sharing a `transfer_id`), and undone from Transactions (the confirmation naming both accounts);
  - the accounts end exactly as migrated, and a fresh start loads them without rebuilding.

### Phase 6: out-of-order insertion (done)
- **Dates:** `validate_date(day)` no longer takes the ledger. It refuses only a missing day, a future one, and one before 01-01-2000 (`LEDGER_START_DATE`, the day every account opens on): `misc_errors.date_too_early` replaces `misc_errors.date_sequential`. `last_operation_date` and `_earliest_new_date` are gone, and the Operations pickers offer every day since 2000. `parse_trade` no longer takes `ledger_df`.
- **Recording, in `_record` (`views/operations_view.py`), for every form:**
  1. **Work out the changes** in the background: the ETF/Stock forms' check with Yahoo of the ticker's kind, then `journal_service.record`. So a refusal comes before any question: the operation's own ("Quantity sold … exceeds …"), a later operation it makes impossible (`journal.refused.*`, since phase 1), or a ticker of the wrong kind.
  2. **Ask, when operations come after it.** The count is `journal_service.later_operations(accounts, account, kind, day, **fields)`, which takes `record`'s arguments: a transfer out also counts its counterpart's. Operations on the same day don't count, since the new one goes after them. Rows of a ledger out of step with its journal, rebuilt too, aren't counted: they're only brought back to what the journal says.
     - The question is closed by reference, and answered once (a second tap on Record does nothing). Cancel saves nothing.
     - Locale keys: `journal.insert.{title,one,many,confirm}`, e.g. "Questa operazione precede 20 operazioni successive, che verranno ricalcolate (imposte, Zainetto Fiscale e valori di mercato compresi)". `one` is the singular.
  3. **Save** with `AppState.commit_changes(changes, built_from=journals())`.
  - While the changes are worked out or saved, the form ignores Add (`_recording`), so a second tap doesn't record the operation twice.
- **Two changes at once:** `commit_changes` refuses changes whose accounts have another journal than the one they were worked out from (`built_from`, taken with `AppState.journals()`), with `journal.changed_meanwhile` ("…nothing was saved. Please try again"). Otherwise the second of two changes worked out at once would undo the first, e.g. a deposit recorded while a removal from Transactions is saved. The check and the save hold one lock. Operations, Transactions' "remove last" and Home's splits all pass it.
- **Transfers:**
  - the recipient's last-operation check is gone (`operations.transfer.date_recipient` removed);
  - **the cash a transfer can send** is the least the account holds from its day on (`operations_service.cash_available_on(account, day)`, through `get_pf_date`): on its day, after that day's operations, and on every later row.
    - Later buys and withdrawals aren't checked against the cash (decision 5). So otherwise a transfer in the past could leave them, and the final cash, below zero, which the old check against the last row's cash prevented.
    - Example: 1,000 deposited, then a buy of 501. On a day between them only 499 can be sent.
  - `parse_transfer(source, recipient, day, text)` checks against it. The amount's helper ("Available: …") shows it for the date typed (today's without one), recomputed only when the date changes.
- **A sale's fee panel** (Tax Carryforward mode) reads the pending fees and the average buy price on the sale's date, not after later buys (`_ledger_until`). It is redrawn when the date changes, and only computed while shown.
- **Unchanged:** the lists of assets to sell or split are those held after the last operation. In a consistent history that's enough: an asset sold out later can only be sold earlier together with a forgotten buy, which, recorded first, makes it held at the end again. The quantity shown next to it is the current one.
- **Tests:**
  - `test_past_operations.py`, through the forms:
    - a deposit dated before 8 operations asks first, naming them; Cancel records nothing; recorded, it raises their cash by its amount;
    - a sale leaving a later one short is refused, naming it, with no question, and with the files, journal and ledger unchanged;
    - a transfer dated in the past goes before later operations in both accounts, the question counting both, and the helper showing what can be sent then;
    - a past sale's fee panel uses the pending fees and average buy price of its date;
  - `test_app_state.py`: a change worked out before another was saved is refused, and the first stays saved;
  - updated:
    - a date before 01-01-2000 is refused (`test_general_form`, `test_buy_sell`), and the pickers start at 2000;
    - a transfer is checked against what the account can send from its day on: before a later buy, at most what the buy leaves (`test_transfer`).
- **Checked:**
  - on a copy of `portfolio_backup_23-10-2026.zip` (live prices): a deposit and a transfer in the middle of Fineco's history are recorded (0.3 s and 0.7 s), then deleted, and both ledgers are back as migrated, valuations aside;
  - in the app (web), a transfer Fineco → BG Saxo on 10-03-2026:
    - the helper shows 17.77 €, the least Fineco holds from then on (29.51 € on the day, 24.90 € at the end), and 20 € is refused;
    - for 10 € the question comes once the changes are worked out, about 20 later operations (13 + 7);
    - Cancel leaves both journals unchanged;
    - Record saves it after that day's buy, Fineco's lowest cash from then on becoming 7.77 €.

### Phases 7–8, shared: one way to change the operations
**`components/journal_change.change_accounts(app, work_out, question=, saved_message=, then=, loading=)`** is how every screen changes the operations: Operations recording or editing one, Transactions removing one, Home recording a split found on Yahoo. Phase 6's `_record` became it.
1. **Work out** the changes in the background (`work_out`, e.g. `journal_service.delete`). A refusal is shown instead of any question.
2. **Ask `question`, if any:** a (title, text, confirm label).
   - `ask` opens it on the event loop (`page.run_task`), since it is called from the worker thread, as Home does for its split prompt.
   - It closes it by reference (`components/dialogs.close_dialog`, shared with the migration and the row dialog).
   - It is answered once. Dismissing it (tapping outside, Android's back button) cancels.
3. **Save** with `AppState.commit_changes(changes, built_from=journals())`, show `saved_message`, then run `then` (`app.refresh` by default).
- **One change at a time:** `AppState.changing` replaces the forms' `_recording` and Transactions' `_removing`. It holds from the tap until the change is saved, refused or cancelled, the question included, across every screen. Another change meanwhile isn't made, and says so ("Another change is being saved: try again in a moment", `journal.busy`): e.g. a split recorded from Home while a removal is saving.
- **The counts:** `recalculated_text(t, count, group)` words them, with `group` "journal.insert", "journal.edit" or "journal.delete", each with "one" and "many". In `journal_service`, `later_operations` (record), `later_operations_deleting` and `later_operations_editing` count the operations after the change's earliest place, `(date, seq)`, in both accounts for a transfer (`_count_after`, `_with_other_half`).
- **Public helpers:** `journal_service.find_operation(account, op_id)` (was `_find`), and `transfer_half(accounts, account, op_id)` (was `transfer_partner`, which gave the account only), returning the other account and its half.
- `utils/columns.operation_title(row, t)` names a ledger row's operation, e.g. "Buy ISP.MI" or "Transfer out to: BG Saxo". It titles the row's dialog and the edit banner.

### Phase 7: delete any operation (done)
- **Transactions:** a tap on a row (`DataRow.on_select_change`, with the row's `op_id`, in one account's view or all of them) opens a dialog. It names the operation, its date and account, and offers Cancel, Edit and Remove.
  - A row whose operation isn't in the journal says so (`journal.row_outdated`) and the list is shown again. E.g. it was just removed and the list wasn't shown again yet, or the ledger was left out of step by a rebuild that failed offline.
- **`_remove(account, op)`** is what Remove and "remove last" share; "remove last" still undoes the operation entered last (`last_entered`).
  - **The question** comes only for a transfer ("It will be removed from both A and B") or when operations come after it ("Removing it recalculates 4 other operations (…)"), or both.
  - **A removal that makes a later operation impossible** is refused, naming it, with no question: e.g. removing a buy that a later sale needs.
  - **A transfer** is removed from both accounts. One whose other account isn't loaded is refused (`journal.partner_unavailable`), as in phase 5.
  - **A removal that leaves a later operation short of cash** is refused too (see "Cash after removals and edits" below), e.g. removing the deposit that paid for a buy.
- Locale keys: `journal.delete.{title,one,many,confirm}`.

### Phase 8: edit any operation (done)
- **From Transactions:** Edit on a row's dialog calls `AppController.edit_operation(idx, op_id)`, which sets `AppState.editing` and shows Operations.
  - A transfer in is edited from the account sending it, through its transfer out.
  - A transfer whose other account is gone offers no Edit, only Remove.
  - **Operations shows the edited operation's account** (`_account_idx`), leaving the account picked in `ops_acc_idx` as it was for after the edit.
  - **An edit that can no longer be shown is given up** (`_edited_operation`). That is when the operation is gone from its journal, its ledger has no row for it, or it is a transfer whose other account is gone or not migrated (e.g. deleted in Settings meanwhile).
- **Operations while editing:**
  - only the form recording the operation (`_tab_of`: General, ETF or Stock), under a banner: "Modifica: Acquisto XEON.MI del 16-10-2026", with an X to give up;
  - the account is locked, and so is the kind: the General form hides its kind buttons, the ETF/Stock forms lock the buy/sell switch. A transfer's recipient is locked too.
  - **The form is filled in** (`_fill_in`) with the values as recorded (`_typed` keeps every digit):
    - a sale or split of an asset no longer held gets its ticker added to the list;
    - the ETF fee mode maps back: "pending" on a buy is the Tax Carryforward option's card for later;
    - the fee shows in EUR, as stored;
    - the money-market tax bracket shows as a percentage.
  - The form's handlers that redraw it were split so filling in doesn't update the page: `_show_kind`, `_show_side`, `_show_currency`, `_show_etf_subtype`.
- **Saving** goes through `journal_service.edit(accounts, account, op_id, date=…, **fields)`:
  - for a transfer, only the date and amount (`counterpart` and `transfer_id` can't change);
  - Yahoo's asset name is asked for again only when the ticker changed;
  - the question uses `journal.edit.*` ("The change recalculates 1 other operation (…)", "Save changes");
  - once saved, "Changes saved" shows and Transactions comes back (`AppController.stop_editing`). If the user left Operations while it saved, the tab they went to is only refreshed.
- **An edited operation keeps its place among those of its day** (its order of entry), as its rebuild does. `operations_service.rows_before(account, day, edited)` gives the rows it comes after, leaving out its own row and those of its day entered after it.
  - **The transfer's cash check** uses it: `cash_available_on(account, day, edited)` also counts the cash the transfer already sends as available again.
  - **A sale's fee panel** uses it too: the pending fees and average buy price just before the sale, not after it as the sale's own row says.
- **Leaving Operations** through the navigation bar gives up the edit (`AppController.show_tab` clears `editing`).
- Locale keys: `journal.edit.{action,banner,title,one,many,save,saved}` (`save` is both the button and the question's confirmation, set by `_show_save_button`), `journal.busy`, `journal.row_outdated`, and `journal.changed_meanwhile` (phase 6).

### Cash after removals and edits (decided after phase 8)
**Rule:** a removal or an edit can't leave another operation short of cash, as a transfer out can't (decision 5, extended).
- **Where:** `journal_service.delete` and `edit` rebuild with `keep_cash=True`, and `_refuse_short_of_cash` compares each rebuilt row's cash with the account's ledger before the change, by `op_id`.
- **Refused:** a row that ends below zero but wasn't below zero before raises `journal.short_of_cash`. The message names the account, the cash and the date of the first such row: "This would leave Test Broker short of cash: -1,002.00€ on 03-01-2024".
- **Allowed:**
  - **Rows already below zero, however the change moves them.** Buys and withdrawals aren't checked when recorded, so a history can be short somewhere already, as Fineco's is. It can still be corrected, and a deposit recorded by mistake above a short row can still be undone (first rule, after review: rows lowered while below zero were refused, which blocked that undo).
  - **The edited operation's own row, when it spends cash** (a buy, a withdrawal, a charge), as when recording it. One bringing cash in (a deposit, a dividend, a sale, a transfer in: `_CASH_IN`) is checked like the others: lowering the last deposit can't leave its own row short, as it couldn't with an operation after it.
- **Transfers:** both accounts are checked. Removing or lowering a transfer whose receiver has spent the cash is refused, naming the receiver.
- **Unchanged:** recording a new operation, even dated before others, keeps decision 5: a past-dated withdrawal or buy can still leave later rows below zero.
- **Tests** (`test_journal_service.py`):
  - removing STOCKS_EUR's deposit, or lowering it to 2,000, is refused, naming the first buy left short;
  - raising a deposit under a buy already short is allowed though the buy stays below zero;
  - raising the last withdrawal beyond the cash is allowed on its own row;
  - removing a transfer the receiver has spent is refused, naming the receiver;
  - after review: undoing a deposit recorded above a buy already short is allowed; lowering the last deposit below what was spent is refused on its own row.

**Fixed after the review of phases 7–8, also tested:**
- an edited transfer can send only the cash held before it on its day, not a deposit entered after it that day (`test_transfer.py`);
- a row whose operation is gone says so;
- no other change starts while one waits for its answer, and it says why (`test_transactions_view.py`);
- an edited sale's fee panel counts the fees pending before it;
- an edit whose transfer recipient was deleted is given up instead of failing;
- leaving an edit for Home while it saves keeps Home shown, and the account picked in Operations stays picked (`test_edit_operations.py`).

Tests where a question opens use the `immediately` fixture (`conftest.py`): the page's threads and event-loop tasks run straight away.

**Checked in the app** (web, on a copy of `portfolio_backup_23-10-2026.zip`):
- removing a Fineco deposit is refused, naming −125.10 € on 20-10-2026;
- removing a charge asks about 6 operations, the question opening from the worker thread;
- dismissing it by tapping outside frees the guard (the question opens again), and confirming removes the charge.

**Tests (phases 7–8):**
- `test_transactions_view.py`:
  - a tapped row (the dividend of 15-04-2024) offers Cancel, Edit and Remove; removed, after a question naming 6 operations, their cash drops by its 12.5;
  - removing a buy a later sale needs is refused, naming that sale, with no question and the account unchanged;
  - "remove last" of a split recorded on a past date asks first, since the withdrawal after it is recalculated.
- `test_edit_operations.py`:
  - **every operation of `STOCKS_EUR`, `ETFS_AND_USD` and an ETF buy with its fee pending, opened for editing and saved unchanged, is the very same operation.** So each form shows every value as recorded;
  - the dividend, edited from Transactions to 20, keeps its id and order of entry, adds 7.5 to the later cash after the question, and Transactions is shown again;
  - a buy edited down so a later sale falls short is refused, with no question, and the edit stays open;
  - a transfer picked from the receiving account is edited from the sending one, its recipient locked. Raised from 8,000 to 8,500 of the 8,723.12 held, it is allowed, its own cash counting again, and both halves change.
- **Checked in the app** (web, on a copy of `portfolio_backup_23-10-2026.zip`):
  - a tapped row's dialog: "Acquisto XEON.MI", "16-10-2026 · Fineco", with Annulla, Modifica and Rimuovi;
  - **the edit:** the ETF form filled in (Monetari, quantity, price, fee, mode); the price changed to 150.6 asked about 1 other operation, and was saved with the same id and order of entry (27), Transactions coming back;
  - **removing** a Fineco deposit asked about the 4 operations after it, and rebuilt them;
  - the X gave up an edit, and Operations then opened normally.

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
   - the original CSV is kept as `before-journal-<account>.csv`.
3. **Migration is required.** With decision 2 every account can be migrated, so there's no old in-order code path to maintain.
4. **Same-day position:** a new operation goes after the existing ones on that day.
5. **Cash checks while rebuilding:** today's rules. Only transfers check the cash held; withdrawals and buys don't. Extended after phase 8: removals and edits can't leave another operation short of cash either (see "Cash after removals and edits").
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
