from pathlib import Path
import csv
import hashlib
from decimal import Decimal
from datetime import datetime

import duckdb

ACCOUNT_ID = 1
BROKER_NAME = "Trading 212"
BASE_CURRENCY = "EUR"

project_root = Path(__file__).parent.parent
csv_folder = project_root / "data" / "raw" / "trading212"
database_file = project_root / "data" / "arca.duckdb"


def read_rows(folder):
    rows = []
    for path in sorted(folder.glob("*.csv")):
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                rows.append((path.name, row))
    return rows


def to_decimal(value):
    return Decimal(value) if value else None


def parse_row(row, source_file):
    return {
        "source_file": source_file,
        "id": row.get("ID") or None,
        "action": row["Action"],
        "timestamp": datetime.fromisoformat(row["Time (UTC)"]),
        "isin": row.get("ISIN") or None,
        "ticker": row.get("Ticker") or None,
        "name": row.get("Name") or None,
        "notes": row.get("Notes") or None,
        "shares": to_decimal(row.get("No. of shares")),
        "price_per_share": to_decimal(row.get("Price / share")),
        "price_currency": row.get("Currency (Price / share)") or None,
        "exchange_rate": to_decimal(row.get("Exchange rate")),
        "total": Decimal(row["Total"]),
        "total_currency": row["Currency (Total)"],
        "withholding_tax": to_decimal(row.get("Withholding tax")),
        "withholding_currency": row.get("Currency (Withholding tax)") or None,
        "conversion_fee": to_decimal(row.get("Currency conversion fee")),
        "conversion_fee_currency": (
            row.get("Currency (Currency conversion fee)") or None
        ),
    }


def make_source_id(row):
    if row["id"]:
        return f"t212:{row['id']}"

    key = f"{row['action']}|{row['timestamp'].isoformat()}|{row['isin']}|{row['total']}"
    return f"t212:{hashlib.sha256(key.encode()).hexdigest()[:16]}"


def load_rows(folder=csv_folder):
    typed_rows = []
    for source_file, raw in read_rows(folder):
        row = parse_row(raw, source_file)
        row["source_id"] = make_source_id(row)
        typed_rows.append(row)

    unique_rows = list({row["source_id"]: row for row in typed_rows}.values())
    unique_rows.sort(key=lambda x: x["timestamp"])
    return unique_rows


def convert_row(row):
    legs = []
    instrument = None

    if row["action"] == "Deposit":
        tx_type = "deposit"
        legs.append(
            {
                "role": "deposit",
                "amount": row["total"],
                "currency": row["total_currency"],
            }
        )
    elif row["action"] == "Market buy":
        fee = row["conversion_fee"] or Decimal("0")
        tx_type = "buy"
        instrument = {
            "isin": row["isin"],
            "name": row["name"],
            "currency": row["price_currency"],
        }
        legs.extend([
            {
                "role": "shares",
                "amount": row["shares"],
                "instrument": instrument,
                "unit_price": row["price_per_share"],
                "price_currency": row["price_currency"],
            },
            {
                "role": "cost",
                "amount": -(row["total"] - fee),
                "currency": row["total_currency"],
            },
        ])
        if fee > 0:
            legs.append(
                {
                    "role": "fee",
                    "amount": -fee,
                    "currency": row["conversion_fee_currency"],
                }
            )
    elif row["action"] == "Dividend (Dividend)":
        if row["withholding_tax"]:
            raise ValueError(f"Withholding tax not handled yet: {row['source_id']}")
        tx_type = "dividend"
        instrument = {
            "isin": row["isin"],
            "name": row["name"],
            "currency": row["price_currency"],
        }
        legs.append(
            {
                "role": "income",
                "amount": row["total"],
                "currency": row["total_currency"],
                "unit_price": row["price_per_share"],
                "price_currency": row["price_currency"],
            }
        )
    else:
        raise ValueError(f"Unknown action: {row['action']}")

    return {
        "source_file": row["source_file"],
        "source_id": row["source_id"],
        "type": tx_type,
        "event_date": row["timestamp"].date(),
        "instrument": instrument,
        "legs": legs,
    }


def get_instrument(connection, instrument):
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
        [new_id, instrument["isin"], instrument["name"], "etf", instrument["currency"]],
    )
    return new_id


def save_transactions(connection, transactions):
    connection.execute(
        """
        INSERT INTO accounts (account_id, broker_name, base_currency)
        VALUES (?, ?, ?)
        ON CONFLICT DO NOTHING
        """,
        [ACCOUNT_ID, BROKER_NAME, BASE_CURRENCY],
    )

    connection.execute(
        """
        DELETE FROM transaction_legs WHERE transaction_id IN
            (SELECT transaction_id FROM transactions WHERE account_id = ?)
        """,
        [ACCOUNT_ID],
    )
    connection.execute(
        "DELETE FROM transactions WHERE account_id = ?",
        [ACCOUNT_ID],
    )

    next_id = connection.execute(
        "SELECT COALESCE(MAX(transaction_id), 0) + 1 FROM transactions"
    ).fetchone()[0]

    for tx_id, tx in enumerate(transactions, start=next_id):
        connection.execute(
            """
            INSERT INTO transactions (transaction_id, account_id, instrument_id, type, event_date)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                tx_id,
                ACCOUNT_ID,
                get_instrument(connection, tx["instrument"]),
                tx["type"],
                tx["event_date"],
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
                    tx["source_file"],
                    tx["source_id"],
                ],
            )


if __name__ == "__main__":
    transactions = [convert_row(row) for row in load_rows()]

    with duckdb.connect(str(database_file)) as connection:
        save_transactions(connection, transactions)

        print(f"Saved {len(transactions)} transactions\n")
        print("Holdings:")
        for isin, name, quantity in connection.execute(
            """
            SELECT i.isin, i.name, h.quantity
            FROM holdings h
            JOIN instruments i ON i.instrument_id = h.instrument_id
            WHERE h.account_id = ?
            ORDER BY i.isin
            """,
            [ACCOUNT_ID],
        ).fetchall():
            print(f"  {isin}  {name}: {quantity}")

        print("Cash:")
        for currency, balance in connection.execute(
            "SELECT currency, balance FROM cash_balances WHERE account_id = ?",
            [ACCOUNT_ID],
        ).fetchall():
            print(f"  {currency}: {balance}")
