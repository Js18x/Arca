from pathlib import Path
from datetime import datetime

import duckdb

from importers.common import (
    print_account_summary,
    read_csv_rows,
    save_transactions,
    to_decimal,
)
from init_db import DATABASE_FILE

ACCOUNT = {
    "account_id": 2,
    "broker_name": "Lightyear",
    "base_currency": "EUR",
}

project_root = Path(__file__).parent.parent
csv_folder = project_root / "data" / "raw" / "lightyear"


def parse_row(row, source_file):
    return {
        "source_file": source_file,
        "reference": row["Reference"],
        "type": row["Type"],
        "timestamp": datetime.strptime(row["Date"], "%d/%m/%Y %H:%M:%S"),
        "ticker": row.get("Ticker") or None,
        "isin": row.get("ISIN") or None,
        "currency": row["CCY"],
        "quantity": to_decimal(row.get("Quantity")),
        "price_per_share": to_decimal(row.get("Price/share")),
        "gross": to_decimal(row.get("Gross Amount")),
        "net": to_decimal(row.get("Net Amt.")),
        "fee": to_decimal(row.get("Fee")),
        "tax": to_decimal(row.get("Tax Amt.")),
        "fx_rate": to_decimal(row.get("FX Rate")),
    }

def make_source_id(row):
    return f"ly:{row['reference']}"


def load_rows(folder=csv_folder):
    typed_rows = []
    for source_file, raw in read_csv_rows(folder):
        row = parse_row(raw, source_file)
        row["source_id"] = make_source_id(row)
        typed_rows.append(row)

    # A conversion is two rows with the same Reference, one per currency,
    # so duplicates are matched on Reference and currency together.
    unique_rows = list(
        {(row["source_id"], row["currency"]): row for row in typed_rows}.values()
    )
    unique_rows.sort(key=lambda x: x["timestamp"])
    return unique_rows


def group_by_reference(rows):
    groups = {}
    for row in rows:
        groups.setdefault(row["source_id"], []).append(row)
    return list(groups.values())


def make_instrument(row):
    if not row["isin"]:
        return None

    return {
        "isin": row["isin"],
        "name": row["ticker"] or row["isin"],
        "asset_type": "stock",
        "currency": row["currency"],
    }


def convert_group(rows):
    row = rows[0]
    legs = []
    instrument = None

    if row["type"] != "Conversion" and len(rows) != 1:
        raise ValueError(
            f"Expected 1 row for {row['type']} {row['reference']}, got {len(rows)}"
        )

    if row["type"] == "Buy":
        tx_type = "buy"
        instrument = make_instrument(row)
        legs.extend([
            {
                "role": "shares",
                "amount": row["quantity"],
                "instrument": instrument,
                "unit_price": row["price_per_share"],
                "price_currency": row["currency"],
            },
            {
                "role": "cost",
                "amount": -row["net"],
                "currency": row["currency"],
            },
        ])
        if row["fee"] and row["fee"] > 0:
            legs.append(
                {
                    "role": "fee",
                    "amount": -row["fee"],
                    "currency": row["currency"],
                }
            )
    elif row["type"] == "Sell":
        tx_type = "sell"
        instrument = make_instrument(row)
        legs.extend([
            {
                "role": "shares",
                "amount": -row["quantity"],
                "instrument": instrument,
                "unit_price": row["price_per_share"],
                "price_currency": row["currency"],
            },
            {
                "role": "proceeds",
                "amount": row["gross"],
                "currency": row["currency"],
            },
        ])
        if row["fee"] and row["fee"] > 0:
            legs.append(
                {
                    "role": "fee",
                    "amount": -row["fee"],
                    "currency": row["currency"],
                }
            )
    elif row["type"] == "Dividend":
        tx_type = "dividend"
        instrument = make_instrument(row)
        legs.append(
            {
                "role": "income",
                "amount": row["gross"],
                "currency": row["currency"],
            }
        )
        if row["tax"] and row["tax"] > 0:
            legs.append(
                {
                    "role": "tax",
                    "amount": -row["tax"],
                    "currency": row["currency"],
                }
            )
    elif row["type"] == "Conversion":
        sold_rows = [r for r in rows if r["net"] < 0]
        bought_rows = [r for r in rows if r["net"] > 0]
        if len(rows) != 2 or len(sold_rows) != 1 or len(bought_rows) != 1:
            raise ValueError(
                f"Expected one negative and one positive row for conversion "
                f"{row['reference']}, got {len(rows)} rows"
            )

        tx_type = "conversion"
        sold_row = sold_rows[0]
        bought_row = bought_rows[0]

        legs.append(
            {
                "role": "sold",
                "amount": sold_row["net"],
                "currency": sold_row["currency"],
            }
        )
        if sold_row["fee"]:
            legs.append(
                {
                    "role": "fee",
                    "amount": -sold_row["fee"],
                    "currency": sold_row["currency"],
                }
            )
        legs.append(
            {
                "role": "bought",
                "amount": bought_row["net"],
                "currency": bought_row["currency"],
            }
        )
    elif row["type"] == "Reward":
        tx_type = "reward"
        legs.append(
            {
                "role": "reward",
                "amount": row["gross"],
                "currency": row["currency"],
            }
        )
    elif row["type"] == "Deposit":
        tx_type = "deposit"
        legs.append(
            {
                "role": "deposit",
                "amount": row["gross"],
                "currency": row["currency"],
            }
        )
    else:
        raise ValueError(f"Unknown type: {row['type']} ({row['reference']})")

    return {
        "source_file": row["source_file"],
        "source_id": row["source_id"],
        "type": tx_type,
        "event_date": row["timestamp"].date(),
        "instrument": instrument,
        "legs": legs,
    }


if __name__ == "__main__":
    transactions = [convert_group(rows) for rows in group_by_reference(load_rows())]

    with duckdb.connect(str(DATABASE_FILE)) as connection:
        save_transactions(connection, ACCOUNT, transactions)
        print(f"Saved {len(transactions)} transactions\n")
        print_account_summary(connection, ACCOUNT["account_id"])
