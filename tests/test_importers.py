"""Each importer against small made-up exports in tests/fixtures/.

The fixtures cover the cases that are easy to break: Trading 212's two column
layouts and conversion fees, Lightyear's conversion pairs and overlapping
exports, and IBKR's reinvestments, commissions and tax corrections.
"""

from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from importers import ibkr, lightyear, trading212
from importers.common import save_transactions
from init_db import apply_sql_files

FIXTURES = Path(__file__).parent / "fixtures"


def save(account, transactions):
    connection = duckdb.connect(database=":memory:")
    apply_sql_files(connection)
    save_transactions(connection, account, transactions)
    return connection


def cash(connection):
    return dict(connection.execute("SELECT currency, balance FROM cash_balances").fetchall())


def holdings(connection):
    return dict(
        connection.execute(
            """
            SELECT i.isin, h.quantity
            FROM holdings h
            JOIN instruments i ON i.instrument_id = h.instrument_id
            """
        ).fetchall()
    )


def legs(transaction):
    return [(leg["role"], leg["amount"], leg.get("currency")) for leg in transaction["legs"]]


def by_type(transactions, tx_type):
    return [tx for tx in transactions if tx["type"] == tx_type]


# Trading 212


def trading212_transactions():
    rows = trading212.load_rows(FIXTURES / "trading212")
    return [trading212.convert_row(row) for row in rows]


def test_trading212_reads_both_layouts_and_drops_the_overlap():
    transactions = trading212_transactions()

    # The first dividend is in both files, with different columns.
    assert sorted(tx["type"] for tx in transactions) == ["buy", "deposit", "dividend", "dividend"]
    assert {tx["source_file"] for tx in transactions} == {
        "layout_with_ids.csv",
        "layout_without_ids.csv",
    }


def test_trading212_buy_splits_out_the_conversion_fee():
    (buy,) = by_type(trading212_transactions(), "buy")

    assert buy["source_id"] == "t212:BUY-0001"
    assert legs(buy) == [
        ("shares", Decimal("2.0000000000"), None),
        ("cost", Decimal("-181.85"), "EUR"),
        ("fee", Decimal("-0.15"), "EUR"),
    ]


def test_trading212_balances():
    connection = save(trading212.ACCOUNT, trading212_transactions())

    assert cash(connection) == {"EUR": Decimal("320.00")}
    assert holdings(connection) == {"IE0000000001": Decimal("2")}


def test_trading212_rejects_withholding_tax_until_it_is_handled():
    row = next(
        row
        for row in trading212.load_rows(FIXTURES / "trading212")
        if row["action"] == "Dividend (Dividend)"
    )
    row["withholding_tax"] = Decimal("0.10")

    with pytest.raises(ValueError, match="Withholding tax"):
        trading212.convert_row(row)


# Lightyear


def lightyear_transactions():
    rows = lightyear.load_rows(FIXTURES / "lightyear")
    return [lightyear.convert_group(group) for group in lightyear.group_by_reference(rows)]


def test_lightyear_keeps_both_halves_of_a_conversion_across_overlapping_files():
    transactions = lightyear_transactions()

    assert sorted(tx["type"] for tx in transactions) == [
        "buy", "conversion", "deposit", "dividend", "reward", "sell",
    ]
    (conversion,) = by_type(transactions, "conversion")
    assert legs(conversion) == [
        ("sold", Decimal("-49.80"), "EUR"),
        ("fee", Decimal("-0.20"), "EUR"),
        ("bought", Decimal("57.00"), "USD"),
    ]


def test_lightyear_sell_and_dividend_legs():
    transactions = lightyear_transactions()

    (sell,) = by_type(transactions, "sell")
    assert legs(sell) == [
        ("shares", Decimal("-0.1"), None),
        ("proceeds", Decimal("16.00"), "USD"),
        ("fee", Decimal("-0.10"), "USD"),
    ]

    (dividend,) = by_type(transactions, "dividend")
    assert dividend["instrument"]["isin"] == "US0000000001"
    assert legs(dividend) == [
        ("income", Decimal("0.50"), "USD"),
        ("tax", Decimal("-0.08"), "USD"),
    ]


def test_lightyear_balances():
    connection = save(lightyear.ACCOUNT, lightyear_transactions())

    # The deposit's 0.60 fee isn't taken from the balance: its net is still 100.00.
    assert cash(connection) == {"EUR": Decimal("63.00"), "USD": Decimal("43.32")}
    assert holdings(connection) == {"US0000000001": Decimal("0.1")}


# IBKR


def ibkr_transactions():
    folder = FIXTURES / "ibkr"
    transactions = [ibkr.convert_trade_row(row) for row in ibkr.load_trade_rows(folder)]
    transactions += [
        ibkr.convert_cash_group(group)
        for group in ibkr.group_cash_rows(ibkr.load_cash_rows(folder))
    ]
    return transactions


def test_ibkr_conversion_with_commission():
    (conversion,) = by_type(ibkr_transactions(), "conversion")

    assert legs(conversion) == [
        ("sold", Decimal("-40"), "EUR"),
        ("bought", Decimal("46"), "USD"),
        ("fee", Decimal("-1.7"), "EUR"),
    ]


def test_ibkr_reinvestment_is_flagged():
    buys = by_type(ibkr_transactions(), "buy")

    assert {tx["source_id"]: tx["is_reinvestment"] for tx in buys} == {
        "ibkr:1001": False,
        "ibkr:1002": True,
    }
    assert buys[0]["instrument"]["name"] == "TEST BANCORP INC"


def test_ibkr_dividend_keeps_every_tax_row_including_corrections_from_a_later_file():
    (dividend,) = by_type(ibkr_transactions(), "dividend")

    assert dividend["group_ref"] == "5001"
    assert [(leg["role"], leg["amount"], leg["source_id"], leg["source_file"]) for leg in dividend["legs"]] == [
        ("income", Decimal("0.6"), "ibkr:2001", "cash_1.csv"),
        ("tax", Decimal("-0.09"), "ibkr:2002", "cash_1.csv"),
        ("tax", Decimal("0.09"), "ibkr:2003", "cash_2_tax_correction.csv"),
        ("tax", Decimal("-0.08"), "ibkr:2004", "cash_2_tax_correction.csv"),
    ]


def test_ibkr_balances():
    connection = save(ibkr.ACCOUNT, ibkr_transactions())

    assert connection.execute("SELECT COUNT(*) FROM transactions").fetchone() == (5,)
    assert cash(connection) == {"EUR": Decimal("58.30"), "USD": Decimal("15.9698")}
    assert holdings(connection) == {"US0000000002": Decimal("1.51")}
