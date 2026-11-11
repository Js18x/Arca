"""market_data.fx without the network: parsing and rebuilding from a cached file."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from init_db import apply_sql_files
from market_data import fx

FIXTURE = Path(__file__).parent / "fixtures" / "fx" / "eur_rates.json"


def test_parse_rates_returns_one_row_per_day_and_currency():
    rows = fx.parse_rates(FIXTURE)

    assert rows == [
        (date(2025, 1, 2), "EUR", "DKK", Decimal("7.4612")),
        (date(2025, 1, 2), "EUR", "USD", Decimal("1.0321")),
        (date(2025, 1, 3), "EUR", "DKK", Decimal("7.4598")),
        (date(2025, 1, 3), "EUR", "USD", Decimal("1.0299")),
    ]
    # Exact decimals straight from the JSON text, never floats.
    assert all(type(row[3]) is Decimal for row in rows)


def test_offline_run_rebuilds_from_the_cache_and_replaces_old_rows():
    connection = duckdb.connect(database=":memory:")
    apply_sql_files(connection)
    connection.execute("INSERT INTO fx_rates VALUES ('2020-01-01', 'EUR', 'USD', 1.5)")

    assert fx.run(connection, fetch=False, path=FIXTURE) == 4
    assert fx.run(connection, fetch=False, path=FIXTURE) == 4

    assert connection.execute(
        "SELECT MIN(date), COUNT(*) FROM fx_rates"
    ).fetchone() == (date(2025, 1, 2), 4)
    connection.close()


def test_offline_run_without_a_cache_explains_what_to_do(tmp_path):
    connection = duckdb.connect(database=":memory:")
    apply_sql_files(connection)

    with pytest.raises(FileNotFoundError, match="without --offline"):
        fx.run(connection, fetch=False, path=tmp_path / "missing.json")
    connection.close()


def test_fetch_rates_stops_before_calling_the_api_when_there_is_nothing_to_fetch(tmp_path):
    path = tmp_path / "eur_rates.json"

    with pytest.raises(ValueError, match="No foreign currencies"):
        fx.fetch_rates(date(2025, 1, 2), date(2025, 1, 3), [], path)
    assert not path.exists()
