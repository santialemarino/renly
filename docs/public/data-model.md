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

### Collections

Collections are labels you create to organize your investments however you want. Examples:

- "Retirement" -- long-term holdings
- "Trading" -- short-term positions
- "Kids" -- investments earmarked for your children

An investment can belong to **multiple collections** (or none at all). Collections let you filter your dashboard to see metrics for just a slice of your portfolio.

Each collection can optionally have a **target allocation percentage** (e.g., "Retirement: 40%"). The dashboard shows how your actual allocation compares to your target -- helping you spot when you're over or under-exposed in a collection.

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

A settlement records a credit card payment. Settlements are **not expenses** -- they reduce both your bank balance and the card's liability, with net-zero effect on patrimony **within one currency**. Paying a foreign-currency bucket from a local account records two amounts (what cleared the card, and what your bank actually debited); the difference between them is the real exchange + tax cost of that payment.

Settlements are flat: just a date, an amount, a currency (the bucket they reduce), and an optional note. They are **not** tagged with a statement period — you don't pick "which statement is this paying." When the app needs to display a per-statement amount (e.g. on the Payments Calendar or during reconciliation), it computes the running balance at that statement's closing date. Carryover from earlier unpaid statements is implicit, matching how a real bank resumen works.

For the full accounting model (how expenses create liabilities, how settlements reduce them, how balance is computed, how period snapshots are derived), see [Credit Card Liability Model](../technical/credit-card-liability-model.md).

### Card Reconciliations

A reconciliation is a per-bucket, per-statement true-up against the bank. Even with correct currency conversion and accurate settlements, the bank's actual statement balance rarely equals what the app computes — Argentina's 30% Ganancias perception, Visa / Mastercard FX fees, IVA on digital services, provincial sellos, refunds, and network rounding all sit outside the model.

When the user clicks "Reconcile" on a bucket for a closed statement period, they enter the bank's real statement balance. The app computes `difference = statement_balance − computed_balance` and creates a single **signed, card-linked adjustment expense** — positive when the bank charged more than expected, negative when a credit posted — tagged `source = 'reconciliation'` and linked to the reconciliation row via `reconciliation_id`. The adjustment is dated on the period's closing date, so it flows into the next period's running balance naturally. After reconciliation the bucket matches the bank to the cent.

Reconciliations are scoped to `(card, currency, period_start, period_end)`. Re-running for the same scope replaces (the prior row deletes, the cascade drops the prior adjustment, a fresh pair is written).

A reconciliation is flagged `stale` when anything its recorded figures were derived from changes afterwards. The period bounds name _which_ statement; they do not scope the arithmetic — the balance sums every charge and settlement dated on or before `period_end`, from the beginning of the bucket's history. So an edit dated **before** a reconciled period still moves its balance and still flags it, and reconciling (or deleting) an **older** statement flags every later one, because the adjustment posted or removed is itself a dated row inside their balances.

A stale statement shows an amber badge explaining what happened, and the reconcile dialog repeats it as a banner, so refreshing it is one click.

That is why card reconciliation has no forward-only rule while the account version does. Because re-running a card statement _replaces_ it, re-running the flagged statements oldest-first always converges on the correct figures — so out-of-order work is allowed and staleness is the signal, rather than the operation being refused. A period that has not closed yet cannot be reconciled at all.

Both directions create **one signed, card-linked adjustment expense** — positive for a fee or tax, negative for a credit. That signedness is not cosmetic: a bucket balance is `Σ expenses − Σ settlements`, so an expense is the only row type that can move it, and a credit recorded any other way would leave the card overstated. Two dedicated category values keep adjustments out of regular spending breakdowns: `expense_category.card_fees_and_taxes` and `expense_category.card_credits_and_refunds`. Because a category can therefore total below zero, the expense breakdown keeps the negative in its total (net spending is the honest figure) but computes percentages against the positive categories only, and the distribution chart omits it — a pie slice cannot represent a negative.

