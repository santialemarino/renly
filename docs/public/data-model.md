# Data Model

This page explains how Renly organizes your data. No technical background required -- think of it as a map of how the different pieces of information connect to each other.

---

## The building blocks

### Users

Each person has their own account with completely isolated data. Your investments, settings, and metrics are private to you -- no one else can see or modify them.

### Investments

An investment is any financial holding you want to track. It could be a stock, a term deposit, a dollar position, a mutual fund, crypto, a bond, real estate, or anything else.

Each investment has:

- A **name** you choose (e.g., "Apple shares", "Plazo fijo Galicia")
- A **category** that determines how it behaves (see [Investment Categories](investment-categories.md))
- A **base currency** -- the currency the investment is naturally measured in (e.g., USD for US stocks, ARS for term deposits)
- An optional **ticker** for automatic pricing (e.g., `AAPL` for Apple, `BTC` for Bitcoin)
- An optional **broker** to remember where you hold it (e.g., "Cocos Capital", "IOL")

Investments can be **archived** when you close a position. Archived investments disappear from your active portfolio but their history is preserved -- you can always unarchive them later.

### Snapshots

A snapshot records the value of an investment at a specific point in time, typically the end of each month. Think of it as one cell in a spreadsheet where each column is a month and each row is an investment.

Each snapshot stores:

- The **date** (e.g., January 31, 2026)
- The **value** in the investment's currency (e.g., $9,125.00)
- Optionally, the **quantity** of shares or units held (e.g., 50 shares)

There can only be **one snapshot per investment per month**. If you enter a new value for the same month, it replaces the previous one.

For investments with a ticker, snapshots can be generated **automatically** using market prices. For everything else, you enter the value yourself during monthly data entry.

### Transactions

Transactions record money movements -- when you buy more, sell some, deposit additional capital, or withdraw. There are four types:

- **Buy** -- Purchasing shares or units
- **Sell** -- Selling shares or units
- **Deposit** -- Adding money to the investment
- **Withdrawal** -- Taking money out

Why are transactions separate from snapshots? Because you need to know whether your investment grew because the market went up or because you added more money. Without tracking transactions, a $1,000 deposit would look like a $1,000 gain, making your return numbers meaningless.

### Groups

Groups are labels you create to organize your investments however you want. Examples:

- "Retirement" -- long-term holdings
- "Trading" -- short-term positions
- "Kids" -- investments earmarked for your children

An investment can belong to **multiple groups** (or none at all). Groups let you filter your dashboard to see metrics for just a slice of your portfolio.

Each group can optionally have a **target allocation percentage** (e.g., "Retirement: 40%"). The dashboard shows how your actual allocation compares to your target -- helping you spot when you're over or under-exposed in a group.

### Exchange Rates

Renly stores historical exchange rates updated automatically every day:

- **USD/ARS** in three flavors: oficial (government rate), MEP (financial market rate), and blue (informal market rate) -- sourced from DolarApi
- **USD/BRL, USD/EUR, USD/GBP** -- sourced from Frankfurter (European Central Bank data)

All currency conversions go through USD as a pivot. For example, to convert from BRL to ARS, the app converts BRL to USD first, then USD to ARS. This keeps the system simple while supporting any currency pair.

### Asset Prices

For investments with a ticker (stocks, CEDEARs, crypto, government bonds), Renly stores historical prices fetched from external providers like Yahoo Finance and CoinGecko. These prices power automatic snapshots and let you look up past prices when entering historical data.

### CEDEAR Ratios

CEDEARs have a conversion ratio to their underlying stock. For example, 10 CEDEARs of AAPL.BA might equal 1 share of Apple stock. These ratios are updated monthly from Banco Comafi, the principal issuing entity for stock CEDEARs in Argentina (90%+ of programs). Ratios change only when the underlying stock splits.

### Income Entries

An income entry records money coming in -- your salary, freelance work, dividends, refunds, or any other source. Each entry has a date, amount, currency, and optional category and notes.

Income categories are fixed: `salary`, `freelance`, `bonus`, `investment_returns`, `dividends`, `rental_income`, `sales`, `refunds`, `gifts`, `card_credits_and_refunds`, `other`. The `card_credits_and_refunds` value is reserved for the negative-direction reconciliation adjustment (when the bank credited more than the app computed). Income entries also carry `reconciliation_id` (nullable, cascade-deletes) when created by the reconciliation flow.

### Expense Entries

