# Arca

A multi-broker portfolio tracker and analytics platform built on a transaction ledger.

> **Built for my own use.** Arca is shaped around my accounts and how I invest, not
> designed as a general tool. It handles the brokers, transaction types and currencies
> that appear in my own history, and some things are manual, hardcoded or not built
> yet because that's enough for what I need. If you want to use it yourself, expect
> to adapt it. See [Limitations](#limitations) for the details.

## Why I built this

My investments are spread across several brokerage apps. Each app shows its own
slice, but none of them shows the whole picture.

That makes simple questions hard to answer:

- What do I own in total, and how is it split by asset, region and currency?
- How much have I earned in dividends, and how much was withheld in tax?
- How are my individual investment decisions performing against a simple benchmark?

Arca brings every account into one database so I can answer these myself. It's also
a place to learn: I'm writing the code by hand and documenting each week's progress.

## How it works

Every app exports its history in a different format. Arca converts each export into
one shared ledger:

- A **transaction** is one event, such as a buy, deposit, dividend or currency
  conversion.
- Each transaction has one or more **legs**, where each leg is one movement of cash
  or shares. A buy has a shares leg, a cost leg and sometimes a fee leg.

Holdings and cash balances are calculated from the legs rather than stored, so there
is a single source of truth. Each importer is checked against the app's own balances.

Market data is added on top of the ledger: daily exchange rates from the European
Central Bank and daily prices from Yahoo Finance, so every position can be valued
in euros on every day.

```text
broker exports ──► importers/ ──► transactions + legs ─┐
                                                       ├──► DuckDB ──► views
exchange rates, prices ──► market_data/ ───────────────┘
```

## Status

| Part                          | Status      |
|-------------------------------|-------------|
| Trading 212 importer          | Done        |
| Lightyear importer            | Done        |
| IBKR importer                 | Done        |
| Exchange rates (ECB)          | Done        |
| Daily prices (Yahoo Finance)  | Done        |
| Valuation over time           | Done        |
| Analysis functions            | Next        |
| Dashboard                     | Planned     |
| Data science                  | Planned     |

## Project structure

```text
db_files/           schema and views, applied in name order by init_db.py
importers/          one importer per broker, plus shared helpers in common.py
market_data/        exchange rates (fx.py) and prices (prices.py)
reference/          example of the instrument reference file
tests/              tests and made-up sample exports in tests/fixtures/
docs/decisions.md   design decisions and why I made them
init_db.py          creates the database
run_imports.py      runs every importer
update_all.py       runs the importers, then updates exchange rates and prices
data/               your exports, reference file and database (not in Git)
```

## Setup

Requires Python 3 (developed on 3.14).

    python -m venv .arca_env
    source .arca_env/bin/activate
    pip install -r requirements.txt

Then create your instrument reference file from the example:

    mkdir -p data/reference
    cp reference/instruments.example.csv data/reference/instruments.csv

It maps each security's ISIN to its name, type and Yahoo Finance ticker. Add one row
for every security you have ever held. The exports don't always say which exchange
a security trades on, so this mapping is done by hand.

## Usage

Run everything from the project folder.

### Add your exports

Export your history as CSV from each app and put the files in the broker's folder.
Exports often cover up to one year, so you may need several files.

| Broker      | Export                                            | Folder                                            |
|-------------|---------------------------------------------------|---------------------------------------------------|
| Trading 212 | History → Export (CSV)                            | `data/raw/trading212/`                            |
| Lightyear   | Account statement (CSV)                           | `data/raw/lightyear/`                             |
| IBKR        | Two Flex Queries: Trades, Cash Transactions (CSV) | `data/raw/ibkr/trades/` and `data/raw/ibkr/cash/` |

### Update everything

    python update_all.py

This imports any brokers whose files or importer code changed, then updates
exchange rates and prices up to today. It creates the database if needed.

| Option      | What it does                                                  |
|-------------|---------------------------------------------------------------|
| `--offline` | Rebuild exchange rates and prices from the cache, no download |
| `--force`   | Re-import every broker, changed or not                        |

### Run one step on its own

| Step           | Command                         | Notes                                              |
|----------------|---------------------------------|----------------------------------------------------|
| Imports        | `python run_imports.py`         | `--watch` keeps running and imports new files      |
| One importer   | `python -m importers.trading212` | Also `importers.lightyear` and `importers.ibkr`   |
| Exchange rates | `python -m market_data.fx`      | ECB rates from [Frankfurter](https://frankfurter.dev) |
| Prices         | `python -m market_data.prices`  | Applies the reference file first                   |

Each import rebuilds that broker's data from all its files, so overlapping exports
don't create duplicates. Importers and market data scripts run as modules (`-m`) so
they can share code.

The prices script warns if Yahoo's price on your first buy date is far from what you
actually paid, which usually means a wrong ticker or a price quoted in pence. Both
market data scripts cache what they download in `data/raw/` and accept `--offline`.

## What's in the database

The database is `data/arca.duckdb`. These views can be queried like tables, and every
one keeps `account_id`, so any combination of accounts can be selected.

| View                          | What it gives                                                        |
|-------------------------------|----------------------------------------------------------------------|
| `holdings`, `cash_balances`   | Current shares and cash per account                                  |
| `daily_holdings`, `daily_cash` | Shares and cash per account on every day                            |
| `daily_prices`, `daily_fx`    | The latest price and EUR exchange rate on every day                  |
| `daily_valuation`             | The value in EUR of every position and cash balance, per account and day |
| `holding_changes`             | Every buy, sell and reinvestment, with its value                     |
| `transaction_summary`         | One row per transaction                                              |

Markets and the ECB don't publish every day, so weekends and holidays use the latest
available price and rate. `price_date` and `rate_date` show which day they come
from, so values are never mistaken for live ones.

For example, the total value of all accounts over time:

```sql
SELECT date, SUM(value_eur) AS value_eur
FROM daily_valuation
GROUP BY date
ORDER BY date;
```

## Tests

    pytest

The tests use small made-up exports in `tests/fixtures/` and never call an API.

## Privacy

Real exports, the reference file and the database all live in `data/`, which is
excluded from Git. No personal financial data is committed, and the tests use
made-up sample files.

## Limitations

Arca does what I need it to do. Some things are deliberately simple:

- **Manual exports:** Importing starts from CSV files you download yourself. None of
  the broker APIs are used.
- **Only what I've seen:** Each importer handles the transaction types in my own
  history. Anything else, such as an IBKR sell or a Trading 212 dividend with
  withholding tax, stops the import with an error rather than guessing.
- **Hardcoded accounts:** Each broker is one account with a fixed ID, and the base
  currency is EUR.
- **Asset types:** Trading 212 and Lightyear exports don't include them, so they come
  from the reference file.
- **Lightyear deposit fees** are not recorded.
- **Prices come from Yahoo Finance** through the unofficial `yfinance` library,
  which can break if Yahoo changes something. The cached files keep earlier
  downloads usable.
- **Daily closing prices only:** Values are as of the last close, not live.

## Documentation

- [`docs/decisions.md`](docs/decisions.md): Design decisions and why I made them
- Devlog: Weekly progress notes (coming soon)

## Disclaimer

This is a personal project, not financial advice. The numbers are only as accurate
as the exports and market data behind them.

## License

MIT
