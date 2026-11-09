from pathlib import Path
from datetime import datetime

import duckdb

from importers.common import (
    print_account_summary,
    read_csv_rows,
    save_transactions,
    to_decimal,
    unique_by_source_id,
)

from init_db import DATABASE_FILE

ACCOUNT = {
    "account_id": 3,
    "broker_name": "Interactive Brokers",
    "base_currency": "EUR",
}

ASSET_TYPES = {
    "COMMON": "stock",
    "ETF": "etf",
    "REIT": "reit",
}

project_root = Path(__file__).parent.parent
csv_folder = project_root / "data" / "raw" / "ibkr"

def parse_ibkr_date(value):
    return datetime.strptime(value[:8], "%Y%m%d").date() if value else None

def parse_trade_row(row, source_file):
    return {
        "source_file": source_file,
        "transaction_id": row.get("TransactionID"),
        "trade_date": parse_ibkr_date(row["TradeDate"]),
        "settle_date": parse_ibkr_date(row["SettleDateTarget"]),
        "asset_class": row.get("AssetClass"),  # similar to action in trading212
        "sub_category": row.get("SubCategory") or None,
        "symbol": row.get("Symbol"),
        "description": row.get("Description"),  # instrument name
        "isin": row.get("ISIN") or None,
        "currency": row.get("CurrencyPrimary"),
        "quantity": to_decimal(row.get("Quantity")),
        "price": to_decimal(row.get("TradePrice")),
        "proceeds": to_decimal(row.get("Proceeds")),  # cash before commission, or the second currency's amount
        "commission": to_decimal(row.get("IBCommission")),
        "commission_currency": row.get("IBCommissionCurrency"),
        "notes": row.get("Notes/Codes") or None,  # R = reinvestment
    }


def parse_cash_row(row, source_file):
    return {
        "source_file": source_file,
        "transaction_id": row.get("TransactionID"),
        "action_id": row.get("ActionID") or None,  # grouping and group_ref; empty on deposits
        "type": row.get("Type"),  # Dividends, Withholding Tax or Deposits/Withdrawals
        "event_date": parse_ibkr_date(row["Date/Time"]),
        "report_date": parse_ibkr_date(row["ReportDate"]),
        "symbol": row.get("Symbol") or None,
        "description": row.get("Description"),  # instrument name or cash event description
        "isin": row.get("ISIN") or None,
        "sub_category": row.get("SubCategory") or None,
        "currency": row.get("CurrencyPrimary"),
        "amount": to_decimal(row.get("Amount")),
    }


def make_source_id(row):
    if not row["transaction_id"]:
        raise ValueError(f"IBKR row without TransactionID in {row['source_file']}")
    return f"ibkr:{row['transaction_id']}"

def load_trade_rows(folder=csv_folder):
    typed_trade_rows = []
    for source_file, raw in read_csv_rows(folder / "trades"):
        row = parse_trade_row(raw, source_file)
        row["source_id"] = make_source_id(row)
        typed_trade_rows.append(row)

    unique_rows = unique_by_source_id(typed_trade_rows)
    unique_rows.sort(key=lambda x: x["trade_date"])
    return unique_rows

def load_cash_rows(folder=csv_folder):
    typed_cash_rows = []
    for source_file, raw in read_csv_rows(folder / "cash"):
        row = parse_cash_row(raw, source_file)
        row["source_id"] = make_source_id(row)
        typed_cash_rows.append(row)

    unique_rows = unique_by_source_id(typed_cash_rows)
    unique_rows.sort(key=lambda x: x["event_date"])
    return unique_rows

def make_instrument(row, name):
    if not row["isin"]:
        return None

    sub_category = row["sub_category"]
    if sub_category not in ASSET_TYPES:
        raise ValueError(f"Unknown IBKR SubCategory: {sub_category} ({row['isin']})")

    return {
        "isin": row["isin"],
        "name": name,
        "asset_type": ASSET_TYPES[sub_category],
        "currency": row["currency"],
    }

def group_cash_rows(rows):
    groups = {}
    for row in rows:
        key = row["action_id"] or row["source_id"]
        groups.setdefault(key, []).append(row)
    return list(groups.values())

