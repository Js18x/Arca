CREATE OR REPLACE VIEW cash_balances AS
SELECT
  t.account_id,
  l.currency,
  SUM(l.amount) AS balance
FROM transaction_legs l
JOIN transactions t ON t.transaction_id = l.transaction_id
WHERE l.currency IS NOT NULL
GROUP BY t.account_id, l.currency;