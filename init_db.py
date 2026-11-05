from pathlib import Path
import duckdb


ROOT_DIR = Path(__file__).parent
SCHEMA_FILE = ROOT_DIR / "schema.sql"
DATABASE_DIR = ROOT_DIR / "data"
DATABASE_FILE = DATABASE_DIR / "arca.duckdb"


def initialise_database() -> None:
    DATABASE_DIR.mkdir(exist_ok=True)

    schema = SCHEMA_FILE.read_text(encoding="utf-8")

    with duckdb.connect(str(DATABASE_FILE)) as connection:
        connection.execute(schema)
        tables = connection.sql("SHOW TABLES").fetchall()

    print(f"Database ready: {DATABASE_FILE}")
    print("Tables:", ", ".join(table[0] for table in tables))


if __name__ == "__main__":
    initialise_database()