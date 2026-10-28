# Operations journal: plan

Branch: `dev-journal`.

**Goal.** Allow operations to be inserted at any date, not only after the last one. Along the way, allow any operation to be deleted or edited.

**How.** Store what the user did (an *operations journal*), not what it resulted in. The ledger CSVs become a by-product: they are rebuilt from the journal whenever it changes. Everything that reads `account.df` today (Home, Analysis, Transactions, about 35 places) keeps working unchanged, because the CSV keeps its format.

The phases are meant to be implemented one at a time, in order. Each one ends with the app working and the tests passing. Line numbers drift; function names are the reliable reference.

**Status**
- [x] 0. Decisions (see "Decisions" at the end)
- [ ] 1. Journal model and rebuild engine (no app change)
- [ ] 2. Price provider for rebuilds
- [ ] 3. Persistence: new file names, journal files, `op_id` column, saving both files consistently
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
- **Existing data:** when an account's internal CSV still has the old name (`Report <account>.csv` in the resources folder) and no `report-<account>.csv` exists, it is renamed at load. That covers existing installs and old backups.

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
- **A new CSV column, `op_id`, records which operation built the row.** Transactions uses it for delete and edit.
  - It's internal: it's not shown in the Transactions table or exported.
  - So it is *not* added to `utils/columns.py`'s `COLUMNS`, which drives both. It gets its own constant, and `load_single_account` keeps it.

### Rebuilding

A new pure module, **`domain/journal.py`** (no files, no network):
- **The schema:**
  - `Operation` (a frozen dataclass, or a dict validated against the table above);
  - `operation_to_dict` / `operation_from_dict`;
  - `sort_key`.
- **`apply(df, op, broker, prices) -> df`:** dispatches to the `newrow_*` call in the table and returns `df` with one more row, carrying `op_id`.
- **`rebuild(broker, operations, prices, ledger=None, from_index=0) -> df`:**
  - sorts the operations;
  - keeps the opening row plus the first `from_index` rows of `ledger` unchanged;
  - applies the rest in order.

  An operation added in the past only rebuilds from its own position.
- **Checks while rebuilding:** any `ValidationError` raised by `apply` is re-raised naming the operation. The checks are the domain ones that exist today:
  - a sale exceeding the quantity held (`sell_asset`);
  - a split of a ticker not held (`newrow_split`);
  - a transfer out exceeding the cash held. Today only `parse_transfer` checks this, at input time; `apply` must check it too.

  Example of the new message: `journal.later_operation_invalid` = "La vendita di ISP.MI del 05-06-2025 non sarebbe più possibile: {reason}". Withdrawals and buys aren't checked against cash today, and stay unchecked (decision 5).

A service, **`services/journal_service.py`**, does the files and the use cases:
- **Reading and writing journals:** `load_journal(folder, account_name)`, `save_journal(...)`.
- **`record(accounts, account, op) -> {acc_idx: (journal, ledger)}`:** adds the operation (a transfer: both halves, in both accounts, sharing a `transfer_id`) and rebuilds from its position. Nothing is saved; the caller commits.
- **`delete(accounts, account, op_id)`:** for a transfer, both halves.
- **`edit(accounts, account, op_id, new_fields)`:** keeps `id` and `seq`, and rebuilds from the earlier of the old and new positions.

### Prices for a rebuild

**The problem:** `priced_positions` downloads closes (raw and adjusted) for every row, plus the USD→EUR rate for USD assets. A rebuild of 200 rows that way would mean hundreds of requests.

**The fix:** a small **`PriceBook`** (`services/market_data.py`, or a new module):
- built once per rebuild, with one `download_close` for all the journal's tickers (raw + adjusted) and the USD→EUR series, from the earliest date rebuilt minus 10 days to today;
- it answers "close of T on or before D" and "previous close" locally.

It is threaded as an optional `prices=None` argument through `priced_positions`, `newrow_*`, `buy_asset` and `sell_asset`. When it's None, they fetch from Yahoo as today, so Home and Analysis are untouched.

This keeps everything explicit and testable, rather than hiding a cache inside `market_data`.

Rows after the point of a change get today's Yahoo prices, so their `assets_value` / `nav` may differ slightly from what they showed before (decision 7).

### Saving both files consistently

