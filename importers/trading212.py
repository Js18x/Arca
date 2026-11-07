from pathlib import Path
from decimal import Decimal
from datetime import datetime

import duckdb

from importers.common import (
    hashed_source_id,
    print_account_summary,
    read_csv_rows,
    save_transactions,
    to_decimal,
    unique_by_source_id,
)
from init_db import DATABASE_FILE

ACCOUNT = {
    "account_id": 1,
    "broker_name": "Trading 212",
    "base_currency": "EUR",
}

project_root = Path(__file__).parent.parent
csv_folder = project_root / "data" / "raw" / "trading212"


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

    return hashed_source_id(
        "t212", row["action"], row["timestamp"].isoformat(), row["isin"], row["total"]
    )


def load_rows(folder=csv_folder):
    typed_rows = []
    for source_file, raw in read_csv_rows(folder):
        row = parse_row(raw, source_file)
        row["source_id"] = make_source_id(row)
        typed_rows.append(row)

    unique_rows = unique_by_source_id(typed_rows)
    unique_rows.sort(key=lambda x: x["timestamp"])
    return unique_rows


def make_instrument(row):
    return {
        "isin": row["isin"],
        "name": row["name"],
        "currency": row["price_currency"],
        "asset_type": "etf",
    }


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
        instrument = make_instrument(row)
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
        instrument = make_instrument(row)
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


if __name__ == "__main__":
    transactions = [convert_row(row) for row in load_rows()]

    with duckdb.connect(str(DATABASE_FILE)) as connection:
        save_transactions(connection, ACCOUNT, transactions)
        print(f"Saved {len(transactions)} transactions\n")
        print_account_summary(connection, ACCOUNT["account_id"])
