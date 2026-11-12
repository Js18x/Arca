CREATE OR REPLACE VIEW daily_cash AS
WITH daily_changes AS (
  SELECT t.account_id, tl.currency, t.event_date, SUM(tl.amount) AS change
  FROM transactions t
  JOIN transaction_legs tl ON t.transaction_id = tl.transaction_id
  WHERE tl.currency IS NOT NULL
  GROUP BY t.account_id, tl.currency, t.event_date
),
running_totals AS (
  SELECT
    account_id,
    currency,
    event_date,
    change,
    SUM(change) OVER (PARTITION BY account_id, currency ORDER BY event_date) AS balance
  FROM daily_changes
), 
positions AS (
  SELECT
    account_id,
    currency,
    MIN(event_date) AS first_event_date
  FROM running_totals
  GROUP BY account_id, currency
),
all_days AS (
  SELECT
    p.account_id,
    p.currency,
    CAST(d.day AS DATE) AS date
  FROM positions p,
  generate_series(p.first_event_date, CURRENT_DATE, INTERVAL '1 day') AS d(day)
)

SELECT a.date, a.account_id, a.currency, r.balance
FROM all_days a
ASOF JOIN running_totals r
  ON a.account_id = r.account_id
  AND a.currency = r.currency
  AND a.date >= r.event_date;