An expense entry records money going out. Each entry has a date, amount, currency, optional category, payment method, notes, and a source indicating how it was created (`manual`, `shortcut`, `auto`, `email_parsed`, `subscription`, `installment`, or `reconciliation`).

When the source is `subscription` or `installment`, the entry was auto-generated by the daily scheduler and points back to the source plan via `subscription_id` or `installment_id` (both nullable; deleting the plan keeps the historical expense and clears the link). The pair `(source plan, date)` is unique, so re-running the scheduler is a no-op. When the source is `reconciliation`, the entry was created by the card-reconciliation flow as a statement-period adjustment and points back to the reconciliation row via `reconciliation_id` (cascade-deletes if the reconciliation is removed).

Expenses also carry an optional `payment_obligation_id` back-pointer when they were created via the "Mark paid" flow on a payment obligation (nullable, `ON DELETE SET NULL` — deleting the obligation keeps the historical expense and clears the link). The pointer is informational; it doesn't change how the expense is displayed or aggregated, but it lets the obligation track its own paid-state (see [Payment Obligations](#payment-obligations)).

Expense categories are fixed: `food`, `dining`, `transport`, `rent`, `utilities`, `health`, `entertainment`, `sports`, `subscriptions`, `clothing`, `education`, `personal_care`, `home_maintenance`, `gifts`, `travel`, `taxes`, `insurance`, `kids`, `pets`, `card_fees_and_taxes`, `other`. The `card_fees_and_taxes` value is reserved for the positive-direction reconciliation adjustment.

Payment methods: `cash`, `debit`, `transfer`, `credit_card`. When the payment method is `credit_card`, the entry links to a specific credit card -- increasing that card's liability balance.

### Credit Cards

A credit card is a liability account -- it represents money you owe. Each card has a name, closing day, due day, and a primary currency (the statement issuance currency). Cards can be archived to hide them from active selection while preserving their history.

Card balance is reported **per currency bucket**: one bucket per currency that has activity on the card. The primary currency always has a bucket (zero when no activity). Other buckets emerge automatically from the first expense in a non-primary currency -- matching how Argentine resúmenes print "Saldo en pesos" + "Saldo en dólares" on the same physical card. Each bucket's balance is `sum(expenses in this currency) - sum(settlements in this currency)`, with no cross-currency conversion at display time. Single-currency cards collapse to one bucket -- zero overhead for non-Argentine users.

For per-statement displays (Payments Calendar `card_due` events, the Reconcile dialog) the app computes a **running-balance snapshot** at the statement's closing date: `sum(all expenses dated ≤ closing_date) − sum(all settlements dated ≤ closing_date)` for that bucket. Unpaid balance from prior statements is carried forward implicitly — the snapshot at Apr 28 already includes anything left over from March.

A card can only be deleted if it has no linked expenses.

### Card Settlements

A settlement records a credit card payment. Settlements are **not expenses** -- they reduce both your bank balance and the card's liability, with net-zero effect on patrimony.

Settlements are flat: just a date, an amount, a currency (the bucket they reduce), and an optional note. They are **not** tagged with a statement period — you don't pick "which statement is this paying." When the app needs to display a per-statement amount (e.g. on the Payments Calendar or during reconciliation), it computes the running balance at that statement's closing date. Carryover from earlier unpaid statements is implicit, matching how a real bank resumen works.

For the full accounting model (how expenses create liabilities, how settlements reduce them, how balance is computed, how period snapshots are derived), see [Credit Card Liability Model](../technical/credit-card-liability-model.md).

### Card Reconciliations

A reconciliation is a per-bucket, per-statement true-up against the bank. Even with correct currency conversion and accurate settlements, the bank's actual statement balance rarely equals what the app computes — Argentina's 30% Ganancias perception, Visa / Mastercard FX fees, IVA on digital services, provincial sellos, refunds, and network rounding all sit outside the model.

When the user clicks "Reconcile" on a bucket for a closed statement period, they enter the bank's real statement balance. The app computes `difference = statement_balance − computed_balance` and creates a single adjustment — either an expense (when the bank charged more than expected) or income (when the bank credited more than expected) — tagged `source = 'reconciliation'` and linked to the reconciliation row via `reconciliation_id`. The adjustment is dated on the period's closing date, so it flows into the next period's running balance naturally. After reconciliation the bucket matches the bank to the cent.

Reconciliations are scoped to `(card, currency, period_start, period_end)`. Re-running for the same scope replaces (the prior row deletes, the cascade drops the prior adjustment, a fresh pair is written). If the user retroactively edits an expense or settlement whose date falls inside a reconciled period, the reconciliation is flagged `stale` and a soft-confirmation dialog suggests re-reconciling.

