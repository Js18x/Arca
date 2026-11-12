WITH daily_changes AS (
  SELECT t.account_id, tl.instrument_id, t.event_date, SUM(tl.amount) AS change
  FROM transactions t
  JOIN transaction_legs tl ON t.transaction_id = tl.transaction_id
  WHERE tl.instrument_id IS NOT NULL
  GROUP BY t.account_id, tl.instrument_id, t.event_date
)

SELECT
    account_id,
    instrument_id,
    event_date,
    change,
    SUM(change) OVER (PARTITION BY account_id, instrument_id ORDER BY event_date) AS quantity
FROM daily_changes
ORDER BY account_id, instrument_id, event_date;