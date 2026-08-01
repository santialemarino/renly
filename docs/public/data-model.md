# Data Model

This page explains how Renly organizes your data. No technical background required -- think of it as a map of how the different pieces of information connect to each other.

---

## The building blocks

### Users

Each person has their own account with completely isolated data. Your investments, settings, and metrics are private to you -- no one else can see or modify them.

New accounts confirm their email address (via a link sent at signup) before they can log in. From the account settings page you can change your email or password, export all of your data as a JSON file, and permanently delete your account. Changing your password — or resetting a forgotten one — signs you out everywhere else. Verification and reset links are single-use and expire.

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

Income categories are fixed: `salary`, `freelance`, `bonus`, `investment_returns`, `dividends`, `rental_income`, `sales`, `refunds`, `gifts`, `card_credits_and_refunds`, `account_adjustment`, `other`. Two of those are reserved for the system rather than user-picked (absent from the picker and rejected with 422 on write): `account_adjustment` is the surplus-direction account-reconciliation adjustment, and `card_credits_and_refunds` is **legacy** — card credits used to be recorded as income, but a card bucket only moves on expenses and settlements, so they are now signed expenses instead (see [Credit Card Reconciliations](#credit-card-reconciliations)). The value remains declared but nothing writes it.

Income entries carry `account_reconciliation_id` (nullable, cascade-deletes) when created by the account-reconciliation flow, and a legacy `reconciliation_id` pointing at a card reconciliation, which no longer produces income rows. Either link makes the row a reconciliation's adjustment and therefore read-only — see [Reconciliation-owned entries are not editable](#reconciliation-owned-entries-are-not-editable).

### Expense Entries

An expense entry records money going out. Each entry has a date, amount, currency, optional category, payment method, notes, and a source indicating how it was created (`manual`, `shortcut`, `auto`, `email_parsed`, `subscription`, `installment`, or `reconciliation`).

An entry can also point back to a source plan via `subscription_id` or `installment_id` (both nullable; deleting the plan keeps the historical expense and clears the link). The scheduler sets these FKs when auto-emitting cycle charges (source = `subscription` or `installment`); the expense form's "Linked to subscription or installment" dropdown lets users set them on manual entries too. The pair `(source plan, date)` is unique, so re-running the scheduler is a no-op and a manual entry whose date exactly matches the scheduler's expected cycle date is blocked as a duplicate. When the source is `reconciliation`, the entry is a reconciliation's adjustment and points back at the reconciliation that created it — via `reconciliation_id` for a card statement-period adjustment, or `account_reconciliation_id` for an account true-up (both nullable, both cascade-delete when their reconciliation is removed).

Expenses also carry an optional `payment_obligation_id` back-pointer when they were created via the "Mark paid" flow on a payment obligation (nullable, `ON DELETE SET NULL` — deleting the obligation keeps the historical expense and clears the link). The pointer is informational; it doesn't change how the expense is displayed or aggregated, but it lets the obligation track its own paid-state (see [Payment Obligations](#payment-obligations)).

At most one of `payment_obligation_id`, `subscription_id`, `installment_id` is set on the same row — an expense pays exactly one commitment-type.

Expense categories are fixed: `food`, `dining`, `transport`, `rent`, `utilities`, `health`, `entertainment`, `sports`, `subscriptions`, `clothing`, `education`, `personal_care`, `home_maintenance`, `gifts`, `travel`, `taxes`, `insurance`, `kids`, `pets`, `card_fees_and_taxes`, `card_credits_and_refunds`, `account_adjustment`, `other`. The last three are reserved for the system rather than user-picked: they are absent from the category picker AND rejected with 422 on any create or update (see below): `card_fees_and_taxes` is the charged-more direction of a card reconciliation, `card_credits_and_refunds` is the credit direction (a **negative** amount, so it reduces the card bucket), and `account_adjustment` is either direction of an account reconciliation.

### Reconciliation-owned entries are not editable

An adjustment entry is **derived, not authored**: its amount IS its reconciliation's recorded `difference`. Editing or deleting one directly would leave the reconciliation intact but wrong, so the API refuses both (409 `reconciliation_owned_entry`) and the Expenses and Income tables withhold the row's Edit and Delete actions, showing a lock with an explanation instead.

The reason is that the two link directions are deliberately asymmetric. The entry-side links (`expense_entries` / `income_entries` → the reconciliation) are `ON DELETE CASCADE`, so removing a reconciliation cleanly removes the adjustment it created — which is why **re-running or deleting the reconciliation** is the supported way to change one. The reverse pointers (`adjustment_expense_id` / `adjustment_income_id`, the reconciliation → the entry) are `ON DELETE SET NULL`, so removing the entry instead would leave the reconciliation alive with a null pointer and a `difference` it no longer applies, while the balance it was created to correct silently snapped back.

Ownership is the foreign key, not the `source` value. `source` records provenance and survives a restore, which nulls both links because the reconciliation tables are not restored — so a restored adjustment is an ordinary historical entry that nothing owns, and it stays deletable. Its category is still reserved, so the entry form cannot re-save it; Edit stays hidden for that separate reason (with its own explanation) while Delete remains available.

The reserved categories are enforced, not merely convention: `card_fees_and_taxes`, `card_credits_and_refunds` and `account_adjustment` are rejected on any create or update of an expense, an income entry, or a payment obligation's `expense_category`, and the CSV/XLSX importers do not accept them. Only a reconciliation writes them, building its adjustment row directly rather than through the request layer. Without that rule a user could author a row that is indistinguishable from a computed true-up — a fake balance correction sitting in the very category that exists to tell true-ups apart from real spending.

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

When the user clicks "Reconcile" on a bucket for a closed statement period, they enter the bank's real statement balance. The app computes `difference = statement_balance − computed_balance` and creates a single **signed, card-linked adjustment expense** — positive when the bank charged more than expected, negative when a credit posted — tagged `source = 'reconciliation'` and linked to the reconciliation row via `reconciliation_id`. The adjustment is dated on the period's closing date, so it flows into the next period's running balance naturally. After reconciliation the bucket matches the bank to the cent.

Reconciliations are scoped to `(card, currency, period_start, period_end)`. Re-running for the same scope replaces (the prior row deletes, the cascade drops the prior adjustment, a fresh pair is written). If the user retroactively edits an expense or settlement whose date falls inside a reconciled period, the reconciliation is flagged `stale` and a soft-confirmation dialog suggests re-reconciling.

Both directions create **one signed, card-linked adjustment expense** — positive for a fee or tax, negative for a credit. That signedness is not cosmetic: a bucket balance is `Σ expenses − Σ settlements`, so an expense is the only row type that can move it, and a credit recorded any other way would leave the card overstated. Two dedicated category values keep adjustments out of regular spending breakdowns: `expense_category.card_fees_and_taxes` and `expense_category.card_credits_and_refunds`. Because a category can therefore total below zero, the expense breakdown keeps the negative in its total (net spending is the honest figure) but computes percentages against the positive categories only, and the distribution chart omits it — a pie slice cannot represent a negative.

**A credit is not a deposit.** A refund credited to the card clears card debt and moves no cash, so the adjustment is never account-linked; linking it would both clear the debt and add cash for a single event. A refund paid back to your bank account instead never changes the card statement, so it produces no adjustment here at all — record it as ordinary income deposited to that account.

### Accounts

An account is a cash, bank, or wallet balance -- the asset side of net worth, the mirror of a credit-card liability. Each account has a name, a type (`cash`, `bank`, `wallet`, `other`), a single currency, an opening balance, and the date that opening balance is measured at (which anchors the historical series). Accounts can be archived to hide them from active selection while preserving their history.

The balance is **derived at query time**, never stored -- the same principle as credit-card balances: `opening_balance + linked income − linked expenses − settlements paid from the account + transfers in − transfers out`. Expenses, income, and settlements each carry an optional `account_id` (a NULL link is unattributed and affects no balance). Balances may be negative (a real overdraft). An account's currency is fixed once entries link to it, so the balance never mixes currencies.

Every term is bounded by the account's own `opening_date`. `opening_balance` is by definition the balance **at** that date, so anything dated earlier is already inside it and is not counted again -- an entry back-dated before an account opened does not move that account's balance.

Deleting an account preserves your entry history: linked entries are un-attributed (transfers are the one exception — see below, since half a transfer would skew the other account) (their `account_id` clears), not deleted.

### Transfers

A transfer records money moving between two accounts you own. It is the one movement that is neither income nor an expense, because **your net worth does not change** -- the money just leaves one pool and arrives in another. Without it, an ATM withdrawal or buying dollars would have to be faked as an expense plus an income, which would inflate both of your flow totals for something that was never spending or earning.

Each transfer stores a source account, a destination account, a date, optional notes, and **two amounts**:

- Within a single currency the two are equal, and the app fills the second in for you. They must match: a transfer that credited less than it debited would quietly destroy net worth, so a bank fee is recorded as its own expense rather than shrinking the transfer.
- Across currencies -- buying or selling dollars -- you enter both sides, and the pair **is** the record of the rate you actually got, spread included. No stored exchange rate can reconstruct that, which is why it is asked for rather than inferred.

The two accounts must be different (a transfer to the same account moves nothing), and both amounts must be positive. Deleting an account removes the transfers that reference it: leaving half a transfer behind would silently skew the surviving account's balance.

**Paying someone else is an expense, not a transfer.** A transfer is only ever between two of your own accounts.

### Account Reconciliations

The cash-side counterpart of a card reconciliation, and the mechanism that makes optional linking workable. Because linking every movement is never required, a derived balance drifts from the real one — cash spent without an entry, bank fees, interest, taxes, FX spread. Rather than demanding the user back-fill history, reconciliation lets them state the truth: enter the balance the account actually shows on a date, and the app records it and posts one adjustment for the gap.

It is deliberately simpler than the card version. An account is single-currency and its balance is a point-in-time figure, so there is no statement **period** and no currency bucket — just `as_of_date`, `statement_balance`, the `computed_balance` at that date, and their `difference`. There is no `stale` flag either: a later reconciliation just appends and supersedes the earlier one by date, so there is no replace step. Re-running the same date is self-correcting, because the first adjustment is already part of the computed balance and the second difference comes out zero.

That "supersedes by date" property only holds **forward**, so reconciliation is forward-only by rule: a date earlier than the account's most recent reconciliation is rejected, and only the most recent reconciliation can be deleted. Both guards exist for the same reason — a reconciliation's `computed_balance` is bounded to its own date, so it cannot see an adjustment inserted behind it, and it would silently stop matching the balance the user attested to. Revising an older date means deleting the newer reconciliation first.

`difference = statement_balance − computed_balance`. A positive difference (the account holds more than the app knew) creates an **income**; a negative one creates an **expense**; zero creates nothing. The adjustment is dated on `as_of_date`, linked to the account so it enters the running balance from there forward, tagged `source = 'reconciliation'`, and pointed back at its reconciliation via `account_reconciliation_id`. One dedicated enum value on each side makes true-ups identifiable and separable from itemised spending: `expense_category.account_adjustment` and `income_category.account_adjustment`. They label the row rather than exclude it — an adjustment still counts toward income and expense totals and appears in the category breakdown, because the money it accounts for really did move. The card reconciliation categories work the same way.

Deleting a reconciliation cascades to its adjustment, returning the balance to what it was before the true-up. Deleting the **account** does the same to all of its reconciliations and their adjustments — the one place where deleting an account removes entries rather than un-attributing them, because a true-up exists only to make that account's balance right and is meaningless once the account is gone. Entries you created yourself are still only un-attributed, never deleted.

### Subscriptions

A subscription represents a recurring charge (e.g. Netflix, Spotify, gym). Each subscription has a name, amount, currency, billing cycle (`monthly`, `annual`, `quarterly`, `biweekly`, `weekly`), an active flag, and the date of its next billing event. It optionally links to a payment method and credit card.

A daily scheduled job auto-generates one expense entry per billing cycle and advances `next_billing_date` to the next future cycle. Subscriptions registered with a past `next_billing_date` are back-filled in a single tick — every missed cycle gets its own historical-dated expense.

`next_billing_date` is scheduler-owned but also advanced (and reversed) by manual entries linked to the subscription. The advance fires only when the entry's closest cycle equals the current cursor; multi-jump cases (entry matches a cycle ahead of the cursor — pre-pay or mis-click) save the link but leave the cursor untouched, with the scheduler's back-fill loop + the partial UNIQUE INDEX dedup handling catch-up naturally so intermediate cycles still get expense rows. Back-dated entries also never advance. **Reverse:** deleting or unlinking the most-recent linked expense (sort by `date DESC`, `id DESC`) walks `next_billing_date` back by one cycle; middle-of-chain deletions leave the cursor alone. Editing a linked expense's date recomputes the cursor the same way — the old date's advance is reversed and the new date's re-applied on the same subscription. Tolerance for the closest-cycle search scales with the cycle: `min(cycle_length_in_days // 2, 60)`.

The day-of-month is preserved across short-month clamps via an internal `anchor_day` field (1-31, auto-derived from `next_billing_date.day` and not exposed in the form). A subscription billed on the 31st walks Jan 31 → Feb 28 → Mar 31 → Apr 30 → May 31 without drifting to day-28. Weekly and biweekly cycles ignore `anchor_day` since they advance by literal days.

### Installments

An installment plan represents a multi-cuota purchase (e.g. "TV Samsung 12x"). Each plan has a name, total amount, per-cuota amount, currency, total cuota count, the index of the next cuota to issue, an active flag, and a start date. Like subscriptions, it optionally links to a payment method and credit card.

A daily scheduled job auto-generates one expense entry per cuota at its real cuota date (`start_date + (n-1) months`), increments `current_installment`, and flips `is_active` to `false` when the last cuota is issued. Plans registered with a past `start_date` back-fill all due cuotas in a single tick.

`current_installment` is scheduler-owned but also advanced (and reversed) by manual entries linked to the plan. The advance fires only when the matched cuota index equals the current cursor; multi-jump cases (entry matches a cuota ahead of the cursor — pre-pay or mis-click) save the link but leave the cursor untouched. The scheduler's back-fill loop then emits intermediate cuotas on their own dates and dedups the matched one at the partial UNIQUE INDEX, so every cuota gets an expense row naturally (no silent skips). Back-dated entries never advance. **Reverse:** deleting or unlinking the most-recent linked expense walks `current_installment` back by one cuota and re-activates the plan when the reverse moves the cursor back inside the cuota grid (a previous advance to `current = count + 1` flipped `is_active = false`). Editing a linked expense's date recomputes the cursor the same way — the old date's advance is reversed and the new date's re-applied on the same plan.

Once any cuota has been charged (`current_installment > 1`), the contractual fields on the plan -- `total_amount`, `installment_amount`, `installments_count`, `currency`, `start_date`, `payment_method`, `credit_card_id` -- are locked. Always editable: name, current_installment (manual correction), is_active (archive). Attempting to change a locked field returns a 400 with code `installment_locked_field`.

### Payment Obligations

A payment obligation records a recurring or one-off bill (electricity, ABL, internet, etc.). Each obligation has a name, amount, currency, anchor due date (`next_due_date` — the date of the next occurrence; recurring obligations project forward from this), optional recurrence (`monthly`, `bimonthly`, `quarterly`, `annual`, or none for one-off), a free-form `category` label (e.g. "ABL", "Cable"), a structured `expense_category` enum (reuses the expense category enum so dashboards can slice cleanly and Mark Paid pre-fills the linked expense's category), optional payment method/credit card, an active flag, and notes.

Obligations are not auto-generated as expenses — they exist as upcoming commitments that surface in the Payments Calendar (Phase 3, Step 4) so you can see what's due ahead. When you actually pay one, you click "Mark paid" on the obligations table OR pick the obligation from the expense form's "Linked to obligation" dropdown: saving creates a linked expense (with `payment_obligation_id` set) AND auto-advances the obligation. For recurring obligations the advance moves `next_due_date` forward by one recurrence cycle (anchor-day preserved across short-month clamps via `add_months_anchored`); for one-off obligations the advance flips `is_active = false`. Each linked expense advances ONE cycle, so paying two cycles upfront simply creates two expenses. **Reverse:** deleting or unlinking the most-recent linked expense (sort by `date DESC`, `id DESC`) walks `next_due_date` back by one recurrence cycle (recurring) or re-activates the row (one-off, date unchanged). Middle-of-chain deletions leave the cursor alone.

On the Payments Calendar, paid cycles show with a "Paid" badge instead of the default type-specific badge. This applies symmetrically across all three commitment types: a paid obligation cycle (period contains a linked expense via `payment_obligation_id`), a paid subscription cycle (an expense tagged `subscription_id` bound to that cycle), or a paid installment cuota (an expense tagged `installment_id` bound to that cuota). A linked expense is bound to the cycle its date is closest to, so a payment logged a few days off the exact cycle date still marks that cycle Paid. The calendar walks BOTH forward and backward from each commitment's "next" anchor so the user sees both unpaid future events AND past paid events inside the viewed month. Clicking a Paid badge opens the linked expense's edit dialog inline on the calendar (no navigation).

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
- The **dashboard health-indicator thresholds** — all user-configurable from the `/alerts` page, with sensible defaults when unset:
  - `liquidity_threshold_pct` (integer 1–99, default 40) — drives the Liquidity card.
  - `savings_rate_healthy_pct` (integer 1–99, default 20) — Savings Rate "healthy" cut-off.
  - `savings_rate_moderate_pct` (integer 1–99, default 10) — Savings Rate "moderate" cut-off (below this is "at risk").
  - `income_expense_ratio_healthy` (decimal `[0.1, 10.0]`, default 1.5) — Income/Expense ratio "healthy" cut-off. The "amber" pivot is break-even (1.0) and stays hardcoded.

**Credit card revolving-debt handling:** credit cards have an optional `monthly_payment` column. When **set**, the value counts as a fixed monthly commitment in the dashboard Liquidity ratio (typical use: revolving-debt users who carry a balance and pay a roughly constant amount each month). When **null**, the card is treated as paid-in-full and excluded from the ratio — the timing of card spending vs settlement is just balance noise, not a real future commitment. Card-funded subscriptions / installments / obligations are already in the ratio via their own rows regardless of `monthly_payment`. Matches how YNAB and Monarch model revolving debt.

---

## How everything connects

```
User
 |
 |-- has many --> Income Entries
 |                (salary, freelance, dividends, etc.)
 |                  |
 |                  |-- optionally linked to --> Account
 |                                              (the account it was deposited to)
 |
 |-- has many --> Expense Entries
 |                (food, transport, rent, etc.)
 |                  |
 |                  |-- optionally linked to --> Credit Card
 |                  |                           (when payment_method = credit_card)
 |                  |
 |                  |-- optionally linked to --> Account
 |                                              (the account it was paid from;
 |                                               never both a card and an account)
 |
 |-- has many --> Credit Cards
 |                (liability accounts)
 |                  |
 |                  |-- has many --> Card Settlements
 |                  |                (payments that reduce the card balance;
 |                  |                 optionally drawn from an Account)
 |                  |
 |                  |-- has many --> Card Reconciliations
 |                                  (per-bucket statement true-ups against the bank;
 |                                   each owns one signed adjustment expense)
 |
 |-- has many --> Accounts
 |                (cash / bank / wallet balances — the asset side of net worth)
 |                  |
 |                  |-- has many --> Account Reconciliations
 |                                  (point-in-time true-ups against the real balance;
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
