CREATE OR REPLACE VIEW holdings AS
SELECT
  t.account_id,
  l.instrument_id,
  SUM(l.amount) AS quantity
FROM transaction_legs l
JOIN transactions t ON t.transaction_id = l.transaction_id
WHERE l.instrument_id IS NOT NULL
GROUP BY t.account_id, l.instrument_id;