`AppState.commit` becomes `commit(changes: {acc_idx: (journal, ledger)})`. For each account:
1. Write `journal-<account>.json` and `report-<account>.csv` to temporary files.
2. Rename them over the old ones: the journal first, then the CSV.

At startup, `load_single_account` rebuilds the ledger (and saves it) when:
- the CSV is missing;
- the journal is newer than the CSV (by modification time);
- the CSV's `op_id`s don't match the journal (e.g. a crash between the two renames).

### Migration of existing ledgers

Every account is migrated; no old in-order code path is kept (decision 3).

`services/journal_service.migrate_account(ledger_df, accounts)` turns each row after the opening row into an operation, in the CSV's order (`seq` = position):

- **Deposit / Withdrawal / Dividend / Tax rows:** straightforward (table above, reversed). The charge description comes from `product`, unless it is `Product.TAX`.
- **Transfer In / Out rows:**
  - **Pairing:** each pair gets a shared `transfer_id`, using today's matching rule (`_other_side`'s conditions) across all accounts of the user.
  - **Half without a partner** (the account was deleted): it gets a `transfer_id` of its own.
- **Buy / Sell rows:**
  - **Fields from columns:** quantity from `qt_exch`, price = `abs(price)`, `conv_rate = float(conv_rate)`, `tax_rate = tax_bracket / 100`. The price comes back rounded to 4 decimals: lossy, but it's all there is.
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

### Phase 1: journal model and rebuild engine
- `domain/journal.py`: schema, `apply`, `rebuild`, the error naming the operation. For now, prices go through today's `priced_positions` (Yahoo, or the fake market in tests).
- `tests/test_journal.py`:
  - **Round trip:** each snapshot scenario (`STOCKS_EUR`, `ETFS_AND_USD`), written as a journal, rebuilds a ledger identical to `tests/snapshots/*.csv` (ignoring `op_id`).
  - **Order independence:** take each operation out and add it last (the same date, the highest `seq`). The rebuilt ledger is identical.
  - **Refusal:** adding a sale before a later sale that then exceeds the quantity raises, naming the later sale.
- Test helpers: the `deposit` / `buy` / … step builders can produce journal operations, so scenarios are defined once.
- **Done when:** the round trip is byte-identical on both scenarios. **About 250–350 lines** with tests.

### Phase 2: price provider
- `PriceBook`, threaded through as described.
- **Test:** a rebuild of a scenario downloads each ticker once (count the calls to the fake `download_close`), with the same ledger as phase 1.
- **About 100–150 lines.**

### Phase 3: persistence
- **File names:**
  - the new constants and `account_service` functions;
  - `create_defaults` / `load_single_account` / `delete_account_files` on `report-<account>.csv`;
  - the rename of an old `Report <account>.csv` at load;
  - Transactions exports keep `Report <account>.csv` (`export_filename`);
  - `validate_backup` accepts both CSV names.

  The tests that build paths with `REPORT_PREFIX` (`test_create_defaults.py`, `_replay` in `test_ledger_snapshots.py`, `test_app_state.py`) move to the internal name.
- `services/journal_service.py`: load, save, `record`, `delete`, `edit`.
- The `op_id` column; `AppState.commit` saving both files with temporary files and renames; the startup consistency check.
- **Tests:**
  - an old-named CSV is renamed at load;
  - a backup with old names still validates;
  - the export is still named `Report <account>.csv`;
  - the files round-trip;
  - a missing or stale CSV is rebuilt at load;
  - a refused operation leaves both files untouched;
  - transfers are recorded and deleted in both journals by `transfer_id`.
- **About 250–300 lines.**

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
- `operations_view` (cash, transfer, split, trade), `home_view` (split) and `transactions_view` (remove last) build an `Operation` and call `record` / `delete` instead of `execute_*`. Dates are still checked as today.
- The `execute_*` functions remain only as `apply`'s building blocks, or are removed.
- **Tests:** the existing Operations, transfer and transactions tests pass. Their assertions are on the resulting ledgers, which don't change.
- **The app behaves exactly as today.** About 100–150 lines changed.

### Phase 6: out-of-order insertion
- Relaxed date check and pickers, the confirmation with the count, the refusal message. Locale keys: `journal.*`.
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
