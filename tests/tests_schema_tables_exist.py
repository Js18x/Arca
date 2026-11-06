from pathlib import Path
import duckdb

def test_schema_tables_exist():
  connection = duckdb.connect(database=':memory:')

  schema_file = Path(__file__).parent.parent / "schema.sql"
  schema = schema_file.read_text(encoding="utf-8")
  connection.execute(schema)

  tables = connection.sql("SHOW TABLES").fetchall()
  table_names = {table[0] for table in tables}

  expected_tables = {
    "accounts",
    "instruments",
    "transactions",
    "transaction_legs",
    "prices",
    "fx_rates",
  }

  assert table_names == expected_tables

  connection.close()