**Default funding account.** A card can optionally name the account it is normally paid from (Argentine _débito automático_). It only **pre-fills** the "Paid from" field when you record a payment — Renly never creates a settlement from it, because a real auto-debit can fail and inventing a payment that did not happen would leave you deleting a phantom one. The account can be in **any** currency: a settlement can pay a bucket from a differently-denominated account and record what actually left it, so paying a dollar card from your peso account is exactly the case this default exists for. (A recurring plan's default still has to match its own currency — a plan's charge has a single amount and no second figure to record.) Deleting the account clears the default rather than blocking the delete: a default is a convenience, not a record of money that moved.

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

The two accounts must be different (a transfer to the same account moves nothing), both amounts must be positive, and the date must fall on or after both accounts' opening dates — otherwise one leg would count and the other would not, which is the one thing a transfer must never do. For the same reason an account's `opening_date` is locked once anything links to it, exactly like its currency. Deleting an account removes the transfers that reference it: leaving half a transfer behind would silently skew the surviving account's balance.

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

**Default funding account.** A plan can optionally name the account it is paid from, and the scheduler links every charge it emits to that account — so an auto-generated expense decrements the balance it really came out of instead of leaving the balance to drift. It applies only when the payment method is **not** a credit card: a card-paid plan raises the card's balance and draws cash later, at the card settlement, so its cash leg belongs to the card's own default instead. The two together cover both halves. The account must be in the plan's currency; already-emitted expenses are never rewritten when the default changes, and a default that has stopped qualifying makes the scheduler emit the charge unlinked rather than skip it.

`next_billing_date` is scheduler-owned but also advanced (and reversed) by manual entries linked to the subscription. The advance fires only when the entry's closest cycle equals the current cursor; multi-jump cases (entry matches a cycle ahead of the cursor — pre-pay or mis-click) save the link but leave the cursor untouched, with the scheduler's back-fill loop + the partial UNIQUE INDEX dedup handling catch-up naturally so intermediate cycles still get expense rows. Back-dated entries also never advance. **Reverse:** deleting or unlinking the most-recent linked expense (sort by `date DESC`, `id DESC`) walks `next_billing_date` back by one cycle; middle-of-chain deletions leave the cursor alone. Editing a linked expense's date recomputes the cursor the same way — the old date's advance is reversed and the new date's re-applied on the same subscription. Tolerance for the closest-cycle search scales with the cycle: `min(cycle_length_in_days // 2, 60)`.

The day-of-month is preserved across short-month clamps via an internal `anchor_day` field (1-31, auto-derived from `next_billing_date.day` and not exposed in the form). A subscription billed on the 31st walks Jan 31 → Feb 28 → Mar 31 → Apr 30 → May 31 without drifting to day-28. Weekly and biweekly cycles ignore `anchor_day` since they advance by literal days.

### Installments

An installment plan represents a multi-cuota purchase (e.g. "TV Samsung 12x"). Each plan has a name, total amount, per-cuota amount, currency, total cuota count, the index of the next cuota to issue, an active flag, and a start date. Like subscriptions, it optionally links to a payment method and credit card, and to a default funding account the scheduler pays each cuota from. Unlike the plan's contractual fields, that account stays editable once cuotas have been charged — it only affects the cuotas still to come.

A daily scheduled job auto-generates one expense entry per cuota at its real cuota date (`start_date + (n-1) months`), increments `current_installment`, and flips `is_active` to `false` when the last cuota is issued. Plans registered with a past `start_date` back-fill all due cuotas in a single tick.

`current_installment` is scheduler-owned but also advanced (and reversed) by manual entries linked to the plan. The advance fires only when the matched cuota index equals the current cursor; multi-jump cases (entry matches a cuota ahead of the cursor — pre-pay or mis-click) save the link but leave the cursor untouched. The scheduler's back-fill loop then emits intermediate cuotas on their own dates and dedups the matched one at the partial UNIQUE INDEX, so every cuota gets an expense row naturally (no silent skips). Back-dated entries never advance. **Reverse:** deleting or unlinking the most-recent linked expense walks `current_installment` back by one cuota and re-activates the plan when the reverse moves the cursor back inside the cuota grid (a previous advance to `current = count + 1` flipped `is_active = false`). Editing a linked expense's date recomputes the cursor the same way — the old date's advance is reversed and the new date's re-applied on the same plan.

Once any cuota has been charged (`current_installment > 1`), the contractual fields on the plan -- `total_amount`, `installment_amount`, `installments_count`, `currency`, `start_date`, `payment_method`, `credit_card_id` -- are locked. Always editable: name, current_installment (manual correction), is_active (archive). Attempting to change a locked field returns a 400 with code `installment_locked_field`.

### Payment Obligations

A payment obligation records a recurring or one-off bill (electricity, ABL, internet, etc.). Each obligation has a name, amount, currency, anchor due date (`next_due_date` — the date of the next occurrence; recurring obligations project forward from this), optional recurrence (`monthly`, `bimonthly`, `quarterly`, `annual`, or none for one-off), a free-form `category` label (e.g. "ABL", "Cable"), a structured `expense_category` enum (reuses the expense category enum so dashboards can slice cleanly and Mark Paid pre-fills the linked expense's category), optional payment method/credit card, an optional default funding account, an active flag, and notes. Obligations are never auto-emitted, so their default funding account is honoured by **Mark Paid**: it pre-fills "Paid from" on the expense that flow creates, overridable like every other pre-filled field.

Obligations are not auto-generated as expenses — they exist as upcoming commitments that surface in the Payments Calendar (Phase 3, Step 4) so you can see what's due ahead. When you actually pay one, you click "Mark paid" on the obligations table OR pick the obligation from the expense form's "Linked to obligation" dropdown: saving creates a linked expense (with `payment_obligation_id` set) AND auto-advances the obligation. For recurring obligations the advance moves `next_due_date` forward by one recurrence cycle (anchor-day preserved across short-month clamps via `add_months_anchored`); for one-off obligations the advance flips `is_active = false`. Each linked expense advances ONE cycle, so paying two cycles upfront simply creates two expenses. **Reverse:** deleting or unlinking the most-recent linked expense (sort by `date DESC`, `id DESC`) walks `next_due_date` back by one recurrence cycle (recurring) or re-activates the row (one-off, date unchanged). Middle-of-chain deletions leave the cursor alone.

On the Payments Calendar, paid cycles show with a "Paid" badge instead of the default type-specific badge. This applies symmetrically across all three commitment types: a paid obligation cycle (period contains a linked expense via `payment_obligation_id`), a paid subscription cycle (an expense tagged `subscription_id` bound to that cycle), or a paid installment cuota (an expense tagged `installment_id` bound to that cuota). A linked expense is bound to the cycle its date is closest to, so a payment logged a few days off the exact cycle date still marks that cycle Paid. The calendar walks BOTH forward and backward from each commitment's "next" anchor so the user sees both unpaid future events AND past paid events inside the viewed month. Clicking a Paid badge opens the linked expense's edit dialog inline on the calendar (no navigation).

### API Keys

API keys allow external tools (like iOS Shortcuts) to authenticate without a full login flow. Each key has a name, is tied to a user, and can be revoked. The raw key is shown only once at creation.

### Feedback

A **feedback** row is one message someone sent from the in-app form: a category (bug, idea, question or other) and up to 2,000 characters of free text. The submitter's email is attached server-side from their session rather than typed, so a message can always be replied to and can never claim to be from someone else.

You own what you submit; **only an administrator can read the whole list**, which is the one place in Renly where an admin sees more than a member — and it exists because feedback is addressed to whoever runs the instance. Every admin is emailed when a message arrives, best-effort: a mail outage never loses the submission.

### Groups, Group Members and Group Invites

A **group** is a set of people who share money — a household, a couple, a trip, a flat share. It is the one entity in Renly that more than one account can reach; every other table belongs to exactly one person. It holds the people and nothing about what they share, which keeps it reusable for anything a household needs to do together.

A **group member** is a seat in a group. A seat is either linked to a Renly account or a **name-only placeholder** for someone who has no account and may never want one — a roommate who will never use the app still needs a real place in the group for their share of things to attach to. Accepting an invite fills the account in on the seat that already exists, so nothing has to be migrated or recomputed and their history simply becomes visible to them.

Removing someone **deactivates** their seat rather than deleting it: the group's history stays readable, the rows that reference them keep a real counterparty, and an admin can bring them back. Deleting an account reverts their seat to a placeholder rather than taking the group with it — the group belongs to its members, not to whoever created it.

A group member's `role` is `admin` or `member`, and it is about **administration only**: an admin manages members, settings and invites and gains no additional visibility whatsoever. No role in Renly can see more than a member. A group always keeps at least one active admin, since no other role could promote a replacement.

A **group invite** is a pending invitation to claim one seat. It uses the same mechanism as the platform signup invite — a high-entropy token whose SHA-256 hash is all that is stored, single-use, expiring after 7 days, revocable, and rotated on every resend — but it is a separate thing: it links an _existing_ account to a seat and never grants signup access. Sending it by email is optional; without an address it is simply a shareable link.

### Pots, Pot Permissions and the Ownership Ledger

A **pot** is the container co-ownership attaches to. Investments and cash accounts can point at one instead of at a person, and a single ownership ledger divides the whole of it. Ownership lives on the pot and never on the individual holding, which is what makes an internal rebalance — sell one thing, buy another — leave everyone's share completely untouched.

Every group gets a pot automatically and it needs no name; only a second pot in the same group ever needs one. A pot has a **base currency**, and all ownership maths runs in it: changing your display currency re-converts what you see and never moves ownership.

A pot also declares **how often it is expected to be re-valued** — weekly, monthly, or no set rhythm. It is an agreement between the people who share it, not a schedule: nothing gets valued automatically because a pot asked for it. Weekly is genuinely useful for money somebody else holds and reports on often; monthly suits one you control, and is the default because monthly is the rhythm the app itself keeps. Two things follow from the setting and nothing else does — when the pot reads as out of date, and how far apart the points of its value chart sit.

**Out of date is measured against the stalest thing in the pot**, because a total is only as current as its oldest term: one holding nobody has touched since March leaves the whole figure only trustworthy up to March, however fresh the rest are. So the pot says what date its figures are **updated through**, and each holding says when it was last valued — which is what points at the one that is holding the rest back. Note the total itself is still today's best estimate, not what the pot was worth on that date; the date says how stale its oldest input is, not which day the number belongs to. A pot holding only cash accounts is never out of date, since a balance is worked out at the moment you ask rather than recorded on a day. Neither is one with no agreed rhythm, or one holding nothing at all — an overdue valuation of nothing is a demand nobody can meet. The one case that reads as a problem straight away is a pot holding something **nobody has ever valued**: it has no value to divide, so nothing can be contributed to it or taken out of it until somebody records one.

A **pot permission** is one member's access to one pot, and there are two separate questions. Whether you may **see** it defaults to the pot's own setting — every member of the group, or only those explicitly granted access — with a per-member row overriding it either way. Whether you may **record movements** has no such default: it is granted per member and nowhere else, so a pot can name a single custodian who maintains the numbers while everyone else watches. Membership is not ownership: a member who owns **0%** still sees the whole pot, which is exactly what an adult child in a household needs.

The **ownership ledger** is a list of dated events, and every balance is derived by replaying them — nothing is stored as a running total. Each owner holds **units** of the pot; the unit price is the pot's value divided by the units outstanding. That single idea is what makes the numbers behave correctly:

- **Growth is pro-rata with no event at all.** If the pot rises from 100 to 110, a 90% owner simply goes from 90 to 99. Nobody records anything.
- **Money in or out issues or redeems units at that date's price.** Someone adding 5 to a pot worth 110 buys `5 ÷ 1.10 = 4.5455` units. Everyone's _percentage_ moves; nobody's _value_ does. Percentages alone cannot express that, which is the whole reason for units.

Four kinds of event: an **opening** sets the baseline (a value and each owner's percentage on a date — nothing before it is in scope, exactly like an account's opening balance); a **contribution** and a **withdrawal** move real money across the boundary, debiting one account and crediting another so both balances stay right; and a **re-agreement** transfers units between two people with no money at all, which is what a gift or a buy-out is. Conflating the last two would misstate the history: one is an investment, the other is a settlement between people.

Because the opening is one act recorded as one row per owner, **deleting it removes all of those rows together**. Half a division would leave the remaining owners holding a share nobody agreed to. Later movements are kept, and a new baseline can only be recorded once nothing else is on the ledger — it is only ever the first entry, because it issues units at a nominal 1.00 and movements after it are priced at whatever the pot was worth on their own dates.

You always enter percentages and always read percentages and amounts back. A raw unit count appears nowhere. Percentages are shown to two decimals and always add to exactly 100, and each member's share always adds to exactly the pot's value — the rounding remainder goes to the largest holder rather than being left to make the parts visibly disagree.

There is one input that is neither a percentage nor an amount: **the whole of somebody's share**, which is how a person leaves a pot and how one member buys another out. It has to be its own input rather than a figure you work out, because neither of the others can express it. Money divided by the unit price lands on the exact balance about one time in twenty; a share stated as a percentage of the pot, rounded to the two decimals you are shown, almost never does. Both of the near-misses are bad in their own way — one is refused for asking to take out precisely what you own, and the other leaves a fraction of a unit behind, which is enough to keep someone listed as an owner of 0.00% forever. Saying "all of it" is exact by construction.

A pot's **value over time** is the same figure asked at a series of past dates, at whatever rhythm the pot declared, with your own share drawn inside it. Two things about it are deliberate and worth expecting. Periods where the value cannot be worked out in full show as **gaps rather than zeros** — which, on a pot whose newest holding was added last month, is most of the earlier ones. And the chart never reaches back before the pot itself: a shared investment brings its whole history with it, so without that bound a pot created yesterday would appear to have been worth something for years. If the co-owners agreed their split began earlier than they recorded it, the chart starts there instead.

Two things Renly refuses rather than guesses. A movement on a date the pot has no known value for has no honest price to issue units at, so the flow asks for that value first — and "known" means the whole of it, because the value is a sum and a sum missing a term is not a smaller sum. A pot holding something nobody has valued yet reports no value at all rather than the total of the rest. And a private expense cannot be paid from a shared account: the money really leaves, so every co-owner's share would silently fall — one person spending and everyone paying, with nothing recording it. Record it as a shared expense instead and the same purchase is captured honestly, with what the other owners are owed for it written down where they can settle it.

### Shared Expenses, Shared Income, Splits and Settlements

A pot divides what a household **holds**. These divide what it **spends and earns**, and they are deliberately separate tables from your own entries: a row with one funding source and an N-way split cannot be one flat row, and your personal entries keep their simple owner-only privacy while everything here is reachable by every member of the group.

**A shared expense records two figures per member,** and the whole feature balances on the pair: what they **consumed** — their share, which is their expense — and what they **fronted**, the money they actually put up. Both add up to the expense's total, so a member's standing is what they fronted minus what they used, and a group's standing always adds to exactly **zero in every currency**. Not by a rule anybody has to remember: by the shape of the row.

That pair is also why there is **no "who paid" column**. Money can come out of a shared account, in which case the people who own that pot fronted it in their own proportions and there is no single payer — something one column could not say. Those proportions are read from the ownership ledger **as it stood on the expense's date and written onto the split rows then and there**, because the ledger is replayed from its events: worked out fresh on every read, somebody back-dating an ownership change would silently rewrite a balance two people had already agreed.

An expense is divided **equally**, by **exact amounts**, by **shares** (two parts to one), or by **percentages**, and the parts always add up to the total exactly. The leftover cent is spread one at a time from the largest share down, so nobody ever carries more than a cent of it — a split is money somebody owes, and it accumulates across every expense a group ever records. Exact amounts must already add up and percentages must reach 100; neither is quietly rescaled, because turning a 90/5 split into 94.7/5.3 on the user's behalf is worse than refusing it.

Every case follows from the one pair of figures, with no special handling anywhere:

- **One person pays for the group.** Their fronted figure is the whole bill, everyone's consumed figure is their share, and the difference is what they are owed.
- **A shared account pays for the group.** The pot's owners front it between them; if their ownership matches the split, nobody ends up owing anything.
- **A shared account pays for one person.** That person consumed all of it while the others fronted their share, so what they owe each of the others is exactly the joint money spent on them. This is what happens instead of quietly letting one person spend everyone's money.
- **Somebody fronts a bill they are not in on.** They consumed nothing and fronted everything, which is a real position and a real receivable.

The **funding account falls by the whole amount**, because the money really left it — who owed whom afterwards is the split's business, not the account's. A card-funded shared expense raises that card's balance exactly as a personal charge does.

A **settlement** is one recorded payment from one member to another, and the only thing that clears a balance. It is a single row both people see, never two entries to reconcile. Balances are kept in **per-currency buckets that never net against each other**: you can be owed pesos while owing dollars, and each is its own line to settle, because merging them would invent an exchange rate nobody agreed to. When Renly suggests how to square up it pays the largest creditor from the largest debtor and repeats, so A pays C directly rather than A paying B who pays C.

A settlement carries up to three amounts, each answering a different question: what balance it cleared and by how much, what actually left the payer's account, and what arrived in the payee's. The last two are only recorded when that side crossed currencies — when they match, what left the account **is** what cleared the balance. There is no stored exchange rate; the pair of figures is the record of it.

**Each side records their own half.** The two accounts belong to two different people, and neither can see the other's at all — so the payer says where the money left from, the payee says where it arrived, and either can leave theirs blank. Marking a payment as made without naming any account is the ordinary case, and a name-only member has no account to name at all.

A recorded payment **counts against the balance straight away** — the money genuinely moved — and confirming it is the other person acknowledging they received it. What confirmation changes is who can undo it: until then either party can remove it, which is what reversing a payment is; afterwards nobody can, until the person who received it takes their confirmation back. A couple can turn confirmation off entirely.

The other way a balance ends is a **write-off**: giving up on a debt. It clears the same bucket a payment would, moves no money, and only the person who is **owed** can record it — the other way round would be one person deciding on somebody else's behalf. Settling or writing off is required before a member with an open balance leaves the group or deletes their account, because the moment their seat goes the person on the other side loses the record of what they were owed.

**Shared income is the same shape with the two sides swapped.** A piece of income the group shares records what each member is **entitled to** — their share, which is their income — and what actually **reached them**. Both add up to the total, so the same balances still come to zero: somebody who collects the rent and passes on nothing yet owes the others their shares, and somebody entitled to a share who has received nothing is owed it. There is no "who received it" column, for exactly the reason there is no "who paid" one: money can arrive in a shared account, where the pot's owners receive it in their own proportions.

Each piece of income says **where it went**. It either **stayed joint** — landing in a shared account, so the whole pot is worth more and everyone's share rises with it, which needs no ownership event at all because nobody's percentage changes — or it **went to one person**, who holds the rest until they pass it on. Money arriving from outside the household crosses no ownership boundary on the way in; only money already inside a pot can leave one.

It can also say **where it came from**: a co-owned asset the group holds. That divides the income the way the asset is owned, so rent from a property owned 60/40 is 60/40 income unless somebody changes it — the common case needs no decision at all. What gets stored is always the division actually agreed, so later changes to who owns the asset never restate income already recorded. Both flows share one set of balances, so one payment squares up whatever they add up to.

Finally, **your share of a shared expense appears in your ordinary expenses list, and your share of shared income in your income list** — read straight from the group's tables rather than copied into your own. One source of truth: editing the group's row has nothing to chase, and nothing can drift. Each row says which it is, carries the group it belongs to and the whole amount your share is part of, and is edited where it was created rather than from your own list.

### Settings

Each user has personal preferences that control how the app behaves:

- Which currencies to display (primary and secondary)
- Which USD/ARS rate to use for conversions (oficial, MEP, or blue)
- Dashboard period presets and display options
- Which currencies to show in the iOS Shortcut currency picker (defaults to primary + secondary)
- The user's timezone (IANA name like `America/Argentina/Buenos_Aires`) plus a mode flag (`auto` or `manual`). In auto mode the browser-detected timezone is silently kept in sync on every page load; in manual mode the stored value sticks until the user changes it. The auto-expense scheduler uses this to fire recurring charges on the user's local calendar day instead of the server's UTC day.
- The user's language (`en` or `es`) plus a mode flag (`auto` or `manual`) — mirrors the timezone pattern.
- Account caps and warning thresholds: `max_collections`, `collection_warning_pct` (when investment collections approach the cap, the UI warns).
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
 |                  |-- belongs to many --> Collections
 |                                         (user-defined labels like "Retirement")
 |
 |-- has many --> Collections
 |                (each collection can contain many investments)
 |
 |-- has many --> API Keys
 |                (for iOS Shortcut / external tool access)
 |
 |-- has --> Settings
              (currency preferences, display options)
```

**Shared data** (the one branch that is not owned by a single user):

```
Group
 |    (a household / couple / trip / flat — the people, not the money)
 |
 |-- has many --> Group Members
 |                (one seat per person; linked to an account, or a name-only placeholder)
 |                  |
 |                  |-- optionally linked to --> User
 |                                              (filled in when they accept an invite;
 |                                               cleared, not cascaded, if that account is deleted)
 |
 |-- has many --> Group Invites
 |                (one live invite per seat; single-use, expiring, revocable.
 |                 Links an EXISTING account to a seat — never creates one)
 |
 |-- has one  --> Group Money Settings
 |                (the split it proposes by default, and whether a payment
 |                 needs the other side to confirm it)
 |
 |-- has many --> Pots
 |                (what the group HOLDS together)
 |                  |
 |                  |-- has many --> Pot Permissions .... who may see it, who may write to it
 |                  |-- has many --> Ownership Events ... the dated ledger units are replayed from
 |                  \-- holds many -> Investments / Accounts
 |                                    (pointing at the pot instead of at a person)
 |
 |-- has many --> Shared Expenses
 |                (what the group SPENDS together)
 |                  |
 |                  \-- has many --> Shared Expense Splits
 |                                   (per member: what they used, and what they fronted.
 |                                    Both columns add to the expense's total)
 |
 |-- has many --> Shared Income
 |                (what the group EARNS together; says where it went, and
 |                 optionally which co-owned asset it came from)
 |                  |
 |                  \-- has many --> Shared Income Splits
 |                                   (per member: what they are entitled to, and what
 |                                    reached them. Both columns add to the row's total)
 |
 \-- has many --> Group Settlements
                  (payments and write-offs, the only things that clear a balance —
                   whatever the two flows add up to, in one bucket per currency)
```

A group is reachable by every account holding an active seat in it, which is why it hangs off `Group` rather than off `User`. `created_by` records who made it and confers nothing.

Nothing here is owned by one person, and that is the point: a balance is a fact about two people, so it cannot live in either one's data. Group members' seats survive the accounts behind them — deleting an account reverts its seat to a name-only placeholder and leaves everything attached to it intact.

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

**Ownership is a property of the record, never of the login.** Everything answers to exactly one scope: it is yours alone, or it belongs to a group. Nothing blends the two into one unlabelled number. Groups are the first step of that model: they establish _who the people are_, and nothing of yours becomes visible to them until you deliberately share it.

**Administration never grants visibility.** A group admin manages members, settings and permissions — and that gives them zero additional access to any member's data. No role in Renly can see everything. The database enforces this rather than trusting the application to: the membership policy that decides what a group's rows are visible to never looks at anyone's role.

**Credit cards are liabilities, not expenses.** When you buy something with a credit card, the expense is recorded immediately and the card balance increases as a liability. When you pay the statement, you record a settlement that reduces both your bank and the liability. This avoids double-counting and keeps all metrics accurate. See [Credit Card Liability Model](../technical/credit-card-liability-model.md) for the full accounting details.
