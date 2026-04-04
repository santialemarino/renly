-- Renly — PostgreSQL Schema
-- Run this on a fresh database to initialize all tables (rebuild from zero).

-- ---------------------------------------------------------------------------
-- Enums
-- ---------------------------------------------------------------------------

CREATE TYPE investment_category AS ENUM (
  'cedears',
  'fci',
  'dollars',
  'government_bonds',
  'corporate_bonds',
  'stocks',
  'crypto',
  'real_estate',
  'term_deposit',
  'other'
);

CREATE TYPE currency AS ENUM (
  'ARS',
  'USD'
);

CREATE TYPE transaction_type AS ENUM (
  'buy',
  'sell',
  'deposit',
  'withdrawal'
);

CREATE TYPE exchange_rate_pair AS ENUM (
  'USD_ARS_OFICIAL',
  'USD_ARS_MEP',
  'USD_ARS_BLUE',
  'USD_BRL',
  'USD_EUR',
  'USD_GBP'
);

CREATE TYPE expense_category AS ENUM (
  'food',
  'dining',
  'transport',
  'rent',
  'utilities',
  'health',
  'entertainment',
  'sports',
  'subscriptions',
  'clothing',
  'education',
  'personal_care',
  'home_maintenance',
  'gifts',
  'travel',
  'taxes',
  'insurance',
  'kids',
  'pets',
  'other'
);

CREATE TYPE income_category AS ENUM (
  'salary',
  'freelance',
  'bonus',
  'investment_returns',
  'dividends',
  'rental_income',
  'sales',
  'refunds',
  'gifts',
  'other'
);

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------

