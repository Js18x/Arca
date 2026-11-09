import duckdb

from init_db import apply_sql_files


def test_schema_tables_exist():
    connection = duckdb.connect(database=":memory:")
    apply_sql_files(connection)

    tables = connection.sql("SHOW TABLES").fetchall()
    table_names = {table[0] for table in tables}

    expected_tables = {
        "accounts",
        "instruments",
        "transactions",
        "transaction_legs",
        "prices",
        "fx_rates",
        "import_runs",
        "cash_balances",
        "holdings",
        "transaction_summary",
    }

    assert table_names == expected_tables

    connection.close()
