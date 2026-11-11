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
in euros.

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
| Valuation over time           | In progress |
| Dashboard                     | Planned     |
| Analysis and data science     | Planned     |

## Project structure

```text
db_files/           schema and views, applied in order by init_db.py
importers/          one importer per broker, plus shared helpers in common.py
market_data/        exchange rates (fx.py) and prices (prices.py)
reference/          example of the instrument reference file
tests/              tests and made-up sample exports in tests/fixtures/
docs/decisions.md   design decisions and why I made them
init_db.py          creates the database
run_imports.py      runs every importer
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

Run everything from the project folder, in this order.

### 1. Import your transactions

Export your history as CSV from each app and put the files in the broker's folder.
Exports often cover up to one year, so you may need several files.

| Broker      | Export                                   | Folder                                            |
|-------------|------------------------------------------|---------------------------------------------------|
| Trading 212 | History → Export (CSV)                   | `data/raw/trading212/`                            |
| Lightyear   | Account statement (CSV)                  | `data/raw/lightyear/`                             |
| IBKR        | Two Flex Queries: Trades, Cash Transactions (CSV) | `data/raw/ibkr/trades/` and `data/raw/ibkr/cash/` |

Then run:

    python run_imports.py

This creates the database if needed and imports only the brokers whose files or
importer code changed since the last import.

| Option    | What it does                                     |
|-----------|--------------------------------------------------|
| `--force` | Re-import every broker                           |
| `--watch` | Keep running and import new files as they arrive |

Each import rebuilds that broker's data from all its files, so overlapping exports
don't create duplicates. You can also run one importer on its own, for example
`python -m importers.trading212`. Importers run as modules (`-m`) so they can share
code in `importers/common.py`.

### 2. Update exchange rates

    python -m market_data.fx

Downloads daily ECB rates from [Frankfurter](https://frankfurter.dev) for every
currency in your ledger, from your first transaction until today.

### 3. Update prices

    python -m market_data.prices

Applies your reference file, then downloads daily prices for every instrument. It
warns if Yahoo's price on your first buy date is far from what you actually paid,
which usually means a wrong ticker or a price quoted in pence.

Both market data scripts cache what they download in `data/raw/`. Add `--offline`
to rebuild the tables from the cache without downloading anything.

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
- **Market data is updated separately** from the imports, by running the two scripts
  above.
- **Prices come from Yahoo Finance** through the unofficial `yfinance` library,
  which can break if Yahoo changes something. The cached files keep earlier
  downloads usable.

## Documentation

- [`docs/decisions.md`](docs/decisions.md): Design decisions and why I made them
- Devlog: Weekly progress notes (coming soon)

## Disclaimer

This is a personal project, not financial advice. The numbers are only as accurate
as the exports and market data behind them.

## License

MIT
