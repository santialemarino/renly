-- Renly — PostgreSQL Schema
-- Run this on a fresh database to initialize all tables (rebuild from zero).

-- ---------------------------------------------------------------------------
-- Enums
-- ---------------------------------------------------------------------------

CREATE TYPE investment_category AS ENUM (
  'cedears',
  'fci',
  'dollars',
  'bonds',
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
  currency      currency NOT NULL,
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

-- Investment targets (optional in MVP)
-- Target allocation percentage per investment for dashboard over/under-exposure alerts.
CREATE TABLE investment_targets (
  id                BIGSERIAL PRIMARY KEY,
  investment_id     BIGINT NOT NULL REFERENCES investments(id) ON DELETE CASCADE UNIQUE,
  target_percentage NUMERIC(5, 2) NOT NULL CHECK (target_percentage >= 0 AND target_percentage <= 100),
  notes             TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Investment groups
-- User-defined groups for aggregating investments (e.g. Retirement, Kids, Trading).
CREATE TABLE investment_groups (
  id         BIGSERIAL PRIMARY KEY,
  user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name       VARCHAR(255) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_investment_groups_user_id ON investment_groups(user_id);

-- Many-to-many: an investment can belong to zero, one, or several groups.
CREATE TABLE investment_group_members (
  investment_id BIGINT NOT NULL REFERENCES investments(id) ON DELETE CASCADE,
  group_id      BIGINT NOT NULL REFERENCES investment_groups(id) ON DELETE CASCADE,
  PRIMARY KEY (investment_id, group_id)
);

CREATE INDEX idx_investment_group_members_group_id ON investment_group_members(group_id);

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

CREATE TRIGGER trg_investment_targets_updated_at
  BEFORE UPDATE ON investment_targets
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_investment_groups_updated_at
  BEFORE UPDATE ON investment_groups
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_user_settings_updated_at
  BEFORE UPDATE ON user_settings
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
