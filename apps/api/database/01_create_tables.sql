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

CREATE TYPE group_kind AS ENUM (
  'household',
  'couple',
  'trip',
  'flat',
  'other'
);

CREATE TYPE group_member_role AS ENUM (
  'admin',
  'member'
);

-- Who may see a pot, for a group member with no explicit pot_member_permissions row:
-- 'members' = every active member of the group, 'owners' = only those holding an explicit
-- permission row (which is what an ownership event writes). An explicit row always wins.
CREATE TYPE pot_visibility AS ENUM (
  'members',
  'owners'
);

-- How often a pot is expected to be re-valued, which is the standard its freshness indicator is
-- measured against: 'weekly' for a pot someone else holds and reports on often, 'monthly' for one
-- you control (and the default, because auto-snapshots run monthly), 'ad_hoc' for a pot with no
-- agreed rhythm — which is never reported as overdue, since there is nothing to be late against.
-- Ordered by frequency rather than alphabetically; the Python StrEnum stays alphabetical.
CREATE TYPE pot_cadence AS ENUM (
  'weekly',
  'monthly',
  'ad_hoc'
);

-- What an entry in a pot's ownership ledger records. 'opening' sets the division baseline,
-- 'contribution' issues units for money moved in, 'withdrawal' redeems them for money moved out,
-- and 'reagreement' moves units between two members with no money at all.
CREATE TYPE ownership_event_type AS ENUM (
  'opening',
  'contribution',
  'withdrawal',
  'reagreement'
);

-- How a shared expense's total is divided between the members taking part. The method is a record of
-- what the user ASKED for, never of the result: the per-member figures are stored on the splits, so a
-- rounding rule or a member leaving can never re-derive an expense into different amounts than the
-- ones everybody agreed. 'equal' divides by the number of participants, 'exact' takes each figure as
-- given, 'shares' takes parts (2 shares to 1), 'percentage' takes percentages of the total.
CREATE TYPE split_method AS ENUM (
  'equal',
  'exact',
  'shares',
  'percentage'
);

