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
  'USD',
  'BRL',
  'EUR',
  'GBP'
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
  'card_credits_and_refunds',
  'account_adjustment',
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
  'account_adjustment',
  'other'
);

CREATE TYPE user_plan AS ENUM (
  'free',
  'pro'
);

CREATE TYPE auth_token_type AS ENUM (
  'email_verification',
  'password_reset',
  'email_change'
);

CREATE TYPE invite_status AS ENUM (
  'pending',
  'accepted',
  'revoked'
);

CREATE TYPE feedback_category AS ENUM (
  'bug',
  'idea',
  'question',
  'other'
);

CREATE TYPE account_type AS ENUM (
  'cash',
  'bank',
  'wallet',
  'other'
);

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------

-- Users table
-- Passwords hashed with bcrypt. email_verified_at is NULL until the user confirms their address
-- via the AUTH-1 verification link (login is gated on it); it is set on verification or email change.
-- is_admin gates the admin invite endpoints (multi-admin: flag each row, not a role system).
CREATE TABLE users (
  id                BIGSERIAL PRIMARY KEY,
  name              VARCHAR(255) NOT NULL,
  email             VARCHAR(255) NOT NULL UNIQUE,
  password_hash     VARCHAR(255) NOT NULL,
  email_verified_at TIMESTAMPTZ,
  is_admin          BOOLEAN NOT NULL DEFAULT FALSE,
  session_epoch     BIGINT NOT NULL DEFAULT 0,
  plan              user_plan NOT NULL DEFAULT 'free',
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
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
-- user_id is denormalized from the parent investment so the row-level-security policy
-- (SEC-15) is a direct user_id check instead of a per-row EXISTS-join to investments.
CREATE TABLE investment_snapshots (
  id            BIGSERIAL PRIMARY KEY,
  investment_id BIGINT NOT NULL REFERENCES investments(id) ON DELETE CASCADE,
  user_id       BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
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
CREATE INDEX idx_snapshots_user_id ON investment_snapshots(user_id);

-- Transactions
-- Every capital movement: buy, sell, deposit, withdrawal.
-- Stored in original currency — conversion happens at query time.
-- user_id is denormalized from the parent investment for the row-level-security policy (SEC-15).
CREATE TABLE transactions (
  id            BIGSERIAL PRIMARY KEY,
  investment_id BIGINT NOT NULL REFERENCES investments(id) ON DELETE CASCADE,
  user_id       BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
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
CREATE INDEX idx_transactions_user_id ON transactions(user_id);

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
CREATE INDEX idx_exchange_rates_pair_date ON exchange_rates(pair, date);

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
  id              BIGSERIAL PRIMARY KEY,
  user_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name            VARCHAR(100) NOT NULL,
  closing_day     INTEGER NOT NULL CHECK (closing_day >= 1 AND closing_day <= 31),
  due_day         INTEGER NOT NULL CHECK (due_day >= 1 AND due_day <= 31),
  currency        VARCHAR(3) NOT NULL,
  is_active       BOOLEAN NOT NULL DEFAULT TRUE,
  -- Optional typical monthly payment toward this card (for revolving-debt users).
  -- When set, counts as a fixed monthly commitment in the liquidity ratio.
  monthly_payment NUMERIC(18,2) CHECK (monthly_payment IS NULL OR monthly_payment >= 0),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_credit_cards_user_id ON credit_cards(user_id);

-- Cash / bank accounts (asset accounts; Deferred Bucket 3 #1).
-- The running balance is DERIVED at query time (opening_balance plus linked income minus linked
-- expenses/settlements plus/minus transfers), never stored. One currency per account; opening_date
-- anchors the historical balance series. Archived (not deleted) via is_active = false.
CREATE TABLE accounts (
  id              BIGSERIAL PRIMARY KEY,
  user_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name            VARCHAR(255) NOT NULL,
  type            account_type NOT NULL,
  currency        VARCHAR(3) NOT NULL,
  opening_balance NUMERIC(18, 2) NOT NULL DEFAULT 0,
  opening_date    DATE NOT NULL,
  is_active       BOOLEAN NOT NULL DEFAULT TRUE,
  notes           TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_accounts_user_id ON accounts(user_id);
CREATE INDEX idx_accounts_user_active ON accounts(user_id, is_active);

-- Income entries (daily income tracking).
-- source tracks origin: 'manual', 'shortcut', 'auto', 'reconciliation'.
-- reconciliation_id links the adjustment income created by the card reconciliation flow (Phase 3, Step 5).
-- account_reconciliation_id is its cash/bank sibling (Bucket 3 #1, PR 4) — the adjustment income created
--   when an account's real balance is above what Renly computed.
-- Both FK constraints are added via ALTER TABLE after their reconciliation tables exist (circular dependency).
CREATE TABLE income_entries (
  id                        BIGSERIAL PRIMARY KEY,
  user_id                   BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  date                      DATE NOT NULL,
  amount                    NUMERIC(18, 2) NOT NULL,
  currency                  VARCHAR(3) NOT NULL,
  category                  income_category,
  notes                     TEXT,
  source                    VARCHAR(20) NOT NULL DEFAULT 'manual',
  reconciliation_id         BIGINT,
  account_reconciliation_id BIGINT,
  -- Optional cash/bank account this income was deposited to (Bucket 3 #1, PR 2).
  -- ON DELETE SET NULL: deleting an account un-attributes the entry, preserving its history.
  account_id                BIGINT REFERENCES accounts(id) ON DELETE SET NULL,
  created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_income_entries_user_id ON income_entries(user_id);
CREATE INDEX idx_income_entries_user_date ON income_entries(user_id, date DESC);
CREATE INDEX idx_income_entries_reconciliation_id
  ON income_entries(reconciliation_id) WHERE reconciliation_id IS NOT NULL;
CREATE INDEX idx_income_entries_account_reconciliation_id
  ON income_entries(account_reconciliation_id) WHERE account_reconciliation_id IS NOT NULL;
CREATE INDEX idx_income_entries_account_id
  ON income_entries(account_id) WHERE account_id IS NOT NULL;

-- Card settlements (credit card payments — not expenses).
-- Reduces card liability and bank balance simultaneously (net-zero on patrimony).
-- user_id is denormalized from the parent credit card for the row-level-security policy (SEC-15).
CREATE TABLE card_settlements (
  id              BIGSERIAL PRIMARY KEY,
  credit_card_id  BIGINT NOT NULL REFERENCES credit_cards(id) ON DELETE CASCADE,
  user_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  date            DATE NOT NULL,
  amount          NUMERIC(18, 2) NOT NULL,
  currency        VARCHAR(3) NOT NULL,
  -- Optional cash/bank account the payment was drawn from (Bucket 3 #1, PR 2).
  account_id      BIGINT REFERENCES accounts(id) ON DELETE SET NULL,
  notes           TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_card_settlements_credit_card ON card_settlements(credit_card_id);
CREATE INDEX idx_card_settlements_user_id ON card_settlements(user_id);
CREATE INDEX idx_card_settlements_account_id
  ON card_settlements(account_id) WHERE account_id IS NOT NULL;

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
-- reconciliation_id links the adjustment expense created by the card reconciliation flow (Phase 3, Step 5).
-- account_reconciliation_id is its cash/bank sibling (Bucket 3 #1, PR 4) — the adjustment expense created
--   when an account's real balance is below what Renly computed.
-- Both FK constraints are added via ALTER TABLE after their reconciliation tables exist (circular dependency).
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
  -- Optional cash/bank account this expense was paid from (Bucket 3 #1, PR 2).
  -- Not set for credit_card expenses (those hit the card, then draw cash at settlement).
  account_id             BIGINT REFERENCES accounts(id) ON DELETE SET NULL,
  source                 VARCHAR(20) NOT NULL DEFAULT 'manual',
  subscription_id        BIGINT REFERENCES subscriptions(id) ON DELETE SET NULL,
  installment_id         BIGINT REFERENCES installments(id) ON DELETE SET NULL,
  reconciliation_id      BIGINT,
  account_reconciliation_id BIGINT,
  payment_obligation_id  BIGINT,
  created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_expense_entries_user_id ON expense_entries(user_id);
CREATE INDEX idx_expense_entries_user_date ON expense_entries(user_id, date DESC);
CREATE INDEX idx_expense_entries_credit_card ON expense_entries(credit_card_id);
CREATE INDEX idx_expense_entries_account_id
  ON expense_entries(account_id) WHERE account_id IS NOT NULL;
CREATE INDEX idx_expense_entries_reconciliation_id
  ON expense_entries(reconciliation_id) WHERE reconciliation_id IS NOT NULL;
CREATE INDEX idx_expense_entries_account_reconciliation_id
  ON expense_entries(account_reconciliation_id) WHERE account_reconciliation_id IS NOT NULL;
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

-- Point-in-time account true-up against the real balance (Bucket 3 #1, PR 4 — Option F, simplified).
-- The cash/bank sibling of card_reconciliations, and deliberately simpler: an account is
-- single-currency and its balance is a point-in-time figure, so there is no statement PERIOD and no
-- currency bucket — just a balance as of a date. There is also no is_stale flag: re-reconciling
-- simply appends a newer row (a later true-up supersedes an earlier one by date), so no UNIQUE
-- constraint and no delete-and-replace.
-- difference = statement_balance - computed_balance. Positive means the account really holds more
--   than Renly knew, so the adjustment is an INCOME; negative creates an expense; zero creates nothing.
-- adjustment_expense_id / adjustment_income_id back-reference the adjustment row (SET NULL so deleting
--   the adjustment through the normal entry flow leaves the reconciliation record intact); the matching
--   expense_entries / income_entries.account_reconciliation_id closes the loop with ON DELETE CASCADE, so
--   deleting a reconciliation always removes the adjustment it created.
CREATE TABLE account_reconciliations (
  id                    BIGSERIAL PRIMARY KEY,
  user_id               BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  account_id            BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  as_of_date            DATE NOT NULL,
  statement_balance     NUMERIC(18, 2) NOT NULL,
  computed_balance      NUMERIC(18, 2) NOT NULL,
  difference            NUMERIC(18, 2) NOT NULL,
  adjustment_expense_id BIGINT REFERENCES expense_entries(id) ON DELETE SET NULL,
  adjustment_income_id  BIGINT REFERENCES income_entries(id) ON DELETE SET NULL,
  reconciled_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_account_reconciliations_user_id ON account_reconciliations(user_id);
CREATE INDEX idx_account_reconciliations_account_date
  ON account_reconciliations(account_id, as_of_date DESC);

-- Forward FKs from expense_entries / income_entries to account_reconciliations, mirroring the
-- card_reconciliations pair above. Declared via ALTER TABLE for the same circular-dependency reason.
ALTER TABLE expense_entries
  ADD CONSTRAINT expense_entries_account_reconciliation_fkey
  FOREIGN KEY (account_reconciliation_id) REFERENCES account_reconciliations(id) ON DELETE CASCADE;

ALTER TABLE income_entries
  ADD CONSTRAINT income_entries_account_reconciliation_fkey
  FOREIGN KEY (account_reconciliation_id) REFERENCES account_reconciliations(id) ON DELETE CASCADE;

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

-- Auth tokens (AUTH-1/2/8): single-use, time-limited tokens for email verification, password
-- reset, and email change. Only the SHA-256 hash of the high-entropy raw token is stored — the
-- raw value lives only in the emailed link. consumed_at enforces single use; expires_at bounds the
-- validity window. new_email holds the pending address for email_change tokens (NULL otherwise).
-- Timestamps are TIMESTAMP WITHOUT TIME ZONE (naive UTC) because the service compares them against
-- naive utcnow() (the SQLModel datetime mapping), so the driver must round-trip them as naive.
CREATE TABLE auth_tokens (
  id          BIGSERIAL PRIMARY KEY,
  user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash  VARCHAR(64) NOT NULL UNIQUE,
  token_type  auth_token_type NOT NULL,
  new_email   VARCHAR(255),
  expires_at  TIMESTAMP NOT NULL,
  consumed_at TIMESTAMP,
  created_at  TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
);

CREATE INDEX idx_auth_tokens_user_id ON auth_tokens(user_id);
CREATE INDEX idx_auth_tokens_user_type ON auth_tokens(user_id, token_type);

-- Refresh tokens (AUTH-7)
-- Long-lived, rotating refresh token for silent access-token renewal ("remember me"). Issued
-- alongside the access token at login and rotated single-use on every /auth/refresh: each refresh
-- consumes the presented token and mints its successor in the same family. Only the SHA-256 hash of
-- the high-entropy raw token is stored. family_id groups one login's rotation lineage; re-presenting
-- a consumed token (outside a short grace window) is treated as theft and revokes the whole family.
-- session_epoch is the user's epoch at mint time — a later bump (logout / password change) makes the
-- token invalid. remember_me selects the (sliding) validity window. Timestamps are TIMESTAMP WITHOUT
-- TIME ZONE (naive UTC) to match the service's naive utcnow() comparisons.
CREATE TABLE refresh_tokens (
  id            BIGSERIAL PRIMARY KEY,
  user_id       BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash    VARCHAR(64) NOT NULL UNIQUE,
  family_id     VARCHAR(32) NOT NULL,
  session_epoch BIGINT NOT NULL,
  remember_me   BOOLEAN NOT NULL,
  expires_at    TIMESTAMP NOT NULL,
  consumed_at   TIMESTAMP,
  revoked_at    TIMESTAMP,
  created_at    TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
);

CREATE INDEX idx_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE INDEX idx_refresh_tokens_family ON refresh_tokens(family_id);

-- Invites (invite-only access gate)
-- Single-use, time-limited admin invite binding a signup link to one email. An admin creates one
-- per address; only the SHA-256 hash of the high-entropy raw token is stored — the raw value lives
-- only in the emailed signup link. status is pending until the address registers (accepted) or an
-- admin cancels it (revoked); an expired link is a pending invite past expires_at (derived, not
-- stored). One active invite per email (UNIQUE); resend rotates the token in place. Timestamps are
-- TIMESTAMP WITHOUT TIME ZONE (naive UTC) to match the service's naive utcnow() comparisons.
CREATE TABLE invites (
  id          BIGSERIAL PRIMARY KEY,
  email       VARCHAR(255) NOT NULL UNIQUE,
  token_hash  VARCHAR(64) NOT NULL UNIQUE,
  invited_by  BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  status      invite_status NOT NULL DEFAULT 'pending',
  expires_at  TIMESTAMP NOT NULL,
  consumed_at TIMESTAMP,
  created_at  TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
);

CREATE INDEX idx_invites_invited_by ON invites(invited_by);

-- ---------------------------------------------------------------------------
-- Feedback (in-app feedback form)
-- A message a user sends from the in-app feedback form. Stored here for review in the admin area;
-- an email notification to every admin is sent best-effort on submission (not persisted). Owned by
-- user_id (RLS); the admin review list reads across users on the privileged session.
CREATE TABLE feedback (
  id         BIGSERIAL PRIMARY KEY,
  user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  category   feedback_category NOT NULL,
  message    VARCHAR(2000) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
);

CREATE INDEX idx_feedback_user_id ON feedback(user_id);

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

CREATE TRIGGER trg_accounts_updated_at
  BEFORE UPDATE ON accounts
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

CREATE TRIGGER trg_account_reconciliations_updated_at
  BEFORE UPDATE ON account_reconciliations
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------
-- Row-Level Security (SEC-15) — database-enforced per-user isolation
--
-- Two roles carry the design:
--   * the table owner / migration role (the role that runs this script and the
--     scheduler + auth bootstrap) keeps full access — it bypasses RLS because it
--     owns the tables, which is what background jobs and pre-auth lookups need;
--   * a restricted login role (renly_app) is granted DML but is NOT the owner and
--     has NOBYPASSRLS, so every request connection is subject to the policies below.
--
-- Each request sets `app.current_user_id` per transaction (SET LOCAL, re-applied on
-- every BEGIN by the app's session layer because connection pooling reuses connections).
-- Policies compare the row's owner against that GUC; with no GUC set, the helper returns
-- NULL and the comparison excludes every row (a context-less session reads nothing).
-- ENABLE (not FORCE) ROW LEVEL SECURITY is deliberate: FORCE would also subject the
-- owner role, breaking the scheduler and pre-auth reads that legitimately span users.
-- ---------------------------------------------------------------------------

-- Restricted request role. Cluster-global, so guard creation for shared clusters.
-- The password is a local-dev default; production provisions the role with a real secret.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'renly_app') THEN
    CREATE ROLE renly_app LOGIN PASSWORD 'renly_app' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
  END IF;
END $$;

-- Resolves the current request's user id from the per-transaction GUC. The two-arg
-- current_setting(..., true) returns NULL when the GUC was never set (instead of erroring),
-- and NULLIF maps an empty string to NULL, so a context-less session simply matches no rows.
CREATE OR REPLACE FUNCTION app_current_user_id() RETURNS BIGINT
  LANGUAGE sql STABLE
  AS $$ SELECT NULLIF(current_setting('app.current_user_id', true), '')::bigint $$;

-- Grant the restricted role table/sequence access (RLS, not GRANTs, enforces isolation).
-- Default privileges cover tables/sequences added by future migrations run as the owner.
GRANT USAGE ON SCHEMA public TO renly_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO renly_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO renly_app;
GRANT EXECUTE ON FUNCTION app_current_user_id() TO renly_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO renly_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO renly_app;

-- The users table keys on its own id (a user may read/write only its own row).
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
CREATE POLICY users_self_isolation ON users
  USING (id = app_current_user_id())
  WITH CHECK (id = app_current_user_id());

-- Tables owned directly via a user_id column: identical owner-match policy on each.
ALTER TABLE investments ENABLE ROW LEVEL SECURITY;
CREATE POLICY investments_user_isolation ON investments
  USING (user_id = app_current_user_id()) WITH CHECK (user_id = app_current_user_id());

ALTER TABLE investment_snapshots ENABLE ROW LEVEL SECURITY;
CREATE POLICY investment_snapshots_user_isolation ON investment_snapshots
  USING (user_id = app_current_user_id()) WITH CHECK (user_id = app_current_user_id());

ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;
CREATE POLICY transactions_user_isolation ON transactions
  USING (user_id = app_current_user_id()) WITH CHECK (user_id = app_current_user_id());

ALTER TABLE investment_groups ENABLE ROW LEVEL SECURITY;
CREATE POLICY investment_groups_user_isolation ON investment_groups
  USING (user_id = app_current_user_id()) WITH CHECK (user_id = app_current_user_id());

ALTER TABLE credit_cards ENABLE ROW LEVEL SECURITY;
CREATE POLICY credit_cards_user_isolation ON credit_cards
  USING (user_id = app_current_user_id()) WITH CHECK (user_id = app_current_user_id());

ALTER TABLE accounts ENABLE ROW LEVEL SECURITY;
CREATE POLICY accounts_user_isolation ON accounts
  USING (user_id = app_current_user_id()) WITH CHECK (user_id = app_current_user_id());

ALTER TABLE income_entries ENABLE ROW LEVEL SECURITY;
CREATE POLICY income_entries_user_isolation ON income_entries
  USING (user_id = app_current_user_id()) WITH CHECK (user_id = app_current_user_id());

ALTER TABLE card_settlements ENABLE ROW LEVEL SECURITY;
CREATE POLICY card_settlements_user_isolation ON card_settlements
  USING (user_id = app_current_user_id()) WITH CHECK (user_id = app_current_user_id());

ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;
CREATE POLICY subscriptions_user_isolation ON subscriptions
  USING (user_id = app_current_user_id()) WITH CHECK (user_id = app_current_user_id());

ALTER TABLE installments ENABLE ROW LEVEL SECURITY;
CREATE POLICY installments_user_isolation ON installments
  USING (user_id = app_current_user_id()) WITH CHECK (user_id = app_current_user_id());

ALTER TABLE expense_entries ENABLE ROW LEVEL SECURITY;
CREATE POLICY expense_entries_user_isolation ON expense_entries
  USING (user_id = app_current_user_id()) WITH CHECK (user_id = app_current_user_id());

ALTER TABLE card_reconciliations ENABLE ROW LEVEL SECURITY;
CREATE POLICY card_reconciliations_user_isolation ON card_reconciliations
  USING (user_id = app_current_user_id()) WITH CHECK (user_id = app_current_user_id());

ALTER TABLE account_reconciliations ENABLE ROW LEVEL SECURITY;
CREATE POLICY account_reconciliations_user_isolation ON account_reconciliations
  USING (user_id = app_current_user_id()) WITH CHECK (user_id = app_current_user_id());

ALTER TABLE payment_obligations ENABLE ROW LEVEL SECURITY;
CREATE POLICY payment_obligations_user_isolation ON payment_obligations
  USING (user_id = app_current_user_id()) WITH CHECK (user_id = app_current_user_id());

ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
CREATE POLICY api_keys_user_isolation ON api_keys
  USING (user_id = app_current_user_id()) WITH CHECK (user_id = app_current_user_id());

ALTER TABLE user_settings ENABLE ROW LEVEL SECURITY;
CREATE POLICY user_settings_user_isolation ON user_settings
  USING (user_id = app_current_user_id()) WITH CHECK (user_id = app_current_user_id());

-- auth_tokens are owned via user_id. Every flow that touches this table runs on the privileged
-- session and bypasses RLS: the pre-auth flows (verify-email/reset confirm, forgot-password) have no
-- user context, and the authenticated email-change request uses the privileged session so its
-- target-address availability check can see other accounts. This per-user policy is therefore
-- defense-in-depth — no request-session path inserts or reads here.
ALTER TABLE auth_tokens ENABLE ROW LEVEL SECURITY;
CREATE POLICY auth_tokens_user_isolation ON auth_tokens
  USING (user_id = app_current_user_id()) WITH CHECK (user_id = app_current_user_id());

-- refresh_tokens are owned via user_id. Like auth_tokens, every flow that touches this table runs on
-- the privileged session and bypasses RLS: login issues a token before any request-session context
-- exists, and /auth/refresh is pre-auth (it carries a refresh token, not an access token). This
-- per-user policy is therefore defense-in-depth — no request-session path inserts or reads here.
ALTER TABLE refresh_tokens ENABLE ROW LEVEL SECURITY;
CREATE POLICY refresh_tokens_user_isolation ON refresh_tokens
  USING (user_id = app_current_user_id()) WITH CHECK (user_id = app_current_user_id());

-- invites are owned via invited_by (the admin who created them). Every invite flow runs on the
-- privileged session and bypasses RLS: admin reads span all invites, and the register / signup-context
-- lookups are pre-auth. This per-admin policy is therefore defense-in-depth — the real gate is the
-- is_admin check at the admin endpoints, no request-session path inserts or reads here.
ALTER TABLE invites ENABLE ROW LEVEL SECURITY;
CREATE POLICY invites_admin_isolation ON invites
  USING (invited_by = app_current_user_id()) WITH CHECK (invited_by = app_current_user_id());

ALTER TABLE feedback ENABLE ROW LEVEL SECURITY;
CREATE POLICY feedback_user_isolation ON feedback
  USING (user_id = app_current_user_id()) WITH CHECK (user_id = app_current_user_id());

-- investment_group_members is a pure junction (composite PK, no surrogate user column).
-- Isolation is keyed through the parent investment via an EXISTS-join — both parents
-- belong to the same user (enforced by the SEC-4 cross-tenant FK checks), so checking
-- the investment side is sufficient and the lookup hits the investments primary key.
ALTER TABLE investment_group_members ENABLE ROW LEVEL SECURITY;
CREATE POLICY investment_group_members_isolation ON investment_group_members
  USING (
    EXISTS (
      SELECT 1 FROM investments i
      WHERE i.id = investment_group_members.investment_id
        AND i.user_id = app_current_user_id()
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM investments i
      WHERE i.id = investment_group_members.investment_id
        AND i.user_id = app_current_user_id()
    )
  );

-- exchange_rates, asset_prices and cedear_ratios are global reference data keyed by
-- pair/ticker (not by user) and are intentionally left without RLS so every request
-- connection can read them; the scheduler writes them under the owner role.

