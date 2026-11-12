CREATE OR REPLACE VIEW daily_fx AS
WITH rate_ranges AS (
  SELECT quote_currency, MIN(date) AS first_date
  FROM fx_rates
  GROUP BY quote_currency
),
all_days AS (
  SELECT rr.quote_currency, CAST(d.date AS DATE) AS date
  FROM rate_ranges rr,
  generate_series(rr.first_date, CURRENT_DATE, INTERVAL '1 day') AS d(date)
)

SELECT f.base_currency, a.quote_currency, a.date, f.date AS rate_date, f.rate
FROM all_days a
ASOF JOIN fx_rates f
  ON a.quote_currency = f.quote_currency
  AND a.date >= f.date;