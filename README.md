# Arca

A multi-broker portfolio tracker and analytics platform built on a transaction ledger.

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

- A **transaction** is one event, such as a buy, deposit or dividend.
- Each transaction has one or more **legs**, where each leg is one movement of cash
  or shares. A buy has a shares leg, a cost leg and sometimes a fee leg.

Holdings and cash balances are calculated from the legs rather than stored, so there
is a single source of truth. Each importer is checked against the app's own balances.

## Goals

1. **One view of all accounts:** Holdings, cash, allocation and performance across
   every app.
2. **Dividend tracking:** Income per month and holding, withholding tax and
   projected annual income.
3. **Analysis:** Risk, returns and comparisons against benchmarks.
4. **Data science:** Clustering, simulation and forecasting experiments, tested
   honestly against simple baselines.

## Status

| Source      | Status    |
|-------------|-----------|
| Trading 212 | Supported |
| Lightyear   | Planned   |
| IBKR        | Planned   |

## Setup

Requires Python 3.

    python -m venv .arca_env
    source .arca_env/bin/activate
    pip install -r requirements.txt
    python init_db.py

## Importing data

1. Export your Trading 212 history as CSV. Each export covers up to one year, so
   you may need several files.
2. Put the files in `data/raw/trading212/`.
3. Run this from the project folder:

       python -m importers.trading212

   Importers run as modules (`-m`) so they can share code in `importers/common.py`.
   `python importers/trading212.py` will not work.

Running the importer again rebuilds the Trading 212 data, so overlapping exports
don't create duplicates.

## Tests

    pytest

## Privacy

Real exports and the database live in `data/`, which is excluded from Git. No
personal financial data is ever committed. Tests use made-up sample files.

## Documentation

- `docs/decisions.md`: Design decisions and why I made them
- Devlog: Weekly progress notes (coming soon)

## License

MIT