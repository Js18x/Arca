CREATE OR REPLACE VIEW daily_prices AS
WITH price_ranges AS (
  SELECT instrument_id, MIN(date) AS first_date 
  FROM prices
  GROUP BY instrument_id
),
all_days AS (
  SELECT pr.instrument_id, CAST(d.date AS DATE) AS date
  FROM price_ranges pr,
  generate_series(pr.first_date, CURRENT_DATE, INTERVAL '1 day') AS d(date)
)

SELECT a.instrument_id, a.date, p.date AS price_date, p.currency , p.close, p.adj_close
FROM all_days a
ASOF JOIN prices p
  ON a.instrument_id = p.instrument_id
  AND a.date >= p.date;