def convert_trade_row(row):
    instrument = make_instrument(row, row["description"])
    is_reinvestment = row["notes"] == "R"
    legs = []

    if row["asset_class"] == "STK":
        if row["quantity"] > 0:
            tx_type = "buy"
            legs.append(
                {
                    "role": "shares",
                    "amount": row["quantity"],
                    "instrument": instrument,
                    "unit_price": row["price"],
                    "price_currency": row["currency"],
                }
            )
            legs.extend([
                {
                    "role": "cost",
                    "amount": row["proceeds"],
                    "currency": row["currency"],
                },
            ])
        else:
            raise ValueError(f"Unexpected negative quantity in IBKR trade row: {row}")
    elif row["asset_class"] == "CASH":
        tx_type = "conversion"
        base, quote = row["symbol"].split(".")
        legs.extend([
        {
            "role": "bought" if row["quantity"] > 0 else "sold",
            "amount": row["quantity"],
            "currency": base,
        },
        {
            "role": "bought" if row["proceeds"] > 0 else "sold",
            "amount": row["proceeds"],
            "currency": quote,
        },
    ])
    else:
        raise ValueError(f"Unknown IBKR AssetClass: {row['asset_class']} ({row['isin']})")

    if row["commission"]:
        legs.append(
            {
                "role": "fee",
                "amount": row["commission"],
                "currency": row["commission_currency"],
            }
        )

    return {
        "source_file": row["source_file"],
        "source_id": row["source_id"],
        "type": tx_type,
        "event_date": row["trade_date"],
        "instrument": instrument,
        "is_reinvestment": is_reinvestment,
        "legs": legs,
    }

CASH_TYPES = ("Dividends", "Withholding Tax", "Deposits/Withdrawals")


def convert_cash_group(rows):
    unknown_types = {r["type"] for r in rows if r["type"] not in CASH_TYPES}
    if unknown_types:
        raise ValueError(f"Unknown IBKR cash row types: {unknown_types}")

    dividend_rows = [r for r in rows if r["type"] == "Dividends"]
    tax_rows = [r for r in rows if r["type"] == "Withholding Tax"]
    transfer_rows = [r for r in rows if r["type"] == "Deposits/Withdrawals"]

    instrument = None
    legs = []
    group_ref = None

    if dividend_rows:
        tx_type = "dividend"
        main_row = dividend_rows[0]
        instrument = make_instrument(main_row, main_row["symbol"])
        group_ref = main_row["action_id"]

        for row in dividend_rows:
            legs.append(
                {
                    "role": "income",
                    "amount": row["amount"],
                    "currency": row["currency"],
                    "source_id": row["source_id"],
                    "source_file": row["source_file"],
                }
            )

        for row in tax_rows:
            legs.append(
                {
                    "role": "tax",
                    "amount": row["amount"],
                    "currency": row["currency"],
                    "source_id": row["source_id"],
                    "source_file": row["source_file"],
                }
            )

    elif tax_rows:
        raise ValueError(f"IBKR cash group with tax but no dividend: {rows}")

    elif transfer_rows:
        main_row = transfer_rows[0]
        tx_type = "deposit" if main_row["amount"] > 0 else "withdrawal"
        legs.append(
            {
                "role": tx_type,
                "amount": main_row["amount"],
                "currency": main_row["currency"],
            }
        )

    return {
        "source_file": main_row["source_file"],
        "source_id": main_row["source_id"],
        "type": tx_type,
        "event_date": main_row["event_date"],
        "instrument": instrument,
        "group_ref": group_ref,
        "legs": legs,
    }


def run(connection):
    """Rebuild this account from its CSV files and return how many transactions were saved."""
    transactions = [convert_trade_row(row) for row in load_trade_rows()]
    transactions += [convert_cash_group(rows) for rows in group_cash_rows(load_cash_rows())]
    save_transactions(connection, ACCOUNT, transactions)
    return len(transactions)


if __name__ == "__main__":
    with duckdb.connect(str(DATABASE_FILE)) as connection:
        count = run(connection)
        print(f"Saved {count} transactions\n")
        print_account_summary(connection, ACCOUNT["account_id"])
