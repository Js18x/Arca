import duckdb

connection = duckdb.connect("data/arca.duckdb", read_only=True)

print(connection.sql("""
        SELECT * FROM daily_cash
        WHERE account_id = 2 AND currency = 'USD'
        AND date IN ('2026-01-08', '2026-01-09', '2026-01-20', current_date)
        ORDER BY date
    """))