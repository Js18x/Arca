CREATE OR REPLACE VIEW transaction_summary AS
SELECT
  t.transaction_id,
  t.account_id,
  t.event_date,
  t.type,

  MAX(l.instrument_id) FILTER (WHERE l.role = 'shares') AS instrument_id,
  SUM(l.amount) FILTER (WHERE l.role = 'shares') AS quantity,

  SUM(l.amount) FILTER (WHERE l.role = 'cost') AS cost,
  MAX(l.currency) FILTER (WHERE l.role = 'cost') AS cost_currency,

  SUM(l.amount) FILTER (WHERE l.role = 'fee') AS fee,
  MAX(l.currency) FILTER (WHERE l.role = 'fee') AS fee_currency
FROM transactions t
JOIN transaction_legs l ON l.transaction_id = t.transaction_id
GROUP BY t.transaction_id, t.account_id, t.event_date, t.type;