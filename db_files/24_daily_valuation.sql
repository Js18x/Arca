CREATE OR REPLACE VIEW daily_valuation AS
WITH position_values AS (
  SELECT
    dh.date, dh.account_id, dh.instrument_id, dh.quantity, p.currency, p.close AS price,
    p.price_date, (dh.quantity * p.close) AS value_local, 
    CASE WHEN p.currency = 'EUR' THEN 1 ELSE f.rate END AS fx_rate, 
    CAST((dh.quantity * p.close) / fx_rate AS DECIMAL(18, 6)) AS value_eur
  FROM daily_holdings dh
  JOIN daily_prices p ON dh.instrument_id = p.instrument_id AND dh.date = p.date
  LEFT JOIN daily_fx f ON p.currency = f.quote_currency AND dh.date = f.date
), 
cash_values AS (
  SELECT
    dc.date,
    dc.account_id,
    dc.currency,
    dc.balance,
    CASE WHEN dc.currency = 'EUR' THEN 1 ELSE f.rate END AS fx_rate,
    CAST(dc.balance / fx_rate AS DECIMAL(18, 6)) AS value_eur
  FROM daily_cash dc
  LEFT JOIN daily_fx f ON dc.currency = f.quote_currency AND dc.date = f.date
)

SELECT * FROM position_values
UNION ALL BY NAME
SELECT * FROM cash_values;