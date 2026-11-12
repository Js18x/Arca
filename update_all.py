"""Import new broker exports, then update exchange rates and prices.
  python update_all.py             import changed brokers, download market data
  python update_all.py --offline   import changed brokers, rebuild market data from the cache
  python update_all.py --force     re-import every broker
"""

import argparse
import duckdb

import run_imports
from init_db import DATABASE_FILE
from market_data import fx, prices

def main():
  parser = argparse.ArgumentParser(description="Update all data in the database.")
  parser.add_argument("--offline", action="store_true", help="rebuild market data from the cache")
  parser.add_argument("--force", action="store_true", help="re-import every broker")
  args = parser.parse_args()

  # Run imports for all brokers
  run_imports.import_changed(force=args.force)

  # Update market data
  with duckdb.connect(str(DATABASE_FILE)) as connection:
    fx_count = fx.run(connection, fetch=not args.offline)
    print(f"\nSaved {fx_count} FX rates")
    fx.print_summary(connection)

    price_count = prices.run(connection, fetch=not args.offline)
    print(f"\nSaved {price_count} prices")
    prices.print_summary(connection)

if __name__ == "__main__":
  main()