-- Users table
-- Very few records (2-3 trusted family users). Passwords hashed with bcrypt.
CREATE TABLE users (
  id            BIGSERIAL PRIMARY KEY,
  name          VARCHAR(255) NOT NULL,
  email         VARCHAR(255) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  session_epoch BIGINT NOT NULL DEFAULT 0,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Investments table
-- Each distinct investment the user has or had (stock, term deposit, FCI, etc.).
-- base_currency is the currency the investment is naturally measured in.
-- Soft-deleted via is_active = false so history is preserved.
CREATE TABLE investments (
  id            BIGSERIAL PRIMARY KEY,
  user_id       BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name          VARCHAR(255) NOT NULL,
  category      investment_category NOT NULL,
  base_currency VARCHAR(10) NOT NULL,
  ticker        VARCHAR(20),
  broker        VARCHAR(100),
  notes         TEXT,
  is_active     BOOLEAN NOT NULL DEFAULT TRUE,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_investments_user_id ON investments(user_id);
CREATE INDEX idx_investments_user_active ON investments(user_id, is_active);

-- Investment snapshots
-- Total value of an investment at a point in time (typically end of month).
-- UNIQUE(investment_id, date) enforces one snapshot per investment per month.
CREATE TABLE investment_snapshots (
  id            BIGSERIAL PRIMARY KEY,
  investment_id BIGINT NOT NULL REFERENCES investments(id) ON DELETE CASCADE,
  date          DATE NOT NULL,
  value         NUMERIC(18, 2) NOT NULL,
  quantity      NUMERIC(18, 6),
  currency      currency NOT NULL,
  source        VARCHAR(20) NOT NULL DEFAULT 'manual',
  notes         TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (investment_id, date)
);

CREATE INDEX idx_snapshots_investment_date ON investment_snapshots(investment_id, date DESC);

-- Transactions
-- Every capital movement: buy, sell, deposit, withdrawal.
-- Stored in original currency — conversion happens at query time.
CREATE TABLE transactions (
  id            BIGSERIAL PRIMARY KEY,
  investment_id BIGINT NOT NULL REFERENCES investments(id) ON DELETE CASCADE,
  date          DATE NOT NULL,
  amount        NUMERIC(18, 2) NOT NULL,
  quantity      NUMERIC(18, 6),
  currency      currency NOT NULL,
  type          transaction_type NOT NULL,
  notes         TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_transactions_investment_date ON transactions(investment_id, date DESC);

-- Exchange rates
-- Historical rate by pair and date. Auto-updated via scheduled job.
-- source tracks whether the rate came from an API or was entered manually.
CREATE TABLE exchange_rates (
  id         BIGSERIAL PRIMARY KEY,
  date       DATE NOT NULL,
  pair       exchange_rate_pair NOT NULL,
  rate       NUMERIC(18, 6) NOT NULL,
  source     VARCHAR(50) NOT NULL DEFAULT 'manual',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (date, pair)
);

CREATE INDEX idx_exchange_rates_date ON exchange_rates(date DESC);

-- Investment groups
-- User-defined groups for aggregating investments (e.g. Retirement, Kids, Trading).
-- target_percentage is the desired allocation % for dashboard over/under-exposure alerts.
CREATE TABLE investment_groups (
  id                BIGSERIAL PRIMARY KEY,
  user_id           BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name              VARCHAR(255) NOT NULL,
  target_percentage NUMERIC(5, 2) CHECK (target_percentage >= 0 AND target_percentage <= 100),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_investment_groups_user_id ON investment_groups(user_id);

-- Many-to-many: an investment can belong to zero, one, or several groups.
CREATE TABLE investment_group_members (
  investment_id BIGINT NOT NULL REFERENCES investments(id) ON DELETE CASCADE,
  group_id      BIGINT NOT NULL REFERENCES investment_groups(id) ON DELETE CASCADE,
  PRIMARY KEY (investment_id, group_id)
);

CREATE INDEX idx_investment_group_members_group_id ON investment_group_members(group_id);

-- Asset prices
-- Historical prices for publicly traded assets, fetched from external APIs.
-- source tracks the provider (yfinance, coingecko, cafci, manual).
CREATE TABLE asset_prices (
  id         BIGSERIAL PRIMARY KEY,
  ticker     VARCHAR(20) NOT NULL,
  date       DATE NOT NULL,
  price      NUMERIC(18, 6) NOT NULL,
  currency   VARCHAR(10) NOT NULL,
  source     VARCHAR(50) NOT NULL DEFAULT 'manual',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (ticker, date)
);

CREATE INDEX idx_asset_prices_ticker_date ON asset_prices(ticker, date DESC);

-- CEDEAR ratios
-- Conversion ratio between CEDEARs and their underlying stock.
-- e.g. 10 CEDEARs of AAPL.BA = 1 AAPL share (ratio = 10).
-- Ratios change only on stock splits; stored by effective_date.
CREATE TABLE cedear_ratios (
  id              BIGSERIAL PRIMARY KEY,
  ticker          VARCHAR(20) NOT NULL,
  underlying      VARCHAR(20) NOT NULL,
  ratio           NUMERIC(10, 4) NOT NULL,
  effective_date  DATE NOT NULL,
  source          VARCHAR(50) NOT NULL DEFAULT 'manual',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (ticker, effective_date)
);

CREATE INDEX idx_cedear_ratios_ticker ON cedear_ratios(ticker, effective_date DESC);

-- User-owned credit cards (liability accounts).
-- closing_day and due_day are 1-31 day-of-month values.
CREATE TABLE credit_cards (
  id          BIGSERIAL PRIMARY KEY,
  user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name        VARCHAR(100) NOT NULL,
  closing_day INTEGER NOT NULL CHECK (closing_day >= 1 AND closing_day <= 31),
  due_day     INTEGER NOT NULL CHECK (due_day >= 1 AND due_day <= 31),
  currency    VARCHAR(3) NOT NULL,
  is_active   BOOLEAN NOT NULL DEFAULT TRUE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_credit_cards_user_id ON credit_cards(user_id);

-- Expense entries (daily expense tracking).
-- payment_method: 'cash', 'debit', 'transfer', 'credit_card'.
-- credit_card_id only set when payment_method = 'credit_card'.
-- source tracks origin: 'manual', 'shortcut', 'auto', 'email_parsed'.
CREATE TABLE expense_entries (
  id              BIGSERIAL PRIMARY KEY,
  user_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  date            DATE NOT NULL,
  amount          NUMERIC(18, 2) NOT NULL,
  currency        VARCHAR(3) NOT NULL,
  category        expense_category,
  notes           TEXT,
  payment_method  VARCHAR(20),
  credit_card_id  BIGINT REFERENCES credit_cards(id),
  source          VARCHAR(20) NOT NULL DEFAULT 'manual',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_expense_entries_user_id ON expense_entries(user_id);
CREATE INDEX idx_expense_entries_user_date ON expense_entries(user_id, date DESC);
CREATE INDEX idx_expense_entries_credit_card ON expense_entries(credit_card_id);

-- Income entries (daily income tracking).
-- source tracks origin: 'manual', 'shortcut', 'auto'.
CREATE TABLE income_entries (
  id          BIGSERIAL PRIMARY KEY,
  user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  date        DATE NOT NULL,
  amount      NUMERIC(18, 2) NOT NULL,
  currency    VARCHAR(3) NOT NULL,
  category    income_category,
  notes       TEXT,
  source      VARCHAR(20) NOT NULL DEFAULT 'manual',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_income_entries_user_id ON income_entries(user_id);
CREATE INDEX idx_income_entries_user_date ON income_entries(user_id, date DESC);

-- Card settlements (credit card payments — not expenses).
-- Reduces card liability and bank balance simultaneously (net-zero on patrimony).
CREATE TABLE card_settlements (
  id              BIGSERIAL PRIMARY KEY,
  credit_card_id  BIGINT NOT NULL REFERENCES credit_cards(id) ON DELETE CASCADE,
  date            DATE NOT NULL,
  amount          NUMERIC(18, 2) NOT NULL,
  currency        VARCHAR(3) NOT NULL,
  notes           TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_card_settlements_credit_card ON card_settlements(credit_card_id);

-- API keys for external access (iOS Shortcut, automations).
-- key_hash stores bcrypt hash; raw key is shown once at creation.
-- key_prefix stores first 8 chars of the raw key for fast indexed lookup
-- (avoids O(n) bcrypt comparisons on every request).
CREATE TABLE api_keys (
  id           BIGSERIAL PRIMARY KEY,
  user_id      BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  key_hash     VARCHAR(255) NOT NULL,
  key_prefix   VARCHAR(8) NOT NULL,
  name         VARCHAR(100),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_used_at TIMESTAMPTZ,
  is_active    BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX idx_api_keys_user_id ON api_keys(user_id);
CREATE INDEX idx_api_keys_prefix_active ON api_keys(key_prefix) WHERE is_active = TRUE;

-- Per-user app config (primary_currency, secondary_currency; expandable later via JSONB keys).
CREATE TABLE user_settings (
  id         BIGSERIAL PRIMARY KEY,
  user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE UNIQUE,
  settings   JSONB NOT NULL DEFAULT '{}',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_user_settings_user_id ON user_settings(user_id);

-- ---------------------------------------------------------------------------
-- updated_at trigger
-- PostgreSQL does not support ON UPDATE CURRENT_TIMESTAMP natively,
-- so we use a trigger function applied to every table that has updated_at.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_users_updated_at
  BEFORE UPDATE ON users
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_investments_updated_at
  BEFORE UPDATE ON investments
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_snapshots_updated_at
  BEFORE UPDATE ON investment_snapshots
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_transactions_updated_at
  BEFORE UPDATE ON transactions
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_exchange_rates_updated_at
  BEFORE UPDATE ON exchange_rates
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();


CREATE TRIGGER trg_investment_groups_updated_at
  BEFORE UPDATE ON investment_groups
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_asset_prices_updated_at
  BEFORE UPDATE ON asset_prices
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_cedear_ratios_updated_at
  BEFORE UPDATE ON cedear_ratios
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_user_settings_updated_at
  BEFORE UPDATE ON user_settings
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_credit_cards_updated_at
  BEFORE UPDATE ON credit_cards
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_expense_entries_updated_at
  BEFORE UPDATE ON expense_entries
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_income_entries_updated_at
  BEFORE UPDATE ON income_entries
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_card_settlements_updated_at
  BEFORE UPDATE ON card_settlements
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