-- Where a recorded settlement stands. 'pending' is money one member says they paid another, which
-- COUNTS against the balance immediately — it really moved — and which either named member may still
-- delete. 'confirmed' is the payee acknowledging receipt (D28's trust anchor); it locks the row until
-- the payee un-confirms it. 'written_off' is a debt the creditor has given up on: it clears the same
-- bucket a payment would, moves no cash at all, and is the other exit D24 requires before a member
-- with an open balance can be removed.
-- There is deliberately no 'reversed': reversing a settlement DELETES it, exactly as revoking a group
-- invite deletes its row, because until the audit log exists there is nothing that would ever read a
-- reversed state back.
CREATE TYPE group_settlement_status AS ENUM (
  'pending',
  'confirmed',
  'written_off'
);

-- Where money a group shares actually ends up (F2). 'joint' means it landed in a shared account a pot
-- holds, so the pot is worth more and EVERY owner's share rises in proportion — no units are issued
-- and nobody's percentage moves, because pro-rata growth needs no ownership event at all.
-- 'distributed' means it reached one person's hands and becomes each owner's own money in their
-- proportions; whoever collected it holds the rest as a balance until they pass it on.
-- Stored rather than derived from the destination account's scope, even though it usually could be: it
-- is the choice the user made, it is what the remembered per-source default reads back, and it is what
-- lets the API refuse a contradiction by name instead of silently reinterpreting one.
CREATE TYPE income_destination AS ENUM (
  'joint',
  'distributed'
);

-- What a notification is about. Ordered as the preferences surface presents them rather than
-- alphabetically, the same way income_destination and group_settlement_status are declared.
-- The labels are money events because shared money is what produces them; none of the three
-- notification TABLES names a money entity, which is what lets a second module (household reminders
-- and the like) add labels here and reuse every row, policy and preference unchanged.
CREATE TYPE notification_event AS ENUM (
  'group_invited',
  'member_joined',
  'ownership_changed',
  'pot_movement',
  'snapshot_due',
  'settle_marked_paid',
  'settle_confirmed',
  'balance_written_off',
  'shared_expense_added',
  'shared_income_added'
);

-- How a notification reaches someone. 'in_app' is the feed and is never sent anywhere; the other two
-- leave the app, which is why they are the ones a preference usually turns off.
CREATE TYPE notification_channel AS ENUM (
  'in_app',
  'email',
  'push'
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
-- user_id is the OWNER, not the author, and is NULL for a co-owned holding — which is what makes
-- every pre-existing `user_id = me` query keep meaning "exactly my private holdings" instead of
-- silently drifting to "authored by me". A query that forgets the pot branch under-reports; it can
-- never surface someone else's money. created_by carries authorship and is nullable + SET NULL for
-- the same reason groups.created_by is: a shared holding outlives the account that entered it.
-- The FK on pot_id is declared below, after pots exists.
CREATE TABLE investments (
  id            BIGSERIAL PRIMARY KEY,
  user_id       BIGINT REFERENCES users(id) ON DELETE CASCADE,
  pot_id        BIGINT,
  created_by    BIGINT REFERENCES users(id) ON DELETE SET NULL,
  name          VARCHAR(255) NOT NULL,
  category      investment_category NOT NULL,
  base_currency VARCHAR(10) NOT NULL,
  ticker        VARCHAR(20),
  broker        VARCHAR(100),
  notes         TEXT,
  is_active     BOOLEAN NOT NULL DEFAULT TRUE,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT investments_single_owner CHECK ((user_id IS NOT NULL) <> (pot_id IS NOT NULL))
);

CREATE INDEX idx_investments_user_id ON investments(user_id);
CREATE INDEX idx_investments_user_active ON investments(user_id, is_active);
CREATE INDEX idx_investments_pot_id ON investments(pot_id) WHERE pot_id IS NOT NULL;
CREATE INDEX idx_investments_created_by ON investments(created_by);

-- Investment snapshots
-- Total value of an investment at a point in time (typically end of month).
-- UNIQUE(investment_id, date) enforces one snapshot per investment per month.
-- user_id is denormalized from the parent investment so the row-level-security policy
-- (SEC-15) is a direct user_id check instead of a per-row EXISTS-join to investments.
CREATE TABLE investment_snapshots (
  id            BIGSERIAL PRIMARY KEY,
  investment_id BIGINT NOT NULL REFERENCES investments(id) ON DELETE CASCADE,
  user_id       BIGINT REFERENCES users(id) ON DELETE CASCADE,
  pot_id        BIGINT,
  date          DATE NOT NULL,
  value         NUMERIC(18, 2) NOT NULL,
  quantity      NUMERIC(18, 6),
  currency      currency NOT NULL,
  source        VARCHAR(20) NOT NULL DEFAULT 'manual',
  notes         TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (investment_id, date),
  CONSTRAINT investment_snapshots_single_owner CHECK ((user_id IS NOT NULL) <> (pot_id IS NOT NULL))
);

CREATE INDEX idx_snapshots_investment_date ON investment_snapshots(investment_id, date DESC);
CREATE INDEX idx_snapshots_user_id ON investment_snapshots(user_id);
CREATE INDEX idx_snapshots_pot_id ON investment_snapshots(pot_id) WHERE pot_id IS NOT NULL;

-- Transactions
-- Every capital movement: buy, sell, deposit, withdrawal.
-- Stored in original currency — conversion happens at query time.
-- user_id is denormalized from the parent investment for the row-level-security policy (SEC-15).
CREATE TABLE transactions (
  id            BIGSERIAL PRIMARY KEY,
  investment_id BIGINT NOT NULL REFERENCES investments(id) ON DELETE CASCADE,
  user_id       BIGINT REFERENCES users(id) ON DELETE CASCADE,
  pot_id        BIGINT,
  date          DATE NOT NULL,
  amount        NUMERIC(18, 2) NOT NULL,
  quantity      NUMERIC(18, 6),
  currency      currency NOT NULL,
  type          transaction_type NOT NULL,
  notes         TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT transactions_single_owner CHECK ((user_id IS NOT NULL) <> (pot_id IS NOT NULL))
);

CREATE INDEX idx_transactions_investment_date ON transactions(investment_id, date DESC);
CREATE INDEX idx_transactions_user_id ON transactions(user_id);
CREATE INDEX idx_transactions_pot_id ON transactions(pot_id) WHERE pot_id IS NOT NULL;

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

-- Investment collections
-- User-defined collections for aggregating investments (e.g. Retirement, Kids, Trading).
-- target_percentage is the desired allocation % for dashboard over/under-exposure alerts.
CREATE TABLE investment_collections (
  id                BIGSERIAL PRIMARY KEY,
  user_id           BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name              VARCHAR(255) NOT NULL,
  target_percentage NUMERIC(5, 2) CHECK (target_percentage >= 0 AND target_percentage <= 100),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_investment_collections_user_id ON investment_collections(user_id);

-- Many-to-many: an investment can belong to zero, one, or several collections.
CREATE TABLE investment_collection_members (
  investment_id BIGINT NOT NULL REFERENCES investments(id) ON DELETE CASCADE,
  collection_id BIGINT NOT NULL REFERENCES investment_collections(id) ON DELETE CASCADE,
  PRIMARY KEY (investment_id, collection_id)
);

CREATE INDEX idx_investment_collection_members_collection_id ON investment_collection_members(collection_id);

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
-- default_account_id is the optional "débito automático" funding account: it PRE-FILLS the
--   settlement dialog's "Paid from" and never generates a settlement on its own — a real auto-debit
--   can fail, and Renly must never invent a payment that did not happen. Its FK constraint is added
--   via ALTER TABLE below because accounts is created after this table.
CREATE TABLE credit_cards (
  id                 BIGSERIAL PRIMARY KEY,
  user_id            BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name               VARCHAR(100) NOT NULL,
  closing_day        INTEGER NOT NULL CHECK (closing_day >= 1 AND closing_day <= 31),
  due_day            INTEGER NOT NULL CHECK (due_day >= 1 AND due_day <= 31),
  currency           VARCHAR(3) NOT NULL,
  is_active          BOOLEAN NOT NULL DEFAULT TRUE,
  -- Optional typical monthly payment toward this card (for revolving-debt users).
  -- When set, counts as a fixed monthly commitment in the liquidity ratio.
  monthly_payment    NUMERIC(18,2) CHECK (monthly_payment IS NULL OR monthly_payment >= 0),
  default_account_id BIGINT,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_credit_cards_user_id ON credit_cards(user_id);

-- Cash / bank accounts (asset accounts; Deferred Bucket 3 #1).
-- The running balance is DERIVED at query time (opening_balance plus linked income minus linked
-- expenses/settlements plus/minus transfers), never stored. One currency per account; opening_date
-- anchors the historical balance series. Archived (not deleted) via is_active = false.
-- Scope columns mirror investments exactly: user_id is the OWNER (NULL when the account is
-- co-owned through a pot), created_by is authorship. See the investments comment for why.
CREATE TABLE accounts (
  id              BIGSERIAL PRIMARY KEY,
  user_id         BIGINT REFERENCES users(id) ON DELETE CASCADE,
  pot_id          BIGINT,
  created_by      BIGINT REFERENCES users(id) ON DELETE SET NULL,
  name            VARCHAR(255) NOT NULL,
  type            account_type NOT NULL,
  currency        VARCHAR(3) NOT NULL,
  opening_balance NUMERIC(18, 2) NOT NULL DEFAULT 0,
  opening_date    DATE NOT NULL,
  is_active       BOOLEAN NOT NULL DEFAULT TRUE,
  notes           TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT accounts_single_owner CHECK ((user_id IS NOT NULL) <> (pot_id IS NOT NULL))
);

CREATE INDEX idx_accounts_user_id ON accounts(user_id);
CREATE INDEX idx_accounts_user_active ON accounts(user_id, is_active);
CREATE INDEX idx_accounts_pot_id ON accounts(pot_id) WHERE pot_id IS NOT NULL;
CREATE INDEX idx_accounts_created_by ON accounts(created_by);

-- Forward FK from credit_cards to accounts (the default funding account).
-- Declared via ALTER TABLE because accounts is created after credit_cards.
-- ON DELETE SET NULL: deleting an account clears the default rather than blocking the delete —
-- the default is a convenience, never a record of money that moved.
ALTER TABLE credit_cards
  ADD CONSTRAINT credit_cards_default_account_id_fkey
  FOREIGN KEY (default_account_id) REFERENCES accounts(id) ON DELETE SET NULL;

CREATE INDEX idx_credit_cards_default_account_id ON credit_cards(default_account_id)
  WHERE default_account_id IS NOT NULL;

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
-- amount/currency are the CARD leg: what the payment cleared off the bucket. account_amount is the
--   CASH leg, in the funding account's own currency, and is set only when the two differ — paying a
--   USD bucket with pesos clears US$100 while $130,000 leaves the account. The pair IS the record of
--   the rate used (deliberately no stored rate: no single direction reads correctly both ways, the
--   same reason transfers has no implied_rate). The gap between the two is the real FX + tax cost and
--   is never itemised; its effect on the reported net-worth delta depends on the rate the debt was
--   marked at (see docs/technical/currency-handling.md 12).
CREATE TABLE card_settlements (
  id              BIGSERIAL PRIMARY KEY,
  credit_card_id  BIGINT NOT NULL REFERENCES credit_cards(id) ON DELETE CASCADE,
  user_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  date            DATE NOT NULL,
  amount          NUMERIC(18, 2) NOT NULL,
  currency        VARCHAR(3) NOT NULL,
  -- Optional cash/bank account the payment was drawn from (Bucket 3 #1, PR 2).
  account_id      BIGINT REFERENCES accounts(id) ON DELETE SET NULL,
  -- What left the funding account, in THAT account's currency. NULL = no conversion, so the cash leg
  -- is `amount` itself; the cash sums read coalesce(account_amount, amount).
  account_amount  NUMERIC(18, 2),
  notes           TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  -- "No cash amount without the account it came from" is deliberately NOT a CHECK: account_id is
  -- ON DELETE SET NULL, which Postgres runs as an UPDATE, so such a constraint would make any account
  -- that funded a cross-currency settlement permanently undeletable. The service enforces the rule on
  -- write and clears account_amount when it drops the link.
  CONSTRAINT card_settlements_positive_account_amount CHECK (account_amount IS NULL OR account_amount > 0)
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
-- default_account_id is the optional account the scheduler links each emitted charge to, so an
--   auto-generated expense decrements the balance it really came out of. Only meaningful when
--   payment_method <> 'credit_card' (a card-paid plan hits the card, and its cash leg lands at the
--   card settlement instead). ON DELETE SET NULL — the default is a convenience, not a money record.
CREATE TABLE subscriptions (
  id                 BIGSERIAL PRIMARY KEY,
  user_id            BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name               VARCHAR(255) NOT NULL,
  amount             NUMERIC(18, 2) NOT NULL,
  currency           VARCHAR(3) NOT NULL,
  billing_cycle      VARCHAR(20) NOT NULL,
  payment_method     VARCHAR(20),
  credit_card_id     BIGINT REFERENCES credit_cards(id),
  default_account_id BIGINT REFERENCES accounts(id) ON DELETE SET NULL,
  is_active          BOOLEAN NOT NULL DEFAULT TRUE,
  next_billing_date  DATE NOT NULL,
  anchor_day         INTEGER NOT NULL CHECK (anchor_day >= 1 AND anchor_day <= 31),
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_subscriptions_user_id ON subscriptions(user_id);
CREATE INDEX idx_subscriptions_user_next_billing ON subscriptions(user_id, next_billing_date);
CREATE INDEX idx_subscriptions_credit_card ON subscriptions(credit_card_id);
CREATE INDEX idx_subscriptions_default_account_id ON subscriptions(default_account_id)
  WHERE default_account_id IS NOT NULL;

-- Installments (cuotas; e.g. TV Samsung 12x).
-- Auto-generates one expense_entry per cuota each month (Phase 3, Step 3).
-- is_active flips to false when current_installment > installments_count (fully paid).
-- default_account_id mirrors subscriptions: the account the scheduler links each emitted cuota to.
--   Deliberately NOT one of the LOCKED_FIELDS — it is a forward-looking convenience rather than a
--   contractual term of the plan, so it stays editable after charging has started.
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
  default_account_id  BIGINT REFERENCES accounts(id) ON DELETE SET NULL,
  is_active           BOOLEAN NOT NULL DEFAULT TRUE,
  start_date          DATE NOT NULL,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_installments_user_id ON installments(user_id);
CREATE INDEX idx_installments_user_active ON installments(user_id, is_active);
CREATE INDEX idx_installments_credit_card ON installments(credit_card_id);
CREATE INDEX idx_installments_default_account_id ON installments(default_account_id)
  WHERE default_account_id IS NOT NULL;

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
  id                        BIGSERIAL PRIMARY KEY,
  user_id                   BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  date                      DATE NOT NULL,
  amount                    NUMERIC(18, 2) NOT NULL,
  currency                  VARCHAR(3) NOT NULL,
  category                  expense_category,
  notes                     TEXT,
  payment_method            VARCHAR(20),
  credit_card_id            BIGINT REFERENCES credit_cards(id),
  -- Optional cash/bank account this expense was paid from (Bucket 3 #1, PR 2).
  -- Not set for credit_card expenses (those hit the card, then draw cash at settlement).
  account_id                BIGINT REFERENCES accounts(id) ON DELETE SET NULL,
  source                    VARCHAR(20) NOT NULL DEFAULT 'manual',
  subscription_id           BIGINT REFERENCES subscriptions(id) ON DELETE SET NULL,
  installment_id            BIGINT REFERENCES installments(id) ON DELETE SET NULL,
  reconciliation_id         BIGINT,
  account_reconciliation_id BIGINT,
  payment_obligation_id     BIGINT,
  created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
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
-- adjustment_expense_id back-references the single SIGNED expense row created to capture the difference
--   (positive -> card_fees_and_taxes; negative -> card_credits_and_refunds; zero -> no adjustment). Both
--   directions are expenses because a bucket balance is `sum(expenses) - sum(settlements)`, so only an
--   expense can move it — an income row would leave the card overstated. ON DELETE SET NULL is only a
--   safety net for an out-of-band delete: the entry endpoints REFUSE a direct PUT / DELETE on an
--   adjustment (409 reconciliation_owned_entry), because clearing this pointer would leave the
--   reconciliation claiming a difference it no longer applies. Delete the reconciliation instead — the
--   expense_entries.reconciliation_id side is ON DELETE CASCADE and drops the adjustment with it.
-- adjustment_income_id is retained for the historical shape but is no longer written.
-- is_stale flips to true when a row the recorded balance was derived from changes afterwards. The
-- balance sums everything dated <= period_end from the start of the bucket's history, so the trigger
-- is a charge or settlement dated ON OR BEFORE period_end being created
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
-- adjustment_expense_id / adjustment_income_id back-reference the adjustment row. SET NULL is only a
--   safety net for an out-of-band delete: the entry endpoints REFUSE a direct PUT / DELETE on an
--   adjustment (409 reconciliation_owned_entry), because clearing this pointer would leave the
--   reconciliation claiming a difference it no longer applies while the balance snapped back. The
--   matching expense_entries / income_entries.account_reconciliation_id closes the loop with ON DELETE
--   CASCADE, so deleting a reconciliation always removes the adjustment it created — that is the
--   supported way to revise one.
CREATE TABLE account_reconciliations (
  id                    BIGSERIAL PRIMARY KEY,
  user_id               BIGINT REFERENCES users(id) ON DELETE CASCADE,
  pot_id                BIGINT,
  account_id            BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  as_of_date            DATE NOT NULL,
  statement_balance     NUMERIC(18, 2) NOT NULL,
  computed_balance      NUMERIC(18, 2) NOT NULL,
  difference            NUMERIC(18, 2) NOT NULL,
  adjustment_expense_id BIGINT REFERENCES expense_entries(id) ON DELETE SET NULL,
  adjustment_income_id  BIGINT REFERENCES income_entries(id) ON DELETE SET NULL,
  reconciled_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT account_reconciliations_single_owner CHECK ((user_id IS NOT NULL) <> (pot_id IS NOT NULL))
);

CREATE INDEX idx_account_reconciliations_user_id ON account_reconciliations(user_id);
CREATE INDEX idx_account_reconciliations_pot_id ON account_reconciliations(pot_id) WHERE pot_id IS NOT NULL;
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

-- Account-to-account movement (Deferred Bucket 3 #1, PR 5). The one movement type that is neither
-- income nor an expense: net worth does not change, the money just leaves one owned pool and arrives
-- in another. Paying someone ELSE is an expense, not a transfer.
-- Both amounts are stored so a cross-currency transfer (buy/sell USD) records the rate actually used:
--   from_amount is in the source account's currency, to_amount in the destination's, and their ratio
--   is the implied rate including the spread. Within one currency the two are equal — a bank fee is
--   recorded as its own expense rather than shrinking the transfer, so "a transfer never changes net
--   worth" stays a hard invariant rather than something the amounts happen to satisfy.
-- Both account FKs CASCADE: a surviving half-transfer would silently skew the other account's derived
--   balance, which is the opposite of what deleting an account should do.
CREATE TABLE transfers (
  id              BIGSERIAL PRIMARY KEY,
  user_id         BIGINT REFERENCES users(id) ON DELETE CASCADE,
  pot_id          BIGINT,
  from_account_id BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  to_account_id   BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  date            DATE NOT NULL,
  from_amount     NUMERIC(18,2) NOT NULL,
  to_amount       NUMERIC(18,2) NOT NULL,
  notes           TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  -- A same-account transfer is a no-op that would double-count: the balance union sums each leg
  -- independently, so the row would be both added and subtracted on the same account.
  CONSTRAINT transfers_distinct_accounts CHECK (from_account_id <> to_account_id),
  CONSTRAINT transfers_positive_amounts CHECK (from_amount > 0 AND to_amount > 0),
  -- A transfer is net-worth-neutral by construction, which is only true within ONE scope: moving
  -- joint money into a personal account takes value from the other owners. Crossing a scope boundary
  -- is a contribution or a withdrawal instead. The scope columns are denormalized from the two legs,
  -- which the service holds to the same scope, so this row can carry only one.
  CONSTRAINT transfers_single_owner CHECK ((user_id IS NOT NULL) <> (pot_id IS NOT NULL))
);
CREATE INDEX idx_transfers_user_id ON transfers(user_id);
CREATE INDEX idx_transfers_pot_id ON transfers(pot_id) WHERE pot_id IS NOT NULL;
-- The balance union filters one leg at a time by account and bounds by date, so each leg gets its own
-- composite index rather than a bare FK index.
CREATE INDEX idx_transfers_from_account_date ON transfers(from_account_id, date);
CREATE INDEX idx_transfers_to_account_date ON transfers(to_account_id, date);

-- Payment obligations (e.g. electricity, ABL, gas, internet). Surfaces in Payments Calendar (Phase 3, Step 4).
-- recurrence: 'monthly', 'bimonthly', 'quarterly', 'annual', or NULL for one-off.
-- next_due_date is the anchor for the next occurrence; recurring obligations project forward from it.
-- default_account_id is the account Mark Paid pre-fills as "Paid from" on the expense it creates.
--   Obligations are not auto-emitted (there is no scheduler for them), so this default is honoured at
--   Mark Paid time rather than by a background job.
CREATE TABLE payment_obligations (
  id                 BIGSERIAL PRIMARY KEY,
  user_id            BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name               VARCHAR(255) NOT NULL,
  amount             NUMERIC(18, 2) NOT NULL,
  currency           VARCHAR(3) NOT NULL,
  next_due_date      DATE NOT NULL,
  anchor_day         INTEGER NOT NULL CHECK (anchor_day BETWEEN 1 AND 31),
  recurrence         VARCHAR(20),
  category           VARCHAR(100),
  expense_category   expense_category,
  payment_method     VARCHAR(20),
  credit_card_id     BIGINT REFERENCES credit_cards(id),
  default_account_id BIGINT REFERENCES accounts(id) ON DELETE SET NULL,
  is_active          BOOLEAN NOT NULL DEFAULT TRUE,
  notes              TEXT,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_payment_obligations_user_id ON payment_obligations(user_id);
CREATE INDEX idx_payment_obligations_user_next_due_date ON payment_obligations(user_id, next_due_date);
CREATE INDEX idx_payment_obligations_credit_card ON payment_obligations(credit_card_id);
CREATE INDEX idx_payment_obligations_default_account_id ON payment_obligations(default_account_id)
  WHERE default_account_id IS NOT NULL;

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
-- Groups (shared money: the people entity)
-- A group is a set of people who share money — a household, a couple, a trip, a flat. It is the
-- ONLY multi-user entity in the schema: every other table is owned by exactly one user_id, whereas
-- a group's rows are reachable by each of its members through the membership policies below.
-- Deliberately entity-agnostic: it carries who the people are and nothing about what they share, so
-- a non-money module could adopt the same membership kernel unchanged.
-- created_by records who created the group (authorship, not ownership — a group has no single
-- owner). ON DELETE SET NULL because the group belongs to its members, not its creator: deleting
-- the creator's account must not delete a group other people are still using.
CREATE TABLE groups (
  id         BIGSERIAL PRIMARY KEY,
  name       VARCHAR(255) NOT NULL,
  kind       group_kind NOT NULL,
  created_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_groups_created_by ON groups(created_by);

-- One row per seat in a group. user_id is NULL for a name-only placeholder — someone tracked in the
-- group who has no Renly account (and may never have one); accepting an invite fills it in, which is
-- the whole of the "placeholder upgrades on join" mechanic: no migration, no recompute, and the
-- member's history is already attached to this row.
-- role is group administration ONLY: an admin manages members and settings and gains no additional
-- visibility into any member's data.
-- Removing a member DEACTIVATES the seat (is_active = false) rather than deleting it, so the rows
-- that will later reference it (splits, settlements, ownership units) keep a real counterparty. The
-- membership policies require is_active, so a deactivated member loses access immediately.
-- ON DELETE SET NULL on user_id: deleting an account reverts the seat to a name-only placeholder and
-- leaves the group's history intact, instead of cascading a shared group's rows away.
CREATE TABLE group_members (
  id           BIGSERIAL PRIMARY KEY,
  group_id     BIGINT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
  user_id      BIGINT REFERENCES users(id) ON DELETE SET NULL,
  display_name VARCHAR(255) NOT NULL,
  role         group_member_role NOT NULL DEFAULT 'member',
  is_active    BOOLEAN NOT NULL DEFAULT TRUE,
  joined_at    TIMESTAMPTZ,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_group_members_group_id ON group_members(group_id);
-- Every membership policy resolves "which groups is this user in", so the lookup is by user_id with
-- group_id and is_active covered, and the partial predicate skips every placeholder row.
CREATE INDEX idx_group_members_user_active ON group_members(user_id, group_id, is_active)
  WHERE user_id IS NOT NULL;
-- One seat per account per group. Partial because placeholders all have user_id NULL, which a plain
-- UNIQUE would not constrain but would also not usefully index.
CREATE UNIQUE INDEX idx_group_members_group_user ON group_members(group_id, user_id)
  WHERE user_id IS NOT NULL;

-- A pending invitation to claim one seat. Same proven mechanism as `invites` (high-entropy raw token,
-- only its SHA-256 hash stored, time-limited, single-use via consumed_at, rotate-on-resend) but a
-- deliberately separate table: `invites` has a GLOBAL UNIQUE (email) because it gates platform signup
-- ("one active invite per email"), while the same person may legitimately hold seats in several groups
-- at once — and a group invite must never grant signup access, nor consuming one consume the other.
-- The token is the credential: no account is created here, it only links an existing account to this
-- seat, so whoever holds the link claims it (which is also what makes a shareable link possible).
-- email is informational — the address the link was sent to, NULL for a link-only invite.
-- UNIQUE (member_id): one live invite per seat. Revoking DELETES the row, leaving the seat as the
-- name-only member it already was; there is no revoked state to read.
CREATE TABLE group_invites (
  id          BIGSERIAL PRIMARY KEY,
  group_id    BIGINT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
  member_id   BIGINT NOT NULL UNIQUE REFERENCES group_members(id) ON DELETE CASCADE,
  email       VARCHAR(255),
  token_hash  VARCHAR(64) NOT NULL UNIQUE,
  expires_at  TIMESTAMP NOT NULL,
  consumed_at TIMESTAMP,
  created_by  BIGINT REFERENCES users(id) ON DELETE SET NULL,
  created_at  TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
);

CREATE INDEX idx_group_invites_group_id ON group_invites(group_id);

-- A pot is the container co-ownership attaches to: holdings point at it, and ONE ownership ledger
-- divides the whole of it. Ownership deliberately lives here and never on the holding — a rebalance
-- inside the pot (sell A, buy B) would otherwise have to move ownership units between positions,
-- which is meaningless and a silent source of wrong percentages.
-- name is NULL for a group's default pot: the container is a concept the UI does not surface until a
-- group has a second one to distinguish. base_currency is the currency all ownership math runs in;
-- changing a display currency re-converts, it never moves ownership.
-- visibility is only the DEFAULT for a member with no explicit pot_member_permissions row, so a
-- member who joins the group after the pot exists is covered without any seeding step.
-- snapshot_cadence declares how often the pot is expected to be re-valued. It is an expectation, not
-- a schedule: nothing writes snapshots on its account, and the only thing it changes is what counts
-- as an overdue valuation and how the value series is bucketed.
CREATE TABLE pots (
  id               BIGSERIAL PRIMARY KEY,
  group_id         BIGINT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
  name             VARCHAR(255),
  base_currency    VARCHAR(3) NOT NULL,
  snapshot_cadence pot_cadence NOT NULL DEFAULT 'monthly',
  visibility       pot_visibility NOT NULL DEFAULT 'members',
  is_default       BOOLEAN NOT NULL DEFAULT FALSE,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_pots_group_id ON pots(group_id);
-- At most one default pot per group; partial so the non-default rows are not indexed at all.
CREATE UNIQUE INDEX idx_pots_group_default ON pots(group_id) WHERE is_default;

-- Per-member overrides of a pot's visibility default, and the ONLY source of write access.
-- Membership is not ownership (V3): a member holding 0% of a pot may still see all of it, which is
-- why can_view is keyed to the seat and never to whether the member holds units.
-- `role` appears nowhere here or in the helpers below: group administration is management, not
-- access, and an admin sees precisely what any member sees.
CREATE TABLE pot_member_permissions (
  pot_id     BIGINT NOT NULL REFERENCES pots(id) ON DELETE CASCADE,
  member_id  BIGINT NOT NULL REFERENCES group_members(id) ON DELETE CASCADE,
  can_view   BOOLEAN NOT NULL DEFAULT TRUE,
  can_write  BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (pot_id, member_id),
  -- Writing something you cannot see is not a state the product has a meaning for, and allowing it
  -- would make app_can_write_pot answer true where app_can_view_pot answers false.
  CONSTRAINT pot_member_permissions_write_implies_view CHECK (can_view OR NOT can_write)
);

CREATE INDEX idx_pot_member_permissions_member_id ON pot_member_permissions(member_id);

-- The pot's ownership ledger: dated events that are REPLAYED to derive unit balances. Nothing is
-- stored as a running total, matching how every other balance in Renly is derived.
-- 'opening' sets the baseline (value + percentages at a date, units issued at a nominal 1.00), and
-- nothing before that date is in scope — the same anchor accounts.opening_balance/opening_date are.
-- A contribution ISSUES units at that date's price (the mover's share rises, nobody loses value); a
-- withdrawal redeems them; a reagreement TRANSFERS units between two members and carries no money.
-- Conflating the last two would misstate the history: one is an investment, the other a gift.
-- amount/amount_currency/base_amount store BOTH sides of a cross-currency move and never a derived
-- rate, exactly as transfers and card_settlements already do. amount_currency is NULL when the money
-- moved in the pot's own base currency.
-- unit_price is kept for audit: it is derivable from NAV at the date, but NAV moves as later
-- snapshots arrive, so the price actually used has to be recorded when it is used.
-- from_account_id / to_account_id are what make the event a real MOVEMENT rather than a note about
-- one: a contribution debits the mover's private account and credits an account the pot holds, a
-- withdrawal reverses it, and the per-account balance union reads both legs. Without them the money
-- would leave nowhere and arrive nowhere, so the mover's account would silently keep cash it no
-- longer has and the pot would be priced against a NAV that never moved. Two columns rather than
-- one for exactly the reason transfers has two — this IS the transfer mechanic at a different scope.
-- Both are optional: money can legitimately arrive from outside Renly, or land in a holding that is
-- an investment rather than a tracked account.
CREATE TABLE pot_ownership_events (
  id                     BIGSERIAL PRIMARY KEY,
  pot_id                 BIGINT NOT NULL REFERENCES pots(id) ON DELETE CASCADE,
  type                   ownership_event_type NOT NULL,
  date                   DATE NOT NULL,
  member_id              BIGINT NOT NULL REFERENCES group_members(id) ON DELETE CASCADE,
  counterparty_member_id BIGINT REFERENCES group_members(id) ON DELETE CASCADE,
  amount                 NUMERIC(18, 2),
  amount_currency        VARCHAR(3),
  base_amount            NUMERIC(18, 2),
  units                  NUMERIC(18, 6) NOT NULL,
  unit_price             NUMERIC(18, 6) NOT NULL,
  from_account_id        BIGINT REFERENCES accounts(id) ON DELETE SET NULL,
  to_account_id          BIGINT REFERENCES accounts(id) ON DELETE SET NULL,
  notes                  TEXT,
  created_by             BIGINT REFERENCES users(id) ON DELETE SET NULL,
  created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  -- Only a reagreement names a second member, and it must name a different one: units moving from a
  -- member to themselves is a no-op the replay would count on both sides.
  CONSTRAINT pot_ownership_events_counterparty CHECK (
    (type = 'reagreement') = (counterparty_member_id IS NOT NULL)
    AND (counterparty_member_id IS NULL OR counterparty_member_id <> member_id)
  ),
  -- A unit price is a division by total units outstanding, which is never zero or negative: a pot
  -- cannot be valued at <= 0 for ownership purposes.
  CONSTRAINT pot_ownership_events_positive_price CHECK (unit_price > 0),
  -- Only a contribution or a withdrawal moves money. An opening sets a division baseline and a
  -- reagreement moves units between people; neither has a payment to record, so naming an account on
  -- one would be recording a movement that did not happen.
  CONSTRAINT pot_ownership_events_movement CHECK (
    type IN ('contribution', 'withdrawal')
    OR (from_account_id IS NULL AND to_account_id IS NULL AND amount IS NULL AND amount_currency IS NULL)
  ),
  -- Same reason transfers forbids it: the balance union sums each leg independently, so one account
  -- on both sides would be added and subtracted at once and the row would be a silent no-op.
  CONSTRAINT pot_ownership_events_distinct_accounts CHECK (
    from_account_id IS NULL OR to_account_id IS NULL OR from_account_id <> to_account_id
  )
);

CREATE INDEX idx_pot_ownership_events_pot_date ON pot_ownership_events(pot_id, date);
CREATE INDEX idx_pot_ownership_events_member_id ON pot_ownership_events(member_id);
CREATE INDEX idx_pot_ownership_events_counterparty_member_id
  ON pot_ownership_events(counterparty_member_id) WHERE counterparty_member_id IS NOT NULL;
-- The balance union filters one leg at a time by account and bounds by date, so each leg gets its
-- own composite index rather than a bare FK index — the same shape transfers uses.
CREATE INDEX idx_pot_ownership_events_from_account_date
  ON pot_ownership_events(from_account_id, date) WHERE from_account_id IS NOT NULL;
CREATE INDEX idx_pot_ownership_events_to_account_date
  ON pot_ownership_events(to_account_id, date) WHERE to_account_id IS NOT NULL;

-- Forward FKs from the scoped stock tables to pots, declared here because each of those tables is
-- created before pots exists. ON DELETE RESTRICT on every one, and that is the whole safety story:
-- CASCADE would let deleting a pot (or the group above it) destroy real holdings, and SET NULL would
-- violate the single-owner CHECK by leaving a row with neither owner. A pot that still holds anything
-- therefore cannot be deleted at all — the service refuses it first with a real error, and this is
-- the backstop that makes a silent loss impossible rather than merely unlikely.
ALTER TABLE investments
  ADD CONSTRAINT investments_pot_id_fkey FOREIGN KEY (pot_id) REFERENCES pots(id) ON DELETE RESTRICT;
ALTER TABLE investment_snapshots
  ADD CONSTRAINT investment_snapshots_pot_id_fkey FOREIGN KEY (pot_id) REFERENCES pots(id) ON DELETE RESTRICT;
ALTER TABLE transactions
  ADD CONSTRAINT transactions_pot_id_fkey FOREIGN KEY (pot_id) REFERENCES pots(id) ON DELETE RESTRICT;
ALTER TABLE accounts
  ADD CONSTRAINT accounts_pot_id_fkey FOREIGN KEY (pot_id) REFERENCES pots(id) ON DELETE RESTRICT;
ALTER TABLE account_reconciliations
  ADD CONSTRAINT account_reconciliations_pot_id_fkey FOREIGN KEY (pot_id) REFERENCES pots(id) ON DELETE RESTRICT;
ALTER TABLE transfers
  ADD CONSTRAINT transfers_pot_id_fkey FOREIGN KEY (pot_id) REFERENCES pots(id) ON DELETE RESTRICT;

-- Money settings the group holds in common: the split it proposes by default, and whether a
-- settlement one member records needs the other to confirm it. A SIBLING table rather than columns on
-- `groups` on purpose — `groups` is the membership kernel and carries who the people are and nothing
-- about what they share, which is what lets a non-money module adopt it unchanged. Money settings
-- would be the first thing to break that, permanently.
-- One row per group, created with the group, so every read is a plain join with no "or the default"
-- branch to keep in step with the column defaults.
-- The group's balance display currency §6.2 once sketched is deliberately ABSENT: balances are held in
-- per-currency buckets that never net across currencies, the unified figure beside them converts to
-- each VIEWER's own display currency, and a cross-currency settlement names the currency it was
-- actually paid in. There is no question a group-level one would answer.
CREATE TABLE group_money_settings (
  group_id                  BIGINT PRIMARY KEY REFERENCES groups(id) ON DELETE CASCADE,
  default_split_method      split_method NOT NULL DEFAULT 'equal',
  auto_finalise_settlements BOOLEAN NOT NULL DEFAULT FALSE,
  created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- One expense a group shares. It is deliberately NOT a scoped expense_entries row: an expense with one
-- funding source and an N-way split cannot be one flat row, and expense_entries keeps its simple
-- owner-only RLS while everything here is reachable by every member of the group.
-- Each member's own share appears in their normal /expenses list by a read-time UNION over the splits
-- below — never a mirrored expense_entries row, because an edit here would then have to chase every
-- copy and the copies are what drift.
-- There is NO payer column. Who fronted the money lives on the splits as `paid_amount`, for a reason
-- that is not stylistic: money can come from a SHARED account, in which case the pot's owners fronted
-- it in their own proportions and no single member is the payer. One column cannot say that, and a
-- payer column plus per-member figures would be two records of one fact.
-- The funding source is at most one of the two: an account draws cash on the spot, a card raises a
-- liability now and draws cash later at settlement, and naming both would count one payment twice.
-- Naming NEITHER is legal and common — an expense somebody paid in cash outside Renly still splits.
CREATE TABLE shared_expenses (
  id                   BIGSERIAL PRIMARY KEY,
  group_id             BIGINT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
  date                 DATE NOT NULL,
  amount               NUMERIC(18, 2) NOT NULL,
  currency             VARCHAR(3) NOT NULL,
  category             expense_category,
  split_method         split_method NOT NULL,
  paid_from_account_id BIGINT REFERENCES accounts(id) ON DELETE SET NULL,
  payment_method       VARCHAR(20),
  credit_card_id       BIGINT REFERENCES credit_cards(id),
  notes                TEXT,
  created_by           BIGINT REFERENCES users(id) ON DELETE SET NULL,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  -- A shared expense of nothing has nothing to divide, and a negative one is a refund the split
  -- methods have no meaning for (a percentage of a negative total inverts who owes whom).
  CONSTRAINT shared_expenses_positive_amount CHECK (amount > 0),
  -- The cash leg and the card leg are exclusive, the same rule ensure_account_pairing enforces on a
  -- private expense. Both set would subtract the amount from an account AND add it to a card bucket.
  CONSTRAINT shared_expenses_single_funding CHECK (paid_from_account_id IS NULL OR credit_card_id IS NULL)
);

CREATE INDEX idx_shared_expenses_group_date ON shared_expenses(group_id, date DESC);
-- The balance union filters by account and bounds by date, so the leg gets a composite index rather
-- than a bare FK index — the same shape transfers and the ownership ledger use.
CREATE INDEX idx_shared_expenses_account_date
  ON shared_expenses(paid_from_account_id, date) WHERE paid_from_account_id IS NOT NULL;
CREATE INDEX idx_shared_expenses_credit_card
  ON shared_expenses(credit_card_id) WHERE credit_card_id IS NOT NULL;

-- One member's two sides of one shared expense, and the row the whole feature balances on.
--   * `amount` is what this member CONSUMED — their share, which is the figure that lands in their own
--     /expenses list and their own spending analytics. Sums to the expense's total.
--   * `paid_amount` is what this member FRONTED. Sums to the same total.
-- A member's balance is therefore Σ paid_amount − Σ amount across every split they hold, and the sum
-- over all members is zero in every currency BY CONSTRUCTION rather than by a rule anyone has to
-- remember. That one identity is what makes §4.2's four cases one implementation:
--   * one member pays for a group dinner -> their paid_amount is the total, everyone's amount is their
--     share, and the difference is the receivable;
--   * a SHARED account pays -> the pot's owners front it in their ownership proportions at that date,
--     pinned here as several paid_amounts. Pinned rather than derived because the ownership ledger is
--     replayable, so a back-dated ownership event would otherwise silently rewrite an old balance;
--   * a shared account pays for ONE member's own purchase (the private-expense-from-joint-money case)
--     -> that member's amount is the whole total and the other owners' paid_amounts are what they are
--     owed. No special case anywhere.
-- A row with amount = 0 is a payer who took no part (legal, if uncommon); one with paid_amount = 0 is
-- an ordinary participant. Both zero cannot happen — the service never writes such a row — but it is
-- harmless rather than wrong, so it is not constrained.
-- group_id is denormalized from the parent for RLS, the same way the scoped stock tables carry theirs:
-- a policy that had to join shared_expenses to answer "may I see this" would evaluate that join for
-- every row of every query.
CREATE TABLE shared_expense_splits (
  id                BIGSERIAL PRIMARY KEY,
  shared_expense_id BIGINT NOT NULL REFERENCES shared_expenses(id) ON DELETE CASCADE,
  group_id          BIGINT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
  member_id         BIGINT NOT NULL REFERENCES group_members(id) ON DELETE CASCADE,
  amount            NUMERIC(18, 2) NOT NULL DEFAULT 0,
  paid_amount       NUMERIC(18, 2) NOT NULL DEFAULT 0,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  -- One row per member per expense: the two figures above are that member's whole position in it, so a
  -- second row would be a second opinion about the same fact.
  CONSTRAINT shared_expense_splits_member_once UNIQUE (shared_expense_id, member_id),
  -- Negative figures would let a split "un-consume" or "un-pay", inverting who owes whom while still
  -- summing to the total.
  CONSTRAINT shared_expense_splits_nonnegative CHECK (amount >= 0 AND paid_amount >= 0)
);

CREATE INDEX idx_shared_expense_splits_expense ON shared_expense_splits(shared_expense_id);
-- The /expenses union reads a member's own shares, and the balance reads a group's, so both lookups
-- start here rather than at the parent.
CREATE INDEX idx_shared_expense_splits_member ON shared_expense_splits(member_id);
CREATE INDEX idx_shared_expense_splits_group ON shared_expense_splits(group_id);

-- One recorded payment against a group's balances, and the only thing that clears them.
-- Named apart from card_settlements deliberately: the two are different acts on different ledgers, and
-- the per-account movement feed reads both, so one word for both would make every call site ambiguous.
-- ONE row is visible to both parties and updates both at once (D28) — never two entries to reconcile.
-- Up to THREE amounts, and each answers a different question:
--   * `amount`/`currency` is the BUCKET leg: which per-currency balance this cleared, and by how much.
--     Balances never net across currencies, so a settlement always names exactly one bucket.
--   * `from_amount` is what actually left the payer's own account, in THAT account's currency;
--   * `to_amount` is what actually arrived in the payee's, in theirs.
-- Each cash figure is NULL when it equals `amount` — i.e. when no conversion happened — so the sums
-- read coalesce(from_amount, amount), exactly as card_settlements reads its account leg. Two legs
-- rather than one because a settlement moves money between two DIFFERENT people's accounts: the payer
-- records where it left from and the payee where it arrived, each on their own side.
-- There is deliberately no stored rate: a pair of amounts IS the record of the rate used, and no
-- single direction reads correctly both ways.
-- Both account legs are optional — mark-as-paid with no account named is the v1 default (real payment
-- rails are deferred), and a name-only member has no account to name at all.
CREATE TABLE group_settlements (
  id              BIGSERIAL PRIMARY KEY,
  group_id        BIGINT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
  from_member_id  BIGINT NOT NULL REFERENCES group_members(id) ON DELETE CASCADE,
  to_member_id    BIGINT NOT NULL REFERENCES group_members(id) ON DELETE CASCADE,
  date            DATE NOT NULL,
  amount          NUMERIC(18, 2) NOT NULL,
  currency        VARCHAR(3) NOT NULL,
  status          group_settlement_status NOT NULL DEFAULT 'pending',
  from_account_id BIGINT REFERENCES accounts(id) ON DELETE SET NULL,
  from_amount     NUMERIC(18, 2),
  to_account_id   BIGINT REFERENCES accounts(id) ON DELETE SET NULL,
  to_amount       NUMERIC(18, 2),
  confirmed_at    TIMESTAMPTZ,
  notes           TEXT,
  created_by      BIGINT REFERENCES users(id) ON DELETE SET NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT group_settlements_positive_amount CHECK (amount > 0),
  -- Paying yourself moves the same balance in both directions and clears nothing.
  CONSTRAINT group_settlements_distinct_members CHECK (from_member_id <> to_member_id),
  CONSTRAINT group_settlements_positive_legs CHECK (
    (from_amount IS NULL OR from_amount > 0) AND (to_amount IS NULL OR to_amount > 0)
  ),
  -- Same reason transfers forbids it: the balance union sums each leg independently, so one account on
  -- both sides would be added and subtracted at once and the row would be a silent no-op.
  CONSTRAINT group_settlements_distinct_accounts CHECK (
    from_account_id IS NULL OR to_account_id IS NULL OR from_account_id <> to_account_id
  ),
  -- A write-off is a debt given up on, not a payment: no cash moved, so naming an account would record
  -- a movement that never happened and would move a real balance for it.
  -- Safe against the ON DELETE SET NULL above — clearing an account id only makes this MORE satisfied,
  -- unlike a "leg amount requires its account" CHECK, which 0016 measured to make any account that
  -- ever funded a cross-currency settlement permanently undeletable. That rule is enforced in the
  -- service instead, for exactly that reason.
  CONSTRAINT group_settlements_write_off_moves_nothing CHECK (
    status <> 'written_off' OR (from_account_id IS NULL AND to_account_id IS NULL)
  ),
  -- confirmed_at is the timestamp of the acknowledgement, so it exists in exactly one status.
  CONSTRAINT group_settlements_confirmed_at CHECK ((status = 'confirmed') = (confirmed_at IS NOT NULL))
);

CREATE INDEX idx_group_settlements_group_date ON group_settlements(group_id, date DESC);
CREATE INDEX idx_group_settlements_from_member ON group_settlements(from_member_id);
CREATE INDEX idx_group_settlements_to_member ON group_settlements(to_member_id);
CREATE INDEX idx_group_settlements_from_account_date
  ON group_settlements(from_account_id, date) WHERE from_account_id IS NOT NULL;
CREATE INDEX idx_group_settlements_to_account_date
  ON group_settlements(to_account_id, date) WHERE to_account_id IS NOT NULL;

-- One piece of income a group shares — the mirror of shared_expenses, and a sibling table for the same
-- reasons: income with one arrival point and an N-way split cannot be one flat income_entries row, and
-- income_entries keeps its simple owner-only RLS while everything here is reachable by every member.
-- Each member's own share appears in their normal /income list by a read-time UNION over the splits
-- below, never a mirrored income_entries row.
-- There is NO receiver column, for exactly the reason shared_expenses has no payer column: money can
-- arrive in a SHARED account, in which case the pot's owners received it in their own proportions and
-- no single member is the recipient. Who received what lives on the splits as `received_amount`.
-- `source_investment_id` is the co-owned asset the income came from and drives the DEFAULT split (F1):
-- rent from a property the group co-owns divides by that property's pot proportions unless somebody
-- says otherwise. It is a label and a seed, never a dependency — hence SET NULL rather than a delete
-- guard, since the money really arrived whatever later happens to the asset.
CREATE TABLE shared_income (
  id                   BIGSERIAL PRIMARY KEY,
  group_id             BIGINT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
  date                 DATE NOT NULL,
  amount               NUMERIC(18, 2) NOT NULL,
  currency             VARCHAR(3) NOT NULL,
  category             income_category,
  split_method         split_method NOT NULL,
  destination          income_destination NOT NULL,
  source_investment_id BIGINT REFERENCES investments(id) ON DELETE SET NULL,
  paid_to_account_id   BIGINT REFERENCES accounts(id) ON DELETE SET NULL,
  notes                TEXT,
  created_by           BIGINT REFERENCES users(id) ON DELETE SET NULL,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  -- Shared income of nothing has nothing to divide, and a negative one is a reversal the split methods
  -- have no meaning for (a percentage of a negative total inverts who owes whom).
  CONSTRAINT shared_income_positive_amount CHECK (amount > 0)
  -- Joint money landing in a pot's account, and distributed money not, is the service's rule and not a
  -- CHECK here. It depends on accounts.pot_id, which a CHECK cannot reach; and even "joint names SOME
  -- account" is a write-time rule rather than a table invariant, because paid_to_account_id is
  -- ON DELETE SET NULL — pairing the two columns would turn deleting that account into an
  -- impossibility. A joint row whose account is gone is still truthfully joint, and who was credited
  -- what lives on the split rows.
);

CREATE INDEX idx_shared_income_group_date ON shared_income(group_id, date DESC);
-- The balance union filters by account and bounds by date, so the leg gets a composite index rather
-- than a bare FK index — the same shape shared_expenses, transfers and the ownership ledger use.
CREATE INDEX idx_shared_income_account_date
  ON shared_income(paid_to_account_id, date) WHERE paid_to_account_id IS NOT NULL;
-- Earns its place twice: the remembered per-source default looks a group's rows up by source, and
-- moving an investment out of a pot has to find the income that named it.
CREATE INDEX idx_shared_income_source
  ON shared_income(source_investment_id) WHERE source_investment_id IS NOT NULL;

-- One member's two sides of one piece of shared income, and the row the income half balances on.
--   * `amount` is what this member is ENTITLED to — their share, which is the figure that lands in
--     their own /income list and their own income analytics. Sums to the income's total.
--   * `received_amount` is what actually REACHED them. Sums to the same total.
-- A member's balance is therefore Σ amount − Σ received_amount across every split they hold, and the
-- sum over all members is zero in every currency BY CONSTRUCTION. It is the expense identity with the
-- two sides swapped, and the swap is the honest reading: an entitlement is a claim on the group, while
-- cash that has already arrived is the group having settled part of that claim. So:
--   * rent lands in the group's shared account -> the pot's owners received it in their ownership
--     proportions at that date, pinned here as several received_amounts, and anyone whose agreed share
--     differs from their ownership share holds the difference as a balance. Pinned rather than derived
--     because the ownership ledger is replayable, so a back-dated event would otherwise silently
--     rewrite an old balance;
--   * one member collects the rent -> their received_amount is the whole total, everyone's amount is
--     their share, and the difference is what they owe the others;
--   * the tenant pays each owner their own share directly -> every member's two figures match and
--     nobody owes anybody. No special case anywhere.
-- A row with amount = 0 is somebody who received money they were entitled to none of (a collector who
-- takes no share); one with received_amount = 0 is an ordinary participant still waiting for theirs.
-- group_id is denormalized from the parent for RLS, the same way shared_expense_splits carries its own.
CREATE TABLE shared_income_splits (
  id               BIGSERIAL PRIMARY KEY,
  shared_income_id BIGINT NOT NULL REFERENCES shared_income(id) ON DELETE CASCADE,
  group_id         BIGINT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
  member_id        BIGINT NOT NULL REFERENCES group_members(id) ON DELETE CASCADE,
  amount           NUMERIC(18, 2) NOT NULL DEFAULT 0,
  received_amount  NUMERIC(18, 2) NOT NULL DEFAULT 0,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  -- One row per member per income: the two figures above are that member's whole position in it, so a
  -- second row would be a second opinion about the same fact.
  CONSTRAINT shared_income_splits_member_once UNIQUE (shared_income_id, member_id),
  -- Negative figures would let a split "un-earn" or "un-receive", inverting who owes whom while still
  -- summing to the total.
  CONSTRAINT shared_income_splits_nonnegative CHECK (amount >= 0 AND received_amount >= 0)
);

CREATE INDEX idx_shared_income_splits_income ON shared_income_splits(shared_income_id);
-- The /income union reads a member's own shares and the balance reads a group's, so both lookups start
-- here rather than at the parent.
CREATE INDEX idx_shared_income_splits_member ON shared_income_splits(member_id);
CREATE INDEX idx_shared_income_splits_group ON shared_income_splits(group_id);

-- The notification layer: what a person asked to be told about, what they have been told, and which
-- browsers agreed to receive a push. All three are USER-owned rather than group-scoped — a notification
-- belongs to its recipient, not to the group whose activity produced it — so they take the plain
-- owner-match policy shape below and never call app_is_group_member(). Which members of a group get a
-- row is decided by the fan-out in the service, using the group's own visibility rules; once written,
-- the row is simply that person's.
--
-- Nothing here references a group, a pot or an expense. That is the entity-agnostic requirement, and
-- it is met by the shape rather than by anyone remembering it: an event is a label and its context
-- travels in `payload`.

-- Only OVERRIDES. A missing row means the shipped default (app/domain/notification.py), so there is no
-- seeding step, and a new event has an answer for every existing account on the day it is added.
CREATE TABLE notification_preferences (
  id         BIGSERIAL PRIMARY KEY,
  user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  event      notification_event NOT NULL,
  channel    notification_channel NOT NULL,
  enabled    BOOLEAN NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  -- One answer per person per event per channel; a second row would be a second opinion about the same
  -- switch, and the reader would have to pick one.
  CONSTRAINT notification_preferences_once UNIQUE (user_id, event, channel)
);
-- No index on user_id alone: the only read is "every override this user holds", which the unique
-- constraint's index already serves on its leading column.

-- One thing that happened, addressed to one person. Fanning an event out to five people writes five
-- rows, because read state is per-person and a shared row could not carry it.
CREATE TABLE notifications (
  id         BIGSERIAL PRIMARY KEY,
  user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  event      notification_event NOT NULL,
  -- The values the copy interpolates and the ids its link is built from. JSONB rather than columns
  -- precisely because this table must not know what a pot is: every event carries its own shape.
  -- The feed's prose is rendered by the WEB from `notifications.<event>` translation keys, so a row
  -- re-reads in whatever language the reader is using now and a copy fix reaches old rows.
  payload    JSONB NOT NULL DEFAULT '{}'::jsonb,
  -- Identifies a REPEATING notification so the same one is written at most once; NULL for a one-off.
  dedupe_key VARCHAR(255),
  read_at    TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- The feed is one user's rows newest first, which is the only way this table is ever read.
CREATE INDEX idx_notifications_user_created ON notifications(user_id, created_at DESC);
-- The unread badge counts a user's unread rows, and the partial index is the point: a feed is mostly
-- read, so this stays small however long the history grows.
CREATE INDEX idx_notifications_user_unread ON notifications(user_id) WHERE read_at IS NULL;
-- What makes a repeating notification idempotent. The overdue-valuation reminder is attempted hourly
-- and carries a key naming the pot and the cadence period, so every attempt after the first is a no-op
-- — which replaces a "last notified" column that would have had to live on pots (a per-pot answer to a
-- per-user question) and would have needed its own reset rule when the period rolled over.
-- PARTIAL for SIZE rather than for semantics: NULLs are distinct in a unique index, so two keyless
-- rows would not collide either way. Its one consequence is that an ON CONFLICT naming these columns
-- must repeat the predicate, or the statement raises.
CREATE UNIQUE INDEX idx_notifications_dedupe ON notifications(user_id, event, dedupe_key)
  WHERE dedupe_key IS NOT NULL;

-- One BROWSER that has agreed to receive web push for one account — not one user: the Push API mints a
-- subscription per browser profile per device, so a laptop and a phone are two rows and revoking one
-- must not silence the other.
-- p256dh and auth are the SECRETS the payload is encrypted with: anyone holding them plus the endpoint
-- can push to that browser as if they were Renly. They are treated as credentials rather than data —
-- never logged, never returned by an endpoint, and excluded from the data export, exactly as
-- auth_tokens and refresh_tokens are.
CREATE TABLE push_subscriptions (
  id           BIGSERIAL PRIMARY KEY,
  user_id      BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  -- Globally unique, not unique per user: the same endpoint arriving again is the same browser
  -- re-subscribing, which is an upsert. TEXT because the endpoint is a third-party URL whose shape is
  -- not ours to cap.
  endpoint     TEXT NOT NULL,
  p256dh       VARCHAR(255) NOT NULL,
  auth         VARCHAR(255) NOT NULL,
  user_agent   VARCHAR(500),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  -- Last successful send, set explicitly by the sender: "when did a send last succeed" is a different
  -- question from "when was this row last touched", so there is no updated_at trigger here.
  last_used_at TIMESTAMPTZ,
  CONSTRAINT push_subscriptions_endpoint_once UNIQUE (endpoint)
);
CREATE INDEX idx_push_subscriptions_user ON push_subscriptions(user_id);

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


CREATE TRIGGER trg_investment_collections_updated_at
  BEFORE UPDATE ON investment_collections
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

CREATE TRIGGER trg_transfers_updated_at
  BEFORE UPDATE ON transfers
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_groups_updated_at
  BEFORE UPDATE ON groups
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_group_members_updated_at
  BEFORE UPDATE ON group_members
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_pots_updated_at
  BEFORE UPDATE ON pots
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_pot_member_permissions_updated_at
  BEFORE UPDATE ON pot_member_permissions
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_pot_ownership_events_updated_at
  BEFORE UPDATE ON pot_ownership_events
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_group_money_settings_updated_at
  BEFORE UPDATE ON group_money_settings
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_shared_expenses_updated_at
  BEFORE UPDATE ON shared_expenses
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_shared_expense_splits_updated_at
  BEFORE UPDATE ON shared_expense_splits
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_group_settlements_updated_at
  BEFORE UPDATE ON group_settlements
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_shared_income_updated_at
  BEFORE UPDATE ON shared_income
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_shared_income_splits_updated_at
  BEFORE UPDATE ON shared_income_splits
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Only notification_preferences of the three notification tables. A notification is an immutable record
-- of something that happened (the one field that changes is read_at, whose value IS the timestamp), and
-- a push subscription's mutable field is last_used_at, which the sender sets deliberately.
CREATE TRIGGER trg_notification_preferences_updated_at
  BEFORE UPDATE ON notification_preferences
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

-- Shared money — the two pot-scope helpers, defined here because the stock-table policies below are
-- the first thing that calls them. Same SECURITY DEFINER shape and the same reasons as
-- app_is_group_member() further down: one place to answer the question so per-table copies cannot
-- drift, the body runs as the owner (exempt from RLS) so a policy on a scoped table can consult
-- pot_member_permissions without recursing, search_path is pinned, and the default PUBLIC EXECUTE
-- grant is revoked.
--
-- What "may see this pot" means, in one predicate: an ACTIVE seat in the pot's group, plus permission.
-- Permission is the member's explicit pot_member_permissions row if there is one, and otherwise the
-- pot's own visibility default. That COALESCE is load-bearing — a member who joins the group after a
-- pot was created has no permission row at all, and V4 says they should still see a 'members' pot.
-- Reading the default from the pot means that works with no seeding step anywhere, and a pot set to
-- 'owners' fails closed for exactly the same reason (no row, no access) until an ownership event
-- writes them one.
--
-- `role` appears nowhere: administration never grants visibility, and that is enforced by the SHAPE
-- of this function rather than by anyone remembering the rule. It fails closed with no GUC set,
-- because app_current_user_id() is then NULL and the join matches nothing.
CREATE OR REPLACE FUNCTION app_can_view_pot(p_pot_id BIGINT) RETURNS BOOLEAN
  LANGUAGE sql STABLE SECURITY DEFINER
  SET search_path = public, pg_temp
  AS $$
    SELECT EXISTS (
      SELECT 1 FROM pots p
      JOIN group_members gm ON gm.group_id = p.group_id
      LEFT JOIN pot_member_permissions pmp ON pmp.pot_id = p.id AND pmp.member_id = gm.id
      WHERE p.id = p_pot_id
        AND gm.user_id = app_current_user_id()
        AND gm.is_active
        AND COALESCE(pmp.can_view, p.visibility = 'members')
    )
  $$;

-- Write access has no visibility-style default: it is granted per member and nowhere else, so a pot
-- with no permission rows is readable by its group and writable by nobody (V6 — a pot may name a
-- single custodian with everyone else read-only). A CHECK on pot_member_permissions makes can_write
-- imply can_view, so this can never answer true where app_can_view_pot answers false.
CREATE OR REPLACE FUNCTION app_can_write_pot(p_pot_id BIGINT) RETURNS BOOLEAN
  LANGUAGE sql STABLE SECURITY DEFINER
  SET search_path = public, pg_temp
  AS $$
    SELECT EXISTS (
      SELECT 1 FROM pots p
      JOIN group_members gm ON gm.group_id = p.group_id
      JOIN pot_member_permissions pmp ON pmp.pot_id = p.id AND pmp.member_id = gm.id
      WHERE p.id = p_pot_id
        AND gm.user_id = app_current_user_id()
        AND gm.is_active
        AND pmp.can_write
    )
  $$;

REVOKE ALL ON FUNCTION app_can_view_pot(BIGINT) FROM PUBLIC;
REVOKE ALL ON FUNCTION app_can_write_pot(BIGINT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app_can_view_pot(BIGINT) TO renly_app;
GRANT EXECUTE ON FUNCTION app_can_write_pot(BIGINT) TO renly_app;

-- Dual-scope tables: a row belongs EITHER to a user (user_id) or to a pot (pot_id), never both, and
-- the single-owner CHECK on each table is what makes "never both" true rather than conventional.
-- The predicate is therefore an owner match OR a visible pot, and a query that forgets the pot half
-- returns FEWER rows — it cannot surface anyone else's money.
--
-- Each table gets TWO policies rather than one, and the split is not stylistic. Postgres applies
-- WITH CHECK to the new row on INSERT/UPDATE but has no WITH CHECK for DELETE at all — a single
-- FOR ALL policy whose USING clause named app_can_view_pot would therefore let a read-only member
-- DELETE a shared holding. So reading is its own FOR SELECT policy and every write command is gated
-- by app_can_write_pot on both sides. Multiple permissive policies are OR-ed, so SELECT still
-- resolves to the view predicate (write implies view by CHECK, so the union adds nothing).
--
-- The children (investment_snapshots, transactions, account_reconciliations, transfers) carry the
-- same two columns denormalized from their parent, exactly as their user_id already was — a policy
-- that had to EXISTS-join to the parent would pay that join on every row of every read.
ALTER TABLE investments ENABLE ROW LEVEL SECURITY;
CREATE POLICY investments_scope_read ON investments FOR SELECT
  USING (user_id = app_current_user_id() OR (pot_id IS NOT NULL AND app_can_view_pot(pot_id)));
CREATE POLICY investments_scope_write ON investments FOR ALL
  USING (user_id = app_current_user_id() OR (pot_id IS NOT NULL AND app_can_write_pot(pot_id)))
  WITH CHECK (user_id = app_current_user_id() OR (pot_id IS NOT NULL AND app_can_write_pot(pot_id)));

ALTER TABLE investment_snapshots ENABLE ROW LEVEL SECURITY;
CREATE POLICY investment_snapshots_scope_read ON investment_snapshots FOR SELECT
  USING (user_id = app_current_user_id() OR (pot_id IS NOT NULL AND app_can_view_pot(pot_id)));
CREATE POLICY investment_snapshots_scope_write ON investment_snapshots FOR ALL
  USING (user_id = app_current_user_id() OR (pot_id IS NOT NULL AND app_can_write_pot(pot_id)))
  WITH CHECK (user_id = app_current_user_id() OR (pot_id IS NOT NULL AND app_can_write_pot(pot_id)));

ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;
CREATE POLICY transactions_scope_read ON transactions FOR SELECT
  USING (user_id = app_current_user_id() OR (pot_id IS NOT NULL AND app_can_view_pot(pot_id)));
CREATE POLICY transactions_scope_write ON transactions FOR ALL
  USING (user_id = app_current_user_id() OR (pot_id IS NOT NULL AND app_can_write_pot(pot_id)))
  WITH CHECK (user_id = app_current_user_id() OR (pot_id IS NOT NULL AND app_can_write_pot(pot_id)));

ALTER TABLE accounts ENABLE ROW LEVEL SECURITY;
CREATE POLICY accounts_scope_read ON accounts FOR SELECT
  USING (user_id = app_current_user_id() OR (pot_id IS NOT NULL AND app_can_view_pot(pot_id)));
CREATE POLICY accounts_scope_write ON accounts FOR ALL
  USING (user_id = app_current_user_id() OR (pot_id IS NOT NULL AND app_can_write_pot(pot_id)))
  WITH CHECK (user_id = app_current_user_id() OR (pot_id IS NOT NULL AND app_can_write_pot(pot_id)));

ALTER TABLE account_reconciliations ENABLE ROW LEVEL SECURITY;
CREATE POLICY account_reconciliations_scope_read ON account_reconciliations FOR SELECT
  USING (user_id = app_current_user_id() OR (pot_id IS NOT NULL AND app_can_view_pot(pot_id)));
CREATE POLICY account_reconciliations_scope_write ON account_reconciliations FOR ALL
  USING (user_id = app_current_user_id() OR (pot_id IS NOT NULL AND app_can_write_pot(pot_id)))
  WITH CHECK (user_id = app_current_user_id() OR (pot_id IS NOT NULL AND app_can_write_pot(pot_id)));

ALTER TABLE transfers ENABLE ROW LEVEL SECURITY;
CREATE POLICY transfers_scope_read ON transfers FOR SELECT
  USING (user_id = app_current_user_id() OR (pot_id IS NOT NULL AND app_can_view_pot(pot_id)));
CREATE POLICY transfers_scope_write ON transfers FOR ALL
  USING (user_id = app_current_user_id() OR (pot_id IS NOT NULL AND app_can_write_pot(pot_id)))
  WITH CHECK (user_id = app_current_user_id() OR (pot_id IS NOT NULL AND app_can_write_pot(pot_id)));

-- The users table keys on its own id (a user may read/write only its own row).
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
CREATE POLICY users_self_isolation ON users
  USING (id = app_current_user_id())
  WITH CHECK (id = app_current_user_id());

-- Tables owned directly via a user_id column: identical owner-match policy on each.
ALTER TABLE investment_collections ENABLE ROW LEVEL SECURITY;
CREATE POLICY investment_collections_user_isolation ON investment_collections
  USING (user_id = app_current_user_id()) WITH CHECK (user_id = app_current_user_id());

ALTER TABLE credit_cards ENABLE ROW LEVEL SECURITY;
CREATE POLICY credit_cards_user_isolation ON credit_cards
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

-- investment_collection_members is a pure junction (composite PK, no surrogate user column).
-- Isolation is keyed through the parent investment via an EXISTS-join — both parents
-- belong to the same user (enforced by the SEC-4 cross-tenant FK checks), so checking
-- the investment side is sufficient and the lookup hits the investments primary key.
ALTER TABLE investment_collection_members ENABLE ROW LEVEL SECURITY;
CREATE POLICY investment_collection_members_isolation ON investment_collection_members
  USING (
    EXISTS (
      SELECT 1 FROM investments i
      WHERE i.id = investment_collection_members.investment_id
        AND i.user_id = app_current_user_id()
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM investments i
      WHERE i.id = investment_collection_members.investment_id
        AND i.user_id = app_current_user_id()
    )
  );

-- Shared money (groups) — the ONE policy shape in this schema that is not an owner match.
-- A group's rows belong to the group, so the predicate asks "is the requesting user an ACTIVE member
-- of this group". That question is answered in exactly one place, app_is_group_member(), for two
-- reasons:
--   * a policy ON group_members that sub-queried group_members would be evaluated recursively and
--     Postgres aborts it ("infinite recursion detected in policy for relation"). A SECURITY DEFINER
--     function runs its body as the table owner, which is exempt from RLS, so the lookup terminates;
--   * one helper cannot drift. Three tables (and, from the pot work on, more) ask the same question,
--     and a predicate copy-pasted per table is a predicate that eventually disagrees with itself.
-- Three properties make the shape safe:
--   * `is_active` is inside the helper, so deactivating a seat revokes access in the same statement
--     that removes the person — there is no second place to remember;
--   * it fails closed exactly like the owner match: app_current_user_id() returns NULL for a
--     context-less session, so the EXISTS finds nothing and every group reads as empty;
--   * `role` appears NOWHERE in it. Group administration is management, not access: an admin sees
--     precisely what any member sees. No role in Renly can see more than a member.
-- The self-referential bootstrap: creating a group and accepting an invite both have to write the
-- very membership row this predicate reads, so neither can satisfy it. Rather than widen the policy
-- with an author-based escape hatch (which would outlive the author's own membership), those two use
-- cases run on the privileged owner session — the same posture as the pre-auth invite and auth-token
-- flows. Every other group operation runs on the request session under these policies.
--
-- SECURITY DEFINER, and why it leaks nothing: the function takes a group id and returns a boolean
-- about the CALLING user's own membership, which the caller necessarily already knows. It exposes no
-- row and no other user's data for any argument. search_path is pinned so a caller cannot shadow
-- `group_members` with a temp table of their own.
CREATE OR REPLACE FUNCTION app_is_group_member(p_group_id BIGINT) RETURNS BOOLEAN
  LANGUAGE sql STABLE SECURITY DEFINER
  SET search_path = public, pg_temp
  AS $$
    SELECT EXISTS (
      SELECT 1 FROM group_members gm
      WHERE gm.group_id = p_group_id
        AND gm.user_id = app_current_user_id()
        AND gm.is_active
    )
  $$;

-- SECURITY DEFINER runs as the owner, so the default PUBLIC EXECUTE grant that every function gets
-- is revoked before granting it deliberately. app_current_user_id() keeps the default because it is
-- not SECURITY DEFINER — it reads a GUC and can do nothing its caller could not.
REVOKE ALL ON FUNCTION app_is_group_member(BIGINT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app_is_group_member(BIGINT) TO renly_app;

ALTER TABLE groups ENABLE ROW LEVEL SECURITY;
CREATE POLICY groups_member_isolation ON groups
  USING (app_is_group_member(id)) WITH CHECK (app_is_group_member(id));

-- Keyed through the group, NOT through the row's own user_id: a member must see every seat in their
-- group, including the name-only placeholders, which have no user_id to match on at all. Matching on
-- user_id would show each member only themselves, which is the opposite of a roster.
ALTER TABLE group_members ENABLE ROW LEVEL SECURITY;
CREATE POLICY group_members_member_isolation ON group_members
  USING (app_is_group_member(group_id)) WITH CHECK (app_is_group_member(group_id));

-- Same predicate: an invite is group state, so any member may see that a seat has been invited.
-- Consuming one is the bootstrap case above — the accepter is not a member yet, so this policy hides
-- the row from them and the accept runs on the privileged session.
ALTER TABLE group_invites ENABLE ROW LEVEL SECURITY;
CREATE POLICY group_invites_member_isolation ON group_invites
  USING (app_is_group_member(group_id)) WITH CHECK (app_is_group_member(group_id));

-- The pot tables. Membership alone is NOT the read predicate here, unlike the three tables above: a
-- pot set to 'owners' visibility must be invisible to a member without permission, including the
-- fact that it exists. So reading asks app_can_view_pot() and only writing asks membership.
--
-- The two policies are deliberately shaped so their union is still the view predicate: the write
-- policy's USING clause carries app_can_view_pot too, because permissive policies are OR-ed and a
-- bare membership USING would have quietly widened SELECT back to every member. It also means a pot
-- you cannot see is a pot you cannot rename or delete.
-- WITH CHECK stays membership-only: a pot's FIRST permission row does not exist yet while the pot is
-- being created, so requiring view on the new row would refuse the very insert that establishes it.
-- That is the same self-referential bootstrap group creation has, and it has the same answer — pot
-- creation runs on the privileged session, and the admin gate lives in the service either way.
ALTER TABLE pots ENABLE ROW LEVEL SECURITY;
CREATE POLICY pots_scope_read ON pots FOR SELECT
  USING (app_can_view_pot(id));
CREATE POLICY pots_scope_write ON pots FOR ALL
  USING (app_can_view_pot(id) AND app_is_group_member(group_id))
  WITH CHECK (app_is_group_member(group_id));

-- Permissions are pot state, so they are visible to whoever may see the pot — including the rows
-- describing other members, because V5 says a pot is seen in full or not at all.
-- WITH CHECK is app_can_view_pot on the NEW row and that is the load-bearing half: without it, any
-- authenticated user could insert a permission row naming any pot id and their own seat, and read
-- themselves straight into someone else's shared money. Requiring view first means a permission row
-- can only ever be written for a pot the writer can already see, so no row here widens the set of
-- pots anyone can reach. Which member of that pot may write one is the group admin, and that gate
-- lives in the service, exactly as it does for group_members — the same accepted split: RLS holds
-- the confidentiality boundary, the service holds administration.
ALTER TABLE pot_member_permissions ENABLE ROW LEVEL SECURITY;
CREATE POLICY pot_member_permissions_scope_read ON pot_member_permissions FOR SELECT
  USING (app_can_view_pot(pot_id));
CREATE POLICY pot_member_permissions_scope_write ON pot_member_permissions FOR ALL
  USING (app_can_view_pot(pot_id))
  WITH CHECK (app_can_view_pot(pot_id));

-- The ownership ledger: readable by whoever may see the pot (V5 — every movement and every member's
-- percentage), writable only with write permission. Unlike the two above, this one is genuine money
-- movement rather than configuration, so app_can_write_pot is the right gate and the service does not
-- have to be the only thing standing between a read-only custodian and the ledger.
--
-- The second read branch is not a widening of the visibility model, it is what keeps a PRIVATE
-- balance correct. A contribution debits the mover's own account, so the event is a movement in that
-- account's ledger; if the mover later leaves the group the pot branch stops matching, the event
-- disappears from their balance query, and their private account silently gains back money it no
-- longer holds. The branch matches only rows naming an account the caller OWNS — and the service
-- requires the moving member to own the private leg, so such a row is always the caller's own
-- movement. It therefore exposes nothing about any other member, and no row it returns is one the
-- caller did not make themselves.
ALTER TABLE pot_ownership_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY pot_ownership_events_scope_read ON pot_ownership_events FOR SELECT
  USING (
    app_can_view_pot(pot_id)
    OR EXISTS (
      SELECT 1 FROM accounts a
      WHERE a.id IN (pot_ownership_events.from_account_id, pot_ownership_events.to_account_id)
        AND a.user_id = app_current_user_id()
    )
  );
CREATE POLICY pot_ownership_events_scope_write ON pot_ownership_events FOR ALL
  USING (app_can_write_pot(pot_id))
  WITH CHECK (app_can_write_pot(pot_id));

-- The shared-flow tables. All four are group state, so membership is the gate — the same
-- app_is_group_member() helper the three tables above use, for the same two reasons (no predicate
-- copy-pasted per table, and `role` appears in none of them).
--
-- Two of them additionally need a SECOND read branch, and it is not a widening of the visibility
-- model — it is what keeps a PRIVATE balance correct, exactly as pot_ownership_events' is. A shared
-- expense may be funded from one member's own account or card, and a settlement moves money between
-- two members' own accounts. If that member later leaves the group the membership branch stops
-- matching, the row disappears from their balance query, and their account silently gains back money
-- it no longer holds (or their card sheds a charge it still carries). The branch matches only rows
-- naming an account or card the caller OWNS, so every row it returns is the caller's own movement and
-- it exposes nothing about any other member's.
--
-- Reading is FOR SELECT and every write command is FOR ALL on membership alone. Two policies rather
-- than one because Postgres has no WITH CHECK for DELETE: a single FOR ALL policy carrying the wide
-- read branch would let a former member DELETE the group's expense, not merely see their own leg of it.
ALTER TABLE group_money_settings ENABLE ROW LEVEL SECURITY;
CREATE POLICY group_money_settings_member_isolation ON group_money_settings
  USING (app_is_group_member(group_id)) WITH CHECK (app_is_group_member(group_id));

ALTER TABLE shared_expenses ENABLE ROW LEVEL SECURITY;
CREATE POLICY shared_expenses_scope_read ON shared_expenses FOR SELECT
  USING (
    app_is_group_member(group_id)
    OR EXISTS (
      SELECT 1 FROM accounts a
      WHERE a.id = shared_expenses.paid_from_account_id
        AND a.user_id = app_current_user_id()
    )
    OR EXISTS (
      SELECT 1 FROM credit_cards c
      WHERE c.id = shared_expenses.credit_card_id
        AND c.user_id = app_current_user_id()
    )
  );
CREATE POLICY shared_expenses_scope_write ON shared_expenses FOR ALL
  USING (app_is_group_member(group_id)) WITH CHECK (app_is_group_member(group_id));

-- Splits get NO second branch, and that is a decision rather than an omission. A split says what one
-- member consumed, which is group state and nothing else — it names no account and moves no balance,
-- so nothing goes silently wrong when it stops being visible. Leaving a group therefore removes its
-- expenses from your own /expenses list, which is the same thing leaving does to a pot, and it is
-- visible rather than silent.
ALTER TABLE shared_expense_splits ENABLE ROW LEVEL SECURITY;
CREATE POLICY shared_expense_splits_member_isolation ON shared_expense_splits
  USING (app_is_group_member(group_id)) WITH CHECK (app_is_group_member(group_id));

ALTER TABLE group_settlements ENABLE ROW LEVEL SECURITY;
CREATE POLICY group_settlements_scope_read ON group_settlements FOR SELECT
  USING (
    app_is_group_member(group_id)
    OR EXISTS (
      SELECT 1 FROM accounts a
      WHERE a.id IN (group_settlements.from_account_id, group_settlements.to_account_id)
        AND a.user_id = app_current_user_id()
    )
  );
CREATE POLICY group_settlements_scope_write ON group_settlements FOR ALL
  USING (app_is_group_member(group_id)) WITH CHECK (app_is_group_member(group_id));

-- Shared income mirrors shared_expenses, minus the card branch: income never arrives on a credit card.
-- The account branch is there for the same reason — somebody's own account received the money, so the
-- row is a movement in their own ledger, and without the branch leaving the group would silently take
-- that money back off their balance.
ALTER TABLE shared_income ENABLE ROW LEVEL SECURITY;
CREATE POLICY shared_income_scope_read ON shared_income FOR SELECT
  USING (
    app_is_group_member(group_id)
    OR EXISTS (
      SELECT 1 FROM accounts a
      WHERE a.id = shared_income.paid_to_account_id
        AND a.user_id = app_current_user_id()
    )
  );
CREATE POLICY shared_income_scope_write ON shared_income FOR ALL
  USING (app_is_group_member(group_id)) WITH CHECK (app_is_group_member(group_id));

-- No second branch on the splits, for the reason spelled out above shared_expense_splits.
ALTER TABLE shared_income_splits ENABLE ROW LEVEL SECURITY;
CREATE POLICY shared_income_splits_member_isolation ON shared_income_splits
  USING (app_is_group_member(group_id)) WITH CHECK (app_is_group_member(group_id));

-- The notification layer. Back to the plain owner match: these are the recipient's rows, so
-- app_is_group_member() appears nowhere here even though group activity is what produces them.
ALTER TABLE notification_preferences ENABLE ROW LEVEL SECURITY;
CREATE POLICY notification_preferences_user_isolation ON notification_preferences
  USING (user_id = app_current_user_id()) WITH CHECK (user_id = app_current_user_id());

ALTER TABLE push_subscriptions ENABLE ROW LEVEL SECURITY;
CREATE POLICY push_subscriptions_user_isolation ON push_subscriptions
  USING (user_id = app_current_user_id()) WITH CHECK (user_id = app_current_user_id());

-- notifications is the one user-owned table here with per-command policies rather than one FOR ALL,
-- and INSERT deliberately has NO policy at all. Fanning an event out writes rows for OTHER users,
-- which a `user_id = app_current_user_id()` WITH CHECK could never permit, so the dispatcher runs on
-- the privileged session — the same posture as group creation and invite acceptance. With RLS enabled
-- and no INSERT policy, the request role cannot write a notification through any path: nobody can
-- forge an entry in their own feed, or in anyone else's.
-- UPDATE carries WITH CHECK as well as USING, so marking one read cannot also re-address it to somebody
-- else — defence in depth rather than the only guard, since Postgres also requires an updated row to
-- stay visible under the SELECT policy, and widening either one alone still refuses it. DELETE gets its
-- own policy because Postgres has no WITH CHECK for DELETE.
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
CREATE POLICY notifications_user_read ON notifications FOR SELECT
  USING (user_id = app_current_user_id());
CREATE POLICY notifications_user_update ON notifications FOR UPDATE
  USING (user_id = app_current_user_id()) WITH CHECK (user_id = app_current_user_id());
CREATE POLICY notifications_user_delete ON notifications FOR DELETE
  USING (user_id = app_current_user_id());

-- exchange_rates, asset_prices and cedear_ratios are global reference data keyed by
-- pair/ticker (not by user) and are intentionally left without RLS so every request
-- connection can read them; the scheduler writes them under the owner role.