Two dedicated category enum values exist for the adjustments so they're cleanly excluded from regular spending breakdowns: `expense_category.card_fees_and_taxes` and `income_category.card_credits_and_refunds`.

### Subscriptions

A subscription represents a recurring charge (e.g. Netflix, Spotify, gym). Each subscription has a name, amount, currency, billing cycle (`monthly`, `annual`, `quarterly`, `biweekly`, `weekly`), an active flag, and the date of its next billing event. It optionally links to a payment method and credit card.

A daily scheduled job auto-generates one expense entry per billing cycle and advances `next_billing_date` to the next future cycle. Subscriptions registered with a past `next_billing_date` are back-filled in a single tick — every missed cycle gets its own historical-dated expense.

The day-of-month is preserved across short-month clamps via an internal `anchor_day` field (1-31, auto-derived from `next_billing_date.day` and not exposed in the form). A subscription billed on the 31st walks Jan 31 → Feb 28 → Mar 31 → Apr 30 → May 31 without drifting to day-28. Weekly and biweekly cycles ignore `anchor_day` since they advance by literal days.

### Installments

An installment plan represents a multi-cuota purchase (e.g. "TV Samsung 12x"). Each plan has a name, total amount, per-cuota amount, currency, total cuota count, the index of the next cuota to issue, an active flag, and a start date. Like subscriptions, it optionally links to a payment method and credit card.

A daily scheduled job auto-generates one expense entry per cuota at its real cuota date (`start_date + (n-1) months`), increments `current_installment`, and flips `is_active` to `false` when the last cuota is issued. Plans registered with a past `start_date` back-fill all due cuotas in a single tick.

Once any cuota has been charged (`current_installment > 1`), the contractual fields on the plan -- `total_amount`, `installment_amount`, `installments_count`, `currency`, `start_date`, `payment_method`, `credit_card_id` -- are locked. Always editable: name, current_installment (manual correction), is_active (archive). Attempting to change a locked field returns a 400 with code `installment_locked_field`.

### Payment Obligations

