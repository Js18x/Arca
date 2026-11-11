"""Daily prices from Yahoo Finance (via yfinance) into prices.

    python -m market_data.prices            download the latest prices, then rebuild prices
    python -m market_data.prices --offline  rebuild prices from the cached files only

Applies data/reference/instruments.csv to the instruments table first, fetches
each instrument's prices since its first transaction, caches them as one CSV
per ticker in data/raw/prices/, checks them against your buy prices, then
rebuilds the prices table from the cached files.
"""

import argparse
import csv
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import duckdb
import yfinance as yf

from init_db import DATABASE_FILE

project_root = Path(__file__).parent.parent
reference_file = project_root / "data" / "reference" / "instruments.csv"
cache_folder = project_root / "data" / "raw" / "prices"

# How far Yahoo's close on the first buy date may be from what you paid.
CHECK_TOLERANCE = Decimal("0.15")


def load_reference(path=reference_file):
    """Read the reference file into a dict keyed by ISIN."""
    reference = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            reference[row["isin"]] = row
    return reference


def apply_reference(connection, reference):
    """Overwrite each instrument's name, type, ticker and currency with the reference file's."""
    update_counter = 0
    references_in_db = connection.execute("SELECT isin FROM instruments").fetchall()
    for row in references_in_db:
        isin = row[0]
        if isin not in reference:
            raise ValueError(f"ISIN {isin} in the database but not in the reference file.")

        instrument = reference[isin]
        connection.execute(
            """
            UPDATE instruments
            SET name = ?, asset_type = ?, price_ticker = ?, currency = ?
            WHERE isin = ?
            """,
            (
                instrument["name"],
                instrument["asset_type"],
                instrument["price_ticker"],
                instrument["price_currency"],
                isin,
            ),
        )
        update_counter += 1
    print(f"Updated {update_counter} instruments.")


def instruments_to_price(connection):
    """(instrument_id, price_ticker, currency, first transaction date) for each instrument."""
    return connection.execute(
        """
        SELECT i.instrument_id, i.price_ticker, i.currency, MIN(t.event_date)
        FROM instruments i
        JOIN transactions t ON t.instrument_id = i.instrument_id
        GROUP BY i.instrument_id, i.price_ticker, i.currency
        ORDER BY i.instrument_id
        """
    ).fetchall()


def fetch_prices(ticker, start, end, folder=cache_folder):
    """Download a ticker's daily prices and save them as <ticker>.csv. `end` is exclusive."""
    history = yf.Ticker(ticker).history(start=start, end=end, auto_adjust=False)
    if history.empty:
        raise ValueError(f"No price data found for ticker {ticker} between {start} and {end}.")
    folder.mkdir(parents=True, exist_ok=True)
    history.to_csv(folder / f"{ticker}.csv")


def parse_prices(path, instrument_id, currency):
    """Turn a cached CSV into (instrument_id, date, close, adj_close, currency) rows."""
    data = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            event_date = date.fromisoformat(row["Date"][:10])
            close = Decimal(row["Close"]).quantize(Decimal("0.0001"))
            adj_close = Decimal(row["Adj Close"]).quantize(Decimal("0.0001"))
            data.append((instrument_id, event_date, close, adj_close, currency))
    return data


def first_buys(connection):
    """(instrument_id, price_ticker, date, unit_price) of each instrument's first buy."""
    return connection.execute(
        """
        SELECT l.instrument_id, i.price_ticker, t.event_date, l.unit_price
        FROM transaction_legs l
        JOIN transactions t ON t.transaction_id = l.transaction_id
        JOIN instruments i ON i.instrument_id = l.instrument_id
        WHERE l.role = 'shares' AND l.amount > 0 AND l.unit_price IS NOT NULL
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY l.instrument_id ORDER BY t.event_date, t.transaction_id
        ) = 1
        ORDER BY i.price_ticker
        """
    ).fetchall()


def check_against_trades(connection, rows, tolerance=CHECK_TOLERANCE):
    """Compare Yahoo's close on each first buy date with the price you paid.

    Returns a list of warnings; an empty list means every instrument looks right.
    A large gap usually means a wrong listing or a price in the wrong unit
    (such as pence instead of pounds).
    """
    closes = {(instrument_id, day): close for instrument_id, day, close, _, _ in rows}

    warnings = []
    for instrument_id, ticker, buy_date, unit_price in first_buys(connection):
        # The market may have been closed that day: use the latest close in the week before.
        close = None
        for days_back in range(7):
            key = (instrument_id, buy_date - timedelta(days=days_back))
            if key in closes:
                close = closes[key]
                break

        if close is None:
            warnings.append(f"{ticker}: no price within a week before the first buy on {buy_date}")
            continue

        difference = (close - unit_price) / unit_price
        if abs(difference) > tolerance:
            warnings.append(
                f"{ticker}: paid {unit_price:.2f} on {buy_date}, "
                f"Yahoo close {close:.2f} ({difference:+.0%})"
            )
    return warnings


def save_prices_to_db(connection, rows):
    """Replace every row in prices, all or nothing."""
    connection.begin()
    try:
        connection.execute("DELETE FROM prices")
        connection.executemany(
            """
            INSERT INTO prices (instrument_id, date, close, adj_close, currency)
            VALUES (?, ?, ?, ?, ?)
            """,
            rows,
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def run(connection, fetch=True):
    """Rebuild prices and return how many were saved.

    With fetch=False, nothing is downloaded: prices are rebuilt from the cached files.
    """
    apply_reference(connection, load_reference())

    rows = []
    for instrument_id, ticker, currency, first_date in instruments_to_price(connection):
        path = cache_folder / f"{ticker}.csv"
        if fetch:
            fetch_prices(ticker, first_date, date.today() + timedelta(days=1))
        elif not path.exists():
            raise FileNotFoundError(f"No cached prices for {ticker}. Run once without --offline first.")
        rows += parse_prices(path, instrument_id, currency)

    for warning in check_against_trades(connection, rows):
        print("WARNING:", warning)

    save_prices_to_db(connection, rows)
    return len(rows)


def print_summary(connection):
    for ticker, days, latest, close, currency in connection.execute(
        """
        SELECT i.price_ticker, COUNT(*), MAX(p.date), ARG_MAX(p.close, p.date), i.currency
        FROM prices p
        JOIN instruments i ON i.instrument_id = p.instrument_id
        GROUP BY i.price_ticker, i.currency
        ORDER BY i.price_ticker
        """
    ).fetchall():
        print(f"  {ticker:10} {days:4} days, latest {latest}: {close:.2f} {currency}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rebuild prices from Yahoo Finance.")
    parser.add_argument(
        "--offline", action="store_true", help="don't download; rebuild from the cached files"
    )
    args = parser.parse_args()

    with duckdb.connect(str(DATABASE_FILE)) as connection:
        count = run(connection, fetch=not args.offline)
        source = "cached files" if args.offline else "Yahoo Finance"
        print(f"Saved {count} prices from {source}\n")
        print_summary(connection)
