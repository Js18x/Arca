CREATE OR REPLACE VIEW daily_holdings AS
WITH daily_changes AS (
  SELECT t.account_id, tl.instrument_id, t.event_date, SUM(tl.amount) AS change
  FROM transactions t
  JOIN transaction_legs tl ON t.transaction_id = tl.transaction_id
  WHERE tl.instrument_id IS NOT NULL
  GROUP BY t.account_id, tl.instrument_id, t.event_date
),
running_totals AS (
  SELECT
    account_id,
    instrument_id,
    event_date,
    change,
    SUM(change) OVER (PARTITION BY account_id, instrument_id ORDER BY event_date) AS quantity
  FROM daily_changes
), 
positions AS (
  SELECT
    account_id,
    instrument_id,
    MIN(event_date) AS first_event_date
  FROM running_totals
  GROUP BY account_id, instrument_id
),
all_days AS (
  SELECT
    p.account_id,
    p.instrument_id,
    CAST(d.day AS DATE) AS date
  FROM positions p,
  generate_series(p.first_event_date, CURRENT_DATE, INTERVAL '1 day') AS d(day)
)

SELECT a.date, a.account_id, a.instrument_id, r.quantity
FROM all_days a
ASOF JOIN running_totals r
  ON a.account_id = r.account_id
  AND a.instrument_id = r.instrument_id
  AND a.date >= r.event_date;