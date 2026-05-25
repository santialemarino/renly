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
  'card_fees_and_taxes',
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
  'card_credits_and_refunds',
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

-- Income entries (daily income tracking).
-- source tracks origin: 'manual', 'shortcut', 'auto', 'reconciliation'.
-- reconciliation_id links the adjustment income created by the reconciliation flow (Phase 3, Step 5).
-- FK constraint is added via ALTER TABLE after card_reconciliations exists (circular dependency).
CREATE TABLE income_entries (
  id                BIGSERIAL PRIMARY KEY,
  user_id           BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  date              DATE NOT NULL,
  amount            NUMERIC(18, 2) NOT NULL,
  currency          VARCHAR(3) NOT NULL,
  category          income_category,
  notes             TEXT,
  source            VARCHAR(20) NOT NULL DEFAULT 'manual',
  reconciliation_id BIGINT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_income_entries_user_id ON income_entries(user_id);
CREATE INDEX idx_income_entries_user_date ON income_entries(user_id, date DESC);
CREATE INDEX idx_income_entries_reconciliation_id
  ON income_entries(reconciliation_id) WHERE reconciliation_id IS NOT NULL;

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

-- Subscriptions (recurring charges; e.g. Netflix, Spotify, gym).
-- Auto-generates monthly expense_entries via the scheduler (Phase 3, Step 3).
-- billing_cycle: 'monthly', 'annual', 'quarterly', 'biweekly', 'weekly'.
-- credit_card_id only set when payment_method = 'credit_card'.
-- anchor_day is the user's intended day-of-month (1-31). It's auto-derived from
-- next_billing_date and lets the scheduler snap back to the original day after
-- a short-month clamp (e.g. Jan 31 -> Feb 28 -> Mar 31, not Mar 28). Ignored by
-- weekly / biweekly cycles since those advance by literal days.
CREATE TABLE subscriptions (
  id                BIGSERIAL PRIMARY KEY,
  user_id           BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name              VARCHAR(255) NOT NULL,
  amount            NUMERIC(18, 2) NOT NULL,
  currency          VARCHAR(3) NOT NULL,
  billing_cycle     VARCHAR(20) NOT NULL,
  payment_method    VARCHAR(20),
  credit_card_id    BIGINT REFERENCES credit_cards(id),
  is_active         BOOLEAN NOT NULL DEFAULT TRUE,
  next_billing_date DATE NOT NULL,
  anchor_day        INTEGER NOT NULL CHECK (anchor_day >= 1 AND anchor_day <= 31),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_subscriptions_user_id ON subscriptions(user_id);
CREATE INDEX idx_subscriptions_user_next_billing ON subscriptions(user_id, next_billing_date);
CREATE INDEX idx_subscriptions_credit_card ON subscriptions(credit_card_id);

-- Installments (cuotas; e.g. TV Samsung 12x).
-- Auto-generates one expense_entry per cuota each month (Phase 3, Step 3).
-- is_active flips to false when current_installment > installments_count (fully paid).
CREATE TABLE installments (
  id                  BIGSERIAL PRIMARY KEY,
  user_id             BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name                VARCHAR(255) NOT NULL,
  total_amount        NUMERIC(18, 2) NOT NULL,
  installment_amount  NUMERIC(18, 2) NOT NULL,
  currency            VARCHAR(3) NOT NULL,
  installments_count  INTEGER NOT NULL,
  current_installment INTEGER NOT NULL DEFAULT 1,
  payment_method      VARCHAR(20),
  credit_card_id      BIGINT REFERENCES credit_cards(id),
  is_active           BOOLEAN NOT NULL DEFAULT TRUE,
  start_date          DATE NOT NULL,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_installments_user_id ON installments(user_id);
CREATE INDEX idx_installments_user_active ON installments(user_id, is_active);
CREATE INDEX idx_installments_credit_card ON installments(credit_card_id);

-- Expense entries (daily expense tracking).
-- payment_method: 'cash', 'debit', 'transfer', 'credit_card'.
-- credit_card_id only set when payment_method = 'credit_card'.
-- source tracks origin: 'manual', 'shortcut', 'auto', 'email_parsed', 'subscription', 'installment', 'reconciliation'.
-- subscription_id / installment_id link auto-generated entries to their source plan (Phase 3, Step 3 scheduler).
-- Both FKs use ON DELETE SET NULL so deleting a plan keeps historical expenses.
-- reconciliation_id links the adjustment expense created by the reconciliation flow (Phase 3, Step 5).
-- FK constraint on reconciliation_id is added via ALTER TABLE after card_reconciliations exists (circular dependency).
-- payment_obligation_id back-points to the payment_obligations row this expense was created to pay (Phase 3, Step E).
-- FK constraint on payment_obligation_id is added via ALTER TABLE after payment_obligations exists (declaration-order dependency).
-- Defined after subscriptions and installments because of these FK references.
CREATE TABLE expense_entries (
  id                     BIGSERIAL PRIMARY KEY,
  user_id                BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  date                   DATE NOT NULL,
  amount                 NUMERIC(18, 2) NOT NULL,
  currency               VARCHAR(3) NOT NULL,
  category               expense_category,
  notes                  TEXT,
  payment_method         VARCHAR(20),
  credit_card_id         BIGINT REFERENCES credit_cards(id),
  source                 VARCHAR(20) NOT NULL DEFAULT 'manual',
  subscription_id        BIGINT REFERENCES subscriptions(id) ON DELETE SET NULL,
  installment_id         BIGINT REFERENCES installments(id) ON DELETE SET NULL,
  reconciliation_id      BIGINT,
  payment_obligation_id  BIGINT,
  created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_expense_entries_user_id ON expense_entries(user_id);
CREATE INDEX idx_expense_entries_user_date ON expense_entries(user_id, date DESC);
CREATE INDEX idx_expense_entries_credit_card ON expense_entries(credit_card_id);
CREATE INDEX idx_expense_entries_reconciliation_id
  ON expense_entries(reconciliation_id) WHERE reconciliation_id IS NOT NULL;
CREATE INDEX idx_expense_entries_payment_obligation_id
  ON expense_entries(payment_obligation_id) WHERE payment_obligation_id IS NOT NULL;

-- Idempotency for the auto-generation scheduler: at most one entry per source plan per date.
CREATE UNIQUE INDEX idx_expense_entries_subscription_date
  ON expense_entries(subscription_id, date)
  WHERE subscription_id IS NOT NULL;
CREATE UNIQUE INDEX idx_expense_entries_installment_date
  ON expense_entries(installment_id, date)
  WHERE installment_id IS NOT NULL;

-- Card reconciliations (Phase 3, Step 5). One row per (card, currency, period_start, period_end).
-- statement_balance is the user-entered figure from the bank's resumen.
-- computed_balance is the bucket's running balance at period_end (= sum of expenses dated <= period_end
--   minus sum of settlements dated <= period_end). difference = statement_balance - computed_balance.
-- adjustment_expense_id / adjustment_income_id back-reference the single expense or income row created
--   to capture the difference (positive -> expense in card_fees_and_taxes; negative -> income in
--   card_credits_and_refunds; zero -> no adjustment). ON DELETE SET NULL keeps the reconciliation
--   record if the adjustment is deleted via the normal entry flow.
-- is_stale flips to true when an expense_entries or card_settlements row inside the period is created
--   / updated / deleted after this reconciliation was written. UI surfaces a re-reconcile prompt.
-- Re-reconciliation is delete-and-replace via the UNIQUE constraint and the cascade from
--   expense_entries / income_entries.reconciliation_id.
CREATE TABLE card_reconciliations (
  id                    BIGSERIAL PRIMARY KEY,
  user_id               BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  card_id               BIGINT NOT NULL REFERENCES credit_cards(id) ON DELETE CASCADE,
  currency              VARCHAR(3) NOT NULL,
  period_start          DATE NOT NULL,
  period_end            DATE NOT NULL,
  statement_balance     NUMERIC(18, 2) NOT NULL,
  computed_balance      NUMERIC(18, 2) NOT NULL,
  difference            NUMERIC(18, 2) NOT NULL,
  adjustment_expense_id BIGINT REFERENCES expense_entries(id) ON DELETE SET NULL,
  adjustment_income_id  BIGINT REFERENCES income_entries(id) ON DELETE SET NULL,
  is_stale              BOOLEAN NOT NULL DEFAULT FALSE,
  reconciled_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (card_id, currency, period_start, period_end)
);

CREATE INDEX idx_card_reconciliations_user_id ON card_reconciliations(user_id);
CREATE INDEX idx_card_reconciliations_card_currency ON card_reconciliations(card_id, currency);
CREATE INDEX idx_card_reconciliations_period_end ON card_reconciliations(card_id, period_end DESC);

-- Forward FKs from expense_entries / income_entries to card_reconciliations.
-- Declared via ALTER TABLE because card_reconciliations is created after the entry tables
-- (which need to exist first for the back-pointer FKs).
ALTER TABLE expense_entries
  ADD CONSTRAINT expense_entries_reconciliation_fkey
  FOREIGN KEY (reconciliation_id) REFERENCES card_reconciliations(id) ON DELETE CASCADE;

ALTER TABLE income_entries
  ADD CONSTRAINT income_entries_reconciliation_fkey
  FOREIGN KEY (reconciliation_id) REFERENCES card_reconciliations(id) ON DELETE CASCADE;

-- Payment obligations (e.g. electricity, ABL, gas, internet). Surfaces in Payments Calendar (Phase 3, Step 4).
-- recurrence: 'monthly', 'bimonthly', 'quarterly', 'annual', or NULL for one-off.
-- next_due_date is the anchor for the next occurrence; recurring obligations project forward from it.
CREATE TABLE payment_obligations (
  id                BIGSERIAL PRIMARY KEY,
  user_id           BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name              VARCHAR(255) NOT NULL,
  amount            NUMERIC(18, 2) NOT NULL,
  currency          VARCHAR(3) NOT NULL,
  next_due_date     DATE NOT NULL,
  anchor_day        INTEGER NOT NULL CHECK (anchor_day BETWEEN 1 AND 31),
  recurrence        VARCHAR(20),
  category          VARCHAR(100),
  expense_category  expense_category,
  payment_method    VARCHAR(20),
  credit_card_id    BIGINT REFERENCES credit_cards(id),
  is_active         BOOLEAN NOT NULL DEFAULT TRUE,
  notes             TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_payment_obligations_user_id ON payment_obligations(user_id);
CREATE INDEX idx_payment_obligations_user_next_due_date ON payment_obligations(user_id, next_due_date);
CREATE INDEX idx_payment_obligations_credit_card ON payment_obligations(credit_card_id);

-- Forward FK from expense_entries to payment_obligations (Phase 3, Step E).
-- Declared via ALTER TABLE because payment_obligations is created after expense_entries.
-- ON DELETE SET NULL: deleting an obligation keeps the historical expense and clears the back-pointer.
ALTER TABLE expense_entries
  ADD CONSTRAINT expense_entries_payment_obligation_fkey
  FOREIGN KEY (payment_obligation_id) REFERENCES payment_obligations(id) ON DELETE SET NULL;

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

CREATE TRIGGER trg_subscriptions_updated_at
  BEFORE UPDATE ON subscriptions
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_installments_updated_at
  BEFORE UPDATE ON installments
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_payment_obligations_updated_at
  BEFORE UPDATE ON payment_obligations
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_card_reconciliations_updated_at
  BEFORE UPDATE ON card_reconciliations
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