A payment obligation records a recurring or one-off bill (electricity, ABL, internet, etc.). Each obligation has a name, amount, currency, anchor due date (`next_due_date` — the date of the next occurrence; recurring obligations project forward from this), optional recurrence (`monthly`, `bimonthly`, `quarterly`, `annual`, or none for one-off), a free-form `category` label (e.g. "ABL", "Cable"), a structured `expense_category` enum (reuses the expense category enum so dashboards can slice cleanly and Mark Paid pre-fills the linked expense's category), optional payment method/credit card, an active flag, and notes.

Obligations are not auto-generated as expenses — they exist as upcoming commitments that surface in the Payments Calendar (Phase 3, Step 4) so you can see what's due ahead. When you actually pay one, you click "Mark paid" on the obligations table: this opens the expense form pre-filled from the obligation, and saving creates a linked expense (with `payment_obligation_id` set) AND auto-advances the obligation. For recurring obligations the advance moves `next_due_date` forward by one recurrence cycle (anchor-day preserved across short-month clamps via `add_months_anchored`); for one-off obligations the advance flips `is_active = false`. Each linked expense advances ONE cycle, so paying two cycles upfront simply creates two expenses. The advance is one-way — editing or deleting a linked expense later does NOT undo it; if you over-advanced by mistake, edit `next_due_date` on the obligation form to correct it.

On the Payments Calendar, paid cycles show with a "Paid" badge instead of the default type-specific badge. This applies symmetrically across all three commitment types: a paid obligation cycle (period contains a linked expense via `payment_obligation_id`), a paid subscription cycle (scheduler-emitted expense tagged `subscription_id` at that cycle's date), or a paid installment cuota (auto-row tagged `installment_id` at that cuota's date). The calendar walks BOTH forward and backward from each commitment's "next" anchor so the user sees both unpaid future events AND past paid events inside the viewed month. Clicking a Paid badge opens the linked expense's edit dialog inline on the calendar (no navigation).

### API Keys

API keys allow external tools (like iOS Shortcuts) to authenticate without a full login flow. Each key has a name, is tied to a user, and can be revoked. The raw key is shown only once at creation.

### Settings

Each user has personal preferences that control how the app behaves:

- Which currencies to display (primary and secondary)
- Which USD/ARS rate to use for conversions (oficial, MEP, or blue)
- Dashboard period presets and display options
- Which currencies to show in the iOS Shortcut currency picker (defaults to primary + secondary)
- The user's timezone (IANA name like `America/Argentina/Buenos_Aires`) plus a mode flag (`auto` or `manual`). In auto mode the browser-detected timezone is silently kept in sync on every page load; in manual mode the stored value sticks until the user changes it. The auto-expense scheduler uses this to fire recurring charges on the user's local calendar day instead of the server's UTC day.
- The user's language (`en` or `es`) plus a mode flag (`auto` or `manual`) — mirrors the timezone pattern.
- Account caps and warning thresholds: `max_groups`, `group_warning_pct` (when investment groups approach the cap, the UI warns).
- The **liquidity-alert threshold** (`liquidity_threshold_pct`, integer 1–99). Drives the colour band on the dashboard's Liquidity card — see [metrics](metrics.md) for the formula. Defaults to 40% when unset.

**Why credit card balance is excluded from the liquidity ratio:** Renly's data model doesn't yet distinguish between users who pay their card in full each month (where the balance is just timing noise) and users who carry a balance (where a real monthly payment exists). Including the full outstanding balance would over-report dramatically for the first group; making up a "minimum payment" without a stored field would fabricate numbers. Card-funded subscriptions / installments / obligations are already in the count via their own rows, so they're not missed. A future enhancement may add an optional `monthly_payment` field per card for users with revolving debt.

---

## How everything connects

```
User
 |
 |-- has many --> Income Entries
 |                (salary, freelance, dividends, etc.)
 |
 |-- has many --> Expense Entries
 |                (food, transport, rent, etc.)
 |                  |
 |                  |-- optionally linked to --> Credit Card
 |                                              (when payment_method = credit_card)
 |
 |-- has many --> Credit Cards
 |                (liability accounts)
 |                  |
 |                  |-- has many --> Card Settlements
 |                  |                (payments that reduce the card balance)
 |                  |
 |                  |-- has many --> Card Reconciliations
 |                                  (per-bucket statement true-ups against the bank;
 |                                   each owns an adjustment expense or income)
 |
 |-- has many --> Subscriptions
 |                (recurring charges; the daily scheduler auto-generates one expense per cycle)
 |                  |
 |                  |-- optionally linked to --> Credit Card
 |
 |-- has many --> Installments
 |                (cuota plans; the daily scheduler auto-generates one expense per cuota)
 |                  |
 |                  |-- optionally linked to --> Credit Card
 |
 |-- has many --> Payment Obligations
 |                (upcoming bills; surfaces in Payments Calendar)
 |                  |
 |                  |-- optionally linked to --> Credit Card
 |
 |-- has many --> Investments
 |                  |
 |                  |-- has many --> Snapshots
 |                  |                (one per month: the value at that point in time)
 |                  |
 |                  |-- has many --> Transactions
 |                  |                (buys, sells, deposits, withdrawals)
 |                  |
 |                  |-- belongs to many --> Groups
 |                                         (user-defined labels like "Retirement")
 |
 |-- has many --> Groups
 |                (each group can contain many investments)
 |
 |-- has many --> API Keys
 |                (for iOS Shortcut / external tool access)
 |
 |-- has --> Settings
              (currency preferences, display options)
```

**Supporting data** (shared across all users):

```
Exchange Rates ..... daily rates for USD/ARS, USD/BRL, USD/EUR, USD/GBP
Asset Prices ....... daily prices for stocks, CEDEARs, crypto, bonds
CEDEAR Ratios ...... how many CEDEARs equal one underlying share
```

---

## Key design principles

**Original currency storage.** All values (snapshots, transactions) are stored in their original currency. If you buy Apple stock, the value is stored in USD. If you have a plazo fijo, it's stored in ARS. Conversion to your display currency happens on the fly using the exchange rates table. This means no information is ever lost, and switching your display currency always gives you accurate numbers.

**One snapshot per month.** Each investment gets exactly one snapshot per date. If you enter a value for March 2026 and later correct it, the old value is replaced. This keeps things simple -- one number per month, just like a spreadsheet column.

**Transactions are separate from value.** Your portfolio value (snapshots) and your money movements (transactions) are tracked independently. This separation is what makes accurate return calculations possible.

**Credit cards are liabilities, not expenses.** When you buy something with a credit card, the expense is recorded immediately and the card balance increases as a liability. When you pay the statement, you record a settlement that reduces both your bank and the liability. This avoids double-counting and keeps all metrics accurate. See [Credit Card Liability Model](../technical/credit-card-liability-model.md) for the full accounting details.
