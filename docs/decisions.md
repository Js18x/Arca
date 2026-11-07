# Decisions

Short notes on design choices and why I made them.

## Transactions are made of legs
Each transaction has one or more legs, and each leg is one movement of cash or
shares. A buy is a shares leg, a cost leg and sometimes a fee leg. One structure
fits buys, dividends, fees and currency conversions from every app, where fixed
columns or a separate conversions table would not.

## DuckDB instead of PostgreSQL
Single user, mostly analytical queries, and the whole database is one file that's
easy to delete and rebuild. No server to run.

## Balances are calculated, not stored
Holdings and cash balances are views over the legs, so they can't drift out of
sync with the transactions.

## Imports rebuild from the raw files
Each import deletes the account's data and recreates it from `data/raw/`.
Overlapping exports can't double count, and fixing an importer bug only needs a
re-run.

## transactions.instrument_id
A dividend's income leg is cash, so it can't hold an instrument. This nullable
column records which security a buy or dividend is about.