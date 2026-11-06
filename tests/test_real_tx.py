from decimal import Decimal

import duckdb
import pytest

from init_db import apply_sql_files


def test_transaction_legs_can_be_summarized():
    connection = duckdb.connect(database=":memory:")
    apply_sql_files(connection)

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
        VALUES (1, 'US30303M1027', 'Meta Platforms, Inc.', 'stock', 'USD', 'META')
        """
    )
    connection.execute(
        """
        INSERT INTO transactions (transaction_id, account_id, type, event_date)
        VALUES (1, 1, 'buy', '2026-01-09')
        """
    )

    connection.execute(
        """
        INSERT INTO transaction_legs (
            transaction_id, leg_number, role, amount, currency,
            instrument_id, source_file, source_id
        )
        VALUES
            (1, 1, 'shares', 0.100900436, NULL, 1, 'test.csv', 'transaction-1'),
            (1, 2, 'cost', -65.80, 'USD', NULL, 'test.csv', 'transaction-1'),
            (1, 3, 'fee', -0.10, 'USD', NULL, 'test.csv', 'transaction-1')
        """
    )

    currency_totals = connection.execute(
        """
        SELECT currency, balance
        FROM cash_balances
        """
    ).fetchall()
    instrument_totals = connection.execute(
        """
        SELECT instrument_id, quantity
        FROM holdings
        """
    ).fetchall()

    assert currency_totals == [("USD", Decimal("-65.9000000000"))]
    assert instrument_totals == [(1, Decimal("0.1009004360"))]

    connection.close()


def test_transaction_leg_requires_currency_or_instrument():
    connection = duckdb.connect(database=":memory:")
    apply_sql_files(connection)

    connection.execute(
        """
        INSERT INTO accounts (account_id, broker_name, base_currency)
        VALUES (1, 'Lightyear', 'EUR')
        """
    )
    connection.execute(
        """
        INSERT INTO transactions (transaction_id, account_id, type, event_date)
        VALUES (1, 1, 'buy', '2026-01-09')
        """
    )

    with pytest.raises(duckdb.ConstraintException):
        connection.execute(
            """
            INSERT INTO transaction_legs (
                transaction_id, leg_number, role, amount,
                source_file, source_id
            )
            VALUES (1, 1, 'invalid', 1, 'test.csv', 'transaction-1')
            """
        )

    connection.close()
