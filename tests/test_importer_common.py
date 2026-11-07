from datetime import date
from decimal import Decimal

import duckdb

from importers.common import hashed_source_id, save_transactions, unique_by_source_id
from init_db import apply_sql_files

ACCOUNT = {"account_id": 1, "broker_name": "Test Broker", "base_currency": "EUR"}

INSTRUMENT = {
    "isin": "IE00BFMXXD54",
    "name": "Vanguard S&P 500 (Acc)",
    "currency": "EUR",
    "asset_type": "etf",
}

TRANSACTIONS = [
    {
        "source_file": "test.csv",
        "source_id": "test:1",
        "type": "deposit",
        "event_date": date(2025, 6, 25),
        "instrument": None,
        "legs": [{"role": "deposit", "amount": Decimal("100"), "currency": "EUR"}],
    },
    {
        "source_file": "test.csv",
        "source_id": "test:2",
        "type": "buy",
        "event_date": date(2025, 6, 26),
        "instrument": INSTRUMENT,
        "legs": [
            {
                "role": "shares",
                "amount": Decimal("1.5"),
                "instrument": INSTRUMENT,
                "unit_price": Decimal("60"),
                "price_currency": "EUR",
            },
            {"role": "cost", "amount": Decimal("-90"), "currency": "EUR"},
        ],
    },
]


def test_save_transactions_can_run_twice_without_duplicates():
    connection = duckdb.connect(database=":memory:")
    apply_sql_files(connection)

    save_transactions(connection, ACCOUNT, TRANSACTIONS)
    save_transactions(connection, ACCOUNT, TRANSACTIONS)

    counts = connection.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM transactions),
            (SELECT COUNT(*) FROM transaction_legs),
            (SELECT COUNT(*) FROM instruments)
        """
    ).fetchone()
    assert counts == (2, 3, 1)

    assert connection.execute("SELECT balance FROM cash_balances").fetchall() == [
        (Decimal("10.0000000000"),)
    ]
    assert connection.execute("SELECT quantity FROM holdings").fetchall() == [
        (Decimal("1.5000000000"),)
    ]
    assert connection.execute(
        "SELECT type, instrument_id FROM transactions ORDER BY transaction_id"
    ).fetchall() == [("deposit", None), ("buy", 1)]

    connection.close()


def test_hashed_source_id_is_stable():
    assert hashed_source_id("x", "a", 1) == hashed_source_id("x", "a", 1)
    assert hashed_source_id("x", "a", 1) != hashed_source_id("x", "a", 2)


def test_unique_by_source_id_drops_repeats():
    rows = [{"source_id": "a"}, {"source_id": "b"}, {"source_id": "a"}]
    assert [row["source_id"] for row in unique_by_source_id(rows)] == ["a", "b"]
