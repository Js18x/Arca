"""Helpers shared by all broker importers.

A broker importer turns its export files into transactions shaped like this:

    {
        "source_file": "export.csv",
        "source_id": "t212:EOF34750802264",
        "type": "buy",
        "event_date": date(2025, 6, 26),
        "instrument": {"isin": ..., "name": ..., "currency": ..., "asset_type": ...} or None,
        "legs": [
            {"role": "shares", "amount": ..., "instrument": {...}, "unit_price": ..., "price_currency": ...},
            {"role": "cost", "amount": ..., "currency": "EUR"},
        ],
    }

and then calls save_transactions() with them.
"""

import csv
import hashlib
from decimal import Decimal


def to_decimal(value):
    return Decimal(value) if value else None


def read_csv_rows(folder):
    """Read every CSV in a folder and return (file name, row) pairs."""
    rows = []
    for path in sorted(folder.glob("*.csv")):
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                rows.append((path.name, row))
    return rows


def hashed_source_id(prefix, *parts):
    """Build a stable ID for rows the broker gives no ID of its own."""
    key = "|".join(str(part) for part in parts)
    return f"{prefix}:{hashlib.sha256(key.encode()).hexdigest()[:16]}"


def unique_by_source_id(rows):
    """Drop rows that appear more than once, e.g. in overlapping exports."""
    return list({row["source_id"]: row for row in rows}.values())


def get_instrument(connection, instrument):
    """Return the instrument_id for an ISIN, creating the instrument if needed."""
    if not instrument or not instrument["isin"]:
        return None

    found = connection.execute(
        "SELECT instrument_id FROM instruments WHERE isin = ?",
        [instrument["isin"]],
    ).fetchone()
    if found:
        return found[0]

    new_id = connection.execute(
        "SELECT COALESCE(MAX(instrument_id), 0) + 1 FROM instruments"
    ).fetchone()[0]
    connection.execute(
        """
        INSERT INTO instruments (instrument_id, isin, name, asset_type, currency)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            new_id,
            instrument["isin"],
            instrument["name"],
            instrument["asset_type"],
            instrument["currency"],
        ],
    )
    return new_id


def save_transactions(connection, account, transactions):
    """Replace all of an account's transactions with the ones given, all or nothing.

    `account` is a dict with account_id, broker_name and base_currency. If any
    step fails, everything is rolled back and the account keeps its old data.
    """
    connection.begin()
    try:
        _replace_transactions(connection, account, transactions)
        _check_no_orphan_legs(connection)
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def _check_no_orphan_legs(connection):
    """Stand-in for the foreign key DuckDB can't have here (see docs/decisions.md)."""
    orphans = connection.execute(
        """
        SELECT COUNT(*)
        FROM transaction_legs l
        LEFT JOIN transactions t ON t.transaction_id = l.transaction_id
        WHERE t.transaction_id IS NULL
        """
    ).fetchone()[0]
    if orphans:
        raise ValueError(f"{orphans} transaction legs point to a missing transaction")


def _replace_transactions(connection, account, transactions):
    account_id = account["account_id"]

    connection.execute(
        """
        INSERT INTO accounts (account_id, broker_name, base_currency)
        VALUES (?, ?, ?)
        ON CONFLICT DO NOTHING
        """,
        [account_id, account["broker_name"], account["base_currency"]],
    )

    connection.execute(
        """
        DELETE FROM transaction_legs WHERE transaction_id IN
            (SELECT transaction_id FROM transactions WHERE account_id = ?)
        """,
        [account_id],
    )
    connection.execute(
        "DELETE FROM transactions WHERE account_id = ?",
        [account_id],
    )

    next_id = connection.execute(
        "SELECT COALESCE(MAX(transaction_id), 0) + 1 FROM transactions"
    ).fetchone()[0]

    for tx_id, tx in enumerate(transactions, start=next_id):
        connection.execute(
            """
            INSERT INTO transactions (
                transaction_id, account_id, instrument_id, type, event_date,
                group_ref, is_reinvestment
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                tx_id,
                account_id,
                get_instrument(connection, tx["instrument"]),
                tx["type"],
                tx["event_date"],
                tx.get("group_ref"),
                tx.get("is_reinvestment", False),
            ],
        )
        for leg_number, leg in enumerate(tx["legs"], start=1):
            connection.execute(
                """
                INSERT INTO transaction_legs (
                    transaction_id, leg_number, role, amount, currency,
                    instrument_id, unit_price, price_currency,
                    source_file, source_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    tx_id,
                    leg_number,
                    leg["role"],
                    leg["amount"],
                    leg.get("currency"),
                    get_instrument(connection, leg.get("instrument")),
                    leg.get("unit_price"),
                    leg.get("price_currency"),
                    leg.get("source_file", tx["source_file"]),
                    leg.get("source_id", tx["source_id"]),
                ],
            )


def print_account_summary(connection, account_id):
    print("Holdings:")
    for isin, name, quantity in connection.execute(
        """
        SELECT i.isin, i.name, h.quantity
        FROM holdings h
        JOIN instruments i ON i.instrument_id = h.instrument_id
        WHERE h.account_id = ?
        ORDER BY i.isin
        """,
        [account_id],
    ).fetchall():
        print(f"  {isin}  {name}: {quantity}")

    print("Cash:")
    for currency, balance in connection.execute(
        "SELECT currency, balance FROM cash_balances WHERE account_id = ?",
        [account_id],
    ).fetchall():
        print(f"  {currency}: {balance}")
