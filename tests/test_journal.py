"""Tests for the operations journal (domain/journal.py): rebuilding a ledger from the operations entered.

The scenarios are those of test_ledger_snapshots.py. Each step there records
an operation the way the app does today and also gives the same operation as
the journal stores it, so a ledger rebuilt from the journal can be compared
with the one recorded step by step.
"""

import json
from dataclasses import replace
from datetime import date

import pytest

from components.snack import error_message
from conftest import fake_download_close
from domain.journal import Operation, OperationRefused, operation_from_dict, operation_to_dict, rebuild
from services import market_data
from test_ledger_snapshots import (BROKER, ETFS_AND_USD, SCENARIOS, STOCKS_EUR, _replay, buy, deposit, journal_of,
                                   sell, withdrawal)
from utils.columns import INTERNAL_COLUMNS, OP_ID


def csv_text(ledger):
    """Return the ledger as the account CSV would hold it, leaving out the columns new with the journal (op_id, op_hash)."""
    return ledger.drop(columns=INTERNAL_COLUMNS).to_csv(index=False)


@SCENARIOS
def test_a_journal_read_back_from_its_file_rebuilds_the_ledger_recorded_today(name, steps, tmp_path, fake_market):
    """A scenario's journal, written as JSON and read back, rebuilds the very CSV that recording its steps gives.

    So the journal keeps every value a row needs (unrounded prices, fee
    modes, tax rates...), and builds each row with the same arguments as the
    Operations screen. Each row's op_id names the operation that built it.
    """
    stored = json.dumps([operation_to_dict(op) for op in journal_of(steps)])
    operations = [operation_from_dict(op) for op in json.loads(stored)]

    ledger = rebuild(BROKER, operations)

    assert csv_text(ledger) == _replay(steps, tmp_path).to_csv(index=False)
    assert list(ledger[OP_ID].iloc[1:]) == [op.id for op in operations]


@pytest.mark.parametrize("steps, late", [
    (STOCKS_EUR, 0),    # the first deposit: the cash of every later row changes
    (ETFS_AND_USD, 3),  # the EEE.MI sale: its fee loss lowers the tax of the later UUU sale
])
def test_an_operation_entered_after_later_ones_takes_its_place_by_date(steps, late, tmp_path, fake_market):
    """Entering one of a scenario's operations last gives the same ledger as entering them in date order.

    The operation is entered after all the others (the highest seq) but keeps
    its date. Starting from the ledger of the others, only the rows from its
    position on are built again, and they must come out as if it had been
    entered in time. E.g. in ETFS_AND_USD, the EEE.MI sale of 01-03-2024
    entered last adds its 5 EUR fee to the carryforward, which then offsets
    part of the gain of the UUU sale of 01-07-2024.
    """
    operations = journal_of(steps)
    entered_late = replace(operations[late], seq=len(operations) + 1)
    others = operations[:late] + operations[late + 1:]
    before = rebuild(BROKER, others)

    after = rebuild(BROKER, others + [entered_late], ledger=before, from_index=late)

    assert csv_text(after) == _replay(steps, tmp_path).to_csv(index=False)


@pytest.mark.parametrize("steps, from_index, downloads", [
    (STOCKS_EUR, 0, [["AAA.MI", "BBB.MI"]]),
    (ETFS_AND_USD, 0, [["EEE.MI", "MMM.MI", "UUU"], ["USDEUR=X"]]),
    # From the last operation (a withdrawal): AAA.MI is sold out by then, only BBB.MI is held.
    (STOCKS_EUR, 11, [["BBB.MI"]]),
])
def test_a_rebuild_downloads_the_prices_once_for_all_its_rows(steps, from_index, downloads, tmp_path, fake_market,
                                                              monkeypatch):
    """Rebuilding downloads the closes of the assets its rows can hold once, and the USD->EUR rates once if needed.

    Recording the steps one by one downloads for every row instead: on a
    phone, rebuilding a few hundred rows that way would take minutes. Only
    the assets held at `from_index`, or traded after, are downloaded, one
    chart each for their closes and adjusted closes. The ledger is the same:
    each row still gets its own day's closes. Each download lists its tickers.
    """
    expected = _replay(steps, tmp_path).to_csv(index=False)
    operations = journal_of(steps)
    ledger = rebuild(BROKER, operations)
    asked = []

    def counting_download_close(tickers, **kwargs):
        """Record which tickers were asked for, then answer like the fake market."""
        asked.append(sorted([tickers] if isinstance(tickers, str) else tickers))
        return fake_download_close(tickers, **kwargs)

    monkeypatch.setattr(market_data, "download_close", counting_download_close)

    rebuilt = rebuild(BROKER, operations, ledger=ledger, from_index=from_index)

    assert asked == downloads
    assert csv_text(rebuilt) == expected


def test_a_sale_in_usd_of_an_asset_bought_in_eur_is_valued_with_the_exchange_rate(tmp_path, fake_market):
    """A rebuild values a sale in USD of an asset bought in EUR as recording it does: with the USD->EUR rate.

    The row's currency is the sale's, so the shares still held are converted
    at the rate, which the rebuild must download although no buy is in USD.
    """
    steps = [deposit(date(2024, 1, 2), 10_000), buy(date(2024, 1, 3), "AAA.MI", 10, price=100.0, fee=2.0),
             sell(date(2024, 2, 1), "AAA.MI", 5, price=120.0, fee=1.0, currency="USD", conv_rate=0.9),
             withdrawal(date(2024, 3, 1), 500)]

    ledger = rebuild(BROKER, journal_of(steps))

    assert csv_text(ledger) == _replay(steps, tmp_path).to_csv(index=False)


def test_a_sale_that_leaves_a_later_sale_short_is_refused_naming_the_later_one(fake_market, translator):
    """Adding a sale before a later one that would then sell more than is held is refused, naming the later sale.

    STOCKS_EUR holds 10 AAA.MI after its sale of 02-04-2024 and sells 5 more
    on 03-06-2024. Selling all 10 on 15-05-2024 leaves none for that sale.
    """
    operations = journal_of(STOCKS_EUR)
    later_sale = operations[8]
    early_sale = Operation(id="early", seq=len(operations) + 1,
                           **sell(date(2024, 5, 15), "AAA.MI", 10, price=95.0, fee=2.0).fields)

    with pytest.raises(OperationRefused) as refused:
        rebuild(BROKER, operations + [early_sale])

    assert refused.value.operation == later_sale
    assert error_message(translator, refused.value).startswith(
        "The sale of AAA.MI on 03-06-2024 would no longer be possible: Quantity sold (5) exceeds available quantity")


def test_a_transfer_out_left_without_the_cash_it_sends_is_refused(fake_market, translator):
    """A withdrawal added before a transfer out, leaving less cash than it sends, is refused, naming the transfer.

    Today only the Operations form checks a transfer's cash, when it is
    entered: a rebuild must check it again. 1,000 EUR deposited and 800 sent
    to Directa on 10-01-2024; withdrawing 500 on 05-01-2024 leaves 500.
    """
    operations = journal_of([deposit(date(2024, 1, 2), 1000), withdrawal(date(2024, 1, 5), 500)])
    transfer = Operation(id="transfer", seq=3, date=date(2024, 1, 10), kind="transfer_out", amount=800.0,
                         counterpart="Directa", transfer_id="t1")

    with pytest.raises(OperationRefused) as refused:
        rebuild(BROKER, operations + [transfer])

    assert refused.value.operation == transfer
    assert error_message(translator, refused.value) == (
        "The transfer to Directa on 10-01-2024 would no longer be possible: Not enough cash available (500.00€)")
