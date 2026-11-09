CREATE TABLE IF NOT EXISTS accounts (
  account_id INTEGER,
  broker_name VARCHAR(255) NOT NULL,
  base_currency VARCHAR(3) NOT NULL,

  PRIMARY KEY (account_id)
);

CREATE TABLE IF NOT EXISTS instruments (
  instrument_id INTEGER,
  isin VARCHAR(12) NOT NULL,
  name VARCHAR(255) NOT NULL,
  asset_type VARCHAR(255) NOT NULL,
  currency VARCHAR(3) NOT NULL,
  price_ticker VARCHAR(255),

  PRIMARY KEY (instrument_id),
  UNIQUE (isin)
);

CREATE TABLE IF NOT EXISTS transactions (
  transaction_id INTEGER,
  account_id INTEGER NOT NULL REFERENCES accounts(account_id),
  instrument_id INTEGER REFERENCES instruments(instrument_id),
  type VARCHAR(255) NOT NULL,
  event_date DATE NOT NULL,
  settle_date DATE,
  report_date DATE,
  is_reinvestment BOOLEAN NOT NULL DEFAULT FALSE,
  group_ref VARCHAR(255),

  PRIMARY KEY (transaction_id)
);  

CREATE TABLE IF NOT EXISTS transaction_legs (
  transaction_id INTEGER NOT NULL REFERENCES transactions(transaction_id),
  leg_number INTEGER NOT NULL,
  role VARCHAR(255) NOT NULL,
  amount DECIMAL(18, 10) NOT NULL,
  currency VARCHAR(3),
  instrument_id INTEGER REFERENCES instruments(instrument_id),
  unit_price DECIMAL(18, 10),
  price_currency VARCHAR(3),
  source_file VARCHAR(255) NOT NULL,
  source_id VARCHAR(255) NOT NULL,

  PRIMARY KEY (transaction_id, leg_number),
  UNIQUE (role, source_id),

  CHECK (
  (currency IS NOT NULL AND instrument_id IS NULL)
  OR
  (currency IS NULL AND instrument_id IS NOT NULL)
  )
);

CREATE TABLE IF NOT EXISTS prices (
  instrument_id INTEGER NOT NULL REFERENCES instruments(instrument_id),
  date DATE NOT NULL,
  close DECIMAL(18, 10) NOT NULL,
  adj_close DECIMAL(18, 10) NOT NULL,
  currency VARCHAR(3) NOT NULL,

  PRIMARY KEY (instrument_id, date)
);

CREATE TABLE IF NOT EXISTS fx_rates (
  date DATE NOT NULL,
  base_currency VARCHAR(3) NOT NULL,
  quote_currency VARCHAR(3) NOT NULL,
  rate DECIMAL(18, 10) NOT NULL,

  PRIMARY KEY (date, base_currency, quote_currency)
);

CREATE TABLE IF NOT EXISTS import_runs (
  broker VARCHAR(255),
  files_fingerprint VARCHAR(64) NOT NULL,
  code_fingerprint VARCHAR(64) NOT NULL,
  transaction_count INTEGER NOT NULL,
  imported_at TIMESTAMP NOT NULL,

  PRIMARY KEY (broker)
);
