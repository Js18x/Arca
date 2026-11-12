CREATE OR REPLACE VIEW holding_changes AS
SELECT
  t.event_date,
  t.account_id,
  tl.instrument_id,
  t.type,
  t.is_reinvestment,
  tl.amount AS quantity_change,
  tl.unit_price,
  tl.price_currency,
  CAST(tl.amount * tl.unit_price AS DECIMAL(18, 6)) AS value_local,
  CASE WHEN tl.price_currency = 'EUR' THEN 1 ELSE f.rate END AS fx_rate,
  CAST(tl.amount * tl.unit_price / fx_rate AS DECIMAL(18, 6)) AS value_eur
FROM transactions t
JOIN transaction_legs tl ON t.transaction_id = tl.transaction_id
LEFT JOIN daily_fx f
  ON tl.price_currency = f.quote_currency
  AND t.event_date = f.date
WHERE tl.instrument_id IS NOT NULL;