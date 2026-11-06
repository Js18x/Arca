from pathlib import Path
from decimal import Decimal

import duckdb


def test_transaction_legs_can_be_summarized():
    connection = duckdb.connect(database=":memory:")
    schema_file = Path(__file__).parent.parent / "schema.sql"
    connection.execute(schema_file.read_text(encoding="utf-8"))

    connection.execute(
        """
        INSERT INTO accounts (account_id, broker_name, base_currency)
        VALUES (1, 'Lightyear', 'EUR')
        """
    )
    connection.execute(
        """
        INSERT INTO instruments (
            instrument_id, isin, name, asset_type, currency, price_ticker
        )
        VALUES (1, 'US30303M1027', 'Meta Platforms, Inc.', 'Stock', 'USD', 'META')
        """
    )
    connection.execute(
        """
        INSERT INTO transactions (transaction_id, account_id, type, event_date)
        VALUES (1, 1, 'Buy', '2026-01-09')
        """
    )

    connection.execute(
        """
        INSERT INTO transaction_legs (
            transaction_id, leg_number, role, amount, currency,
            instrument_id, source_file, source_id
        )
        VALUES
            (1, 1, 'shares', 0.100900436, NULL, 1, 'test.csv', 'shares-1'),
            (1, 2, 'cost', -65.80, 'USD', NULL, 'test.csv', 'cost-1'),
            (1, 3, 'fee', -0.10, 'USD', NULL, 'test.csv', 'fee-1')
        """
    )

    currency_totals = connection.execute(
        """
        SELECT currency, SUM(amount) AS total
        FROM transaction_legs
        WHERE transaction_id = 1 AND currency IS NOT NULL
        GROUP BY currency
        """
    ).fetchall()
    instrument_totals = connection.execute(
        """
        SELECT instrument_id, SUM(amount) AS total
        FROM transaction_legs
        WHERE transaction_id = 1 AND instrument_id IS NOT NULL
        GROUP BY instrument_id
        """
    ).fetchall()

    assert currency_totals == [("USD", Decimal("-65.9000000000"))]
    assert instrument_totals == [(1, Decimal("0.1009004360"))]

    connection.close()
