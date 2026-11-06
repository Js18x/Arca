from pathlib import Path

import duckdb


ROOT_DIR = Path(__file__).parent
DB_FILES_DIR = ROOT_DIR / "db_files"
DATABASE_DIR = ROOT_DIR / "data"
DATABASE_FILE = DATABASE_DIR / "arca.duckdb"


def apply_sql_files(connection: duckdb.DuckDBPyConnection) -> None:
    sql_files = sorted(
        DB_FILES_DIR.glob("*.sql"),
        key=lambda path: (path.name != "schema.sql", path.name),
    )
    for sql_file in sql_files:
        connection.execute(sql_file.read_text(encoding="utf-8"))


def initialise_database() -> None:
    DATABASE_DIR.mkdir(exist_ok=True)

    with duckdb.connect(str(DATABASE_FILE)) as connection:
        apply_sql_files(connection)
        tables = connection.sql("SHOW TABLES").fetchall()

    print(f"Database ready: {DATABASE_FILE}")
    print("Tables:", ", ".join(table[0] for table in tables))


if __name__ == "__main__":
    initialise_database()