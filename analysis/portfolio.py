def portfolio_value(connection, account_ids):
  if not account_ids:
    raise ValueError("account_ids cannot be empty")

  return connection.execute(
  """
    SELECT date, SUM(value_eur) AS total_value
    FROM daily_valuation
    WHERE list_contains(?, account_id)
    GROUP BY date
    ORDER BY date
  """,
  [account_ids],
  ).df()