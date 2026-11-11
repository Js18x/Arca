"""Daily EUR exchange rates from Frankfurter (ECB data) into fx_rates.

    python -m market_data.fx            download the latest rates, then rebuild fx_rates
    python -m market_data.fx --offline  rebuild fx_rates from the cached file only

Fetches rates for every currency in the ledger since the first transaction,
caches the raw response in data/raw/fx/, then rebuilds fx_rates from that file.
"""

import argparse
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import duckdb
import requests

from init_db import DATABASE_FILE

API_URL = "https://api.frankfurter.dev/v1"
BASE_CURRENCY = "EUR"

project_root = Path(__file__).parent.parent
cache_file = project_root / "data" / "raw" / "fx" / "eur_rates.json"


def first_transaction_date(connection):
    result = connection.execute("SELECT MIN(event_date) FROM transactions").fetchone()[0]
    if result is None:
        raise ValueError("No transactions in the database. Run the importers first.")
    return result


def currencies_needed(connection):
    """Every currency in the ledger except the base currency, sorted."""
    result = connection.execute(
        """
        SELECT currency FROM transaction_legs WHERE currency IS NOT NULL
        UNION
        SELECT price_currency FROM transaction_legs WHERE price_currency IS NOT NULL
        UNION
        SELECT currency FROM instruments
        """
    ).fetchall()

    currencies = []
    for row in result:
        if row[0] != BASE_CURRENCY:
            currencies.append(row[0])
    return sorted(currencies)


def fetch_rates(start, end, currencies, path=cache_file):
    """Download the rates and save the raw response to the cache file."""
    if not currencies:
        raise ValueError("No foreign currencies in the ledger, nothing to fetch.")

    url = f"{API_URL}/{start}..{end}"
    params = {"from": BASE_CURRENCY, "to": ",".join(currencies)}
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(response.text)


def parse_rates(path=cache_file):
    """Turn the cached response into (date, base, quote, rate) rows."""
    data = json.loads(path.read_text(), parse_float=Decimal)
    rows = []
    for day, rates in data["rates"].items():
        for currency, rate in rates.items():
            rows.append((date.fromisoformat(day), BASE_CURRENCY, currency, rate))
    return rows


def save_rates_to_db(connection, rows):
    """Replace every row in fx_rates, all or nothing."""
    connection.begin()
    try:
        connection.execute("DELETE FROM fx_rates")
        connection.executemany(
            """
            INSERT INTO fx_rates (date, base_currency, quote_currency, rate)
            VALUES (?, ?, ?, ?)
            """,
            rows,
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def run(connection, fetch=True, path=cache_file):
    """Rebuild fx_rates and return how many rates were saved.

    With fetch=False, nothing is downloaded: fx_rates is rebuilt from the
    cached file alone, so it works offline or when Frankfurter is down.
    """
    if fetch:
        start = first_transaction_date(connection)
        currencies = currencies_needed(connection)
        fetch_rates(start, date.today(), currencies, path)
    elif not path.exists():
        raise FileNotFoundError(f"No cached rates at {path}. Run once without --offline first.")

    rows = parse_rates(path)
    save_rates_to_db(connection, rows)
    return len(rows)


def print_summary(connection):
    for currency, days, low, high, latest in connection.execute(
        """
        SELECT quote_currency, COUNT(*), MIN(rate), MAX(rate), MAX(date)
        FROM fx_rates
        GROUP BY quote_currency
        ORDER BY quote_currency
        """
    ).fetchall():
        print(f"  {currency}: {days} days, {low:.4f}–{high:.4f}, latest {latest}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rebuild fx_rates from Frankfurter (ECB data).")
    parser.add_argument(
        "--offline", action="store_true", help="don't download; rebuild from the cached file"
    )
    args = parser.parse_args()

    with duckdb.connect(str(DATABASE_FILE)) as connection:
        count = run(connection, fetch=not args.offline)
        source = "cached file" if args.offline else "Frankfurter"
        print(f"Saved {count} FX rates from {source}\n")
        print_summary(connection)
