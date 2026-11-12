CREATE OR REPLACE VIEW holding_changes AS
SELECT
  t.event_date,
  t.account_id,
  tl.instrument_id,
  t.type,
  t.is_reinvestment,
  tl.amount AS quantity_change,
  tl.unit_price,
  tl.price_currency
FROM transactions t
JOIN transaction_legs tl ON t.transaction_id = tl.transaction_id
WHERE tl.instrument_id IS NOT NULL;
