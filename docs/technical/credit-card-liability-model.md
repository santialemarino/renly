# Credit Card Liability Model

How Renly handles credit cards as liabilities, not expenses.

## Core principle

```
patrimony = assets (bank + investments + cash) - liabilities (credit card balances)
```

Credit cards are **liability accounts**. The card balance represents money you owe, not money you've spent. This distinction is what makes expense tracking and patrimony calculations accurate.

## How it works

| Event                  | Bank balance | Card balance | Patrimony | Expense recorded? |
| ---------------------- | ------------ | ------------ | --------- | ----------------- |
| Buy with card ($5,000) | unchanged    | +$5,000      | -$5,000   | Yes (categorized) |
| Pay card statement     | -$5,000      | -$5,000      | unchanged | No (settlement)   |

### Buying with a credit card

When you record an expense with `payment_method = credit_card` and link it to a card:

1. The expense is recorded immediately (date, amount, category -- just like any other expense).
2. The card's balance increases by the expense amount.
3. Patrimony decreases by the expense amount (because liabilities increased).
4. No money leaves the bank account yet.

### Paying the card statement (settlement)

When you pay your credit card bill, you record a **settlement**:

1. The settlement reduces the card's balance.
2. If you link a funding account, its balance decreases too.
3. Net effect on patrimony: zero **within one currency** (asset decreased, liability decreased equally).
4. No new expense is created -- the expense was already recorded when you bought the item.

This is why settlements are stored in their own table (`card_settlements`), not as expenses.

**Across currencies it is deliberately not zero.** Paying a USD bucket with pesos clears the bill at the bank's blended "dólar tarjeta" rate, so the settlement records two amounts: `amount` (what cleared the card, in the bucket's currency) and `account_amount` (what actually left the account, in the account's currency). The gap between them is the real FX + tax cost and is never itemised, because the ~30% Ganancias perception is already inside the rate with no separable figure to record. What it does to the reported net-worth _delta_ depends on the rate the debt was being marked at: clearing it reduces net worth when the debt was marked below the card rate (`oficial`) and can read as a gain when marked at or above it (`mep`, the default, or `blue`). That is consistent mark-to-market, not an error -- see `currency-handling.md` §12. See `currency-handling.md` §12 for which sums read which leg.

## Balance calculation

```
card_balance = sum(expenses where credit_card_id = card.id) - sum(settlements for card)
```

The balance is **computed at query time**, not stored. This means:

- Deleting an expense linked to a card automatically reduces the balance.
- Deleting a settlement automatically increases the balance.
- No balance column to keep in sync -- it's always correct.

The backend computes this in two batch queries (`expense_repository.sum_by_credit_card_ids_grouped()` + `card_settlement_repository.sum_by_card_ids_grouped()`) to avoid N+1 when listing multiple cards. Both are **card-side** sums, so they read the settlement's `amount` and never its `account_amount`: the bank cleared the bill in the bucket's own currency, whatever it debited you.

## Settlement matching

**Decision:** Total balance reduction. Settlements are not matched to specific expenses.

A settlement of $30,000 just reduces the total balance by $30,000 -- it doesn't need to reference which specific purchases it covers. This supports:

- **Partial payments** -- pay any amount, the balance adjusts.
- **Over-payments** -- if you pay more than the balance, the balance goes negative (credit in your favor).
- **Simple reconciliation** -- just compare your bank statement to the settlement amounts.

## Card fields

| Field         | Description                                                    |
| ------------- | -------------------------------------------------------------- |
| `name`        | User-chosen label (e.g., "Visa BBVA", "Amex Platinum").        |
| `closing_day` | Day of month (1-31) when the billing period ends.              |
| `due_day`     | Day of month (1-31) when payment is due.                       |
| `currency`    | Card's denomination (ISO 4217). Settlements use this currency. |
| `is_active`   | Whether the card is in use.                                    |

`closing_day` and `due_day` are informational metadata in Phase 2 -- they become functional in Phase 3 (Payments Calendar) where they drive due date reminders and billing period calculations.

## Settlement fields

| Field      | Description                                                       |
| ---------- | ----------------------------------------------------------------- |
| `date`     | When the payment was made.                                        |
| `amount`   | How much was paid.                                                |
| `currency` | Always matches the card's currency (auto-set, not user-selected). |
| `notes`    | Optional note (e.g., "March statement", "Partial payment").       |

## What settlements are NOT

Settlements do **not** appear in:

- Expense totals or category breakdowns.
- Income-vs-expense charts.
- Any expense metric or aggregation.

Settlements **only** surface in:

- The credit card detail view (settlement history + balance).
- Payments Calendar (Phase 3) -- as due dates with rolled-up totals.
- Cash flow analysis (if added) -- as bank outflows clearly labelled as card payments.

## Archive and delete

Cards can be **archived** (set `is_active = false`) to hide them from the expense form's card selector while preserving all linked expenses, settlements, and balance history. Archived cards appear dimmed in the credit cards table and can be unarchived at any time.

**Archive is a UI filter, not an accounting event.** An archived card's outstanding balance stays a liability in every aggregation — net worth, the finance overview `credit_card_balance`, dashboard composition, the net-worth evolution series, and Payments Calendar `card_due` events all include archived cards. Archiving only hides the card from pickers and list pages. (The single exception is the liquidity indicator, which measures forward-looking monthly commitments from _active_ entities — an archived card's `monthly_payment` is no longer a commitment.)

Cards can only be **deleted** when they have no linked expenses. Attempting to delete a card with expenses returns 409 Conflict (`HasLinkedExpensesError`). Settlements cascade on delete. The `has_expenses` field on the response tells the frontend whether the delete button should be available.

## Statement-period scoping (running-balance snapshots)

The card's running balance (what you owe today) is what the credit-cards table shows. For per-statement views — Payments Calendar `card_due` events, the Reconcile dialog — the app needs a different number: **what was the balance at this statement's closing date?**

```
statement_balance(card, currency, closing_date) =
    sum(expense_entries.amount where credit_card_id = card AND currency = currency AND date <= closing_date)
  − sum(card_settlements.amount where credit_card_id = card AND currency = currency AND date <= closing_date)
```

This is a running-balance **snapshot** at `closing_date` per bucket. Carryover from earlier unpaid statements is implicit (it's already in the running total). This matches how a real bank resumen prints "Saldo total" each month — every settlement up to the closing date counts; everything else is next month's problem.

Pure helper: `compute_bucket_balance_at(card_id, currency, as_of_date)` — used by both the Payments Calendar's `_card_due_items` and the reconciliation service.

**Paid-marking for `card_due` events.** The statement amount stays frozen at its closing-date snapshot, but the calendar flips a `card_due` event's `is_paid` to true when settlements dated inside `(closing_date, due_date]` for that card+currency sum to **at least** the snapshot. A partially-settled statement stays unpaid. A negative snapshot (net credit balance) is never a bill — it keeps `is_paid = false` and skips the settlements query entirely (`card_reconciliation_repository.sum_settlements_between`).

### Statement periods

A statement period is identified by its closing date. Period bounds are `(prev_closing_date, this_closing_date]` — the closing date is the LAST day of its statement; the next period starts the day after. Day-of-month overflow (`closing_day = 31` in February, etc.) is resolved by clamping to the last day of the target month.

- `resolve_day_in_month(day, year, month) -> date_type` — clamp helper.
- `compute_statement_period(closing_day, statement_closing_date) -> (period_start, period_end)` — walks back one calendar month and applies the clamp to find `period_start = previous_closing_date + 1 day`.

Both live in `app/utils/dates.py`.

## Reconciliation (Option F)

Even with correct currency conversion and accurate settlements, the bank's real statement balance rarely equals the app's computed running balance. Argentina's 30% Ganancias perception (RG 5617/2024), Visa / Mastercard FX fees, IVA on digital services, provincial sellos, refunds, and network rounding all sit outside the model. **Reconciliation captures the delta as a single adjustment so the bucket matches the bank to the cent.**

### Math

```
computed_balance  = compute_bucket_balance_at(card_id, currency, period_end)
difference        = statement_balance − computed_balance

if difference > 0:  create expense_entries row (category card_fees_and_taxes, source 'reconciliation')
if difference < 0:  create expense_entries row with a NEGATIVE amount
                    (category card_credits_and_refunds, source 'reconciliation', card-linked)
if difference == 0: no adjustment
```

The adjustment is dated on `period_end` (the closing date) and tagged via `reconciliation_id`. From that date forward it's part of the running balance — so subsequent statements see the adjustment as carryover and the bucket stays accurate without any further intervention.

### The adjustment row is read-only

`expense_service.update_expense` / `delete_expense` (and their income counterparts) call the shared
`ensure_not_reconciliation_owned(reconciliation_id, account_reconciliation_id)` guard
(`app/domain/reconciliation.py`) immediately after fetching the row, raising
`ReconciliationOwnedEntryError` (409 `reconciliation_owned_entry`) before any other read or write — so a
rejected request stages nothing, not even a `mark_stale_for_date`. The adjustment's amount IS the
reconciliation's recorded `difference`, and the reverse pointer `adjustment_expense_id` is
`ON DELETE SET NULL`, so deleting the entry directly would leave the reconciliation alive with a null
pointer and a stale `difference` while the bucket balance snapped back. The entry-side FK is
`ON DELETE CASCADE`, which is why deleting (or re-running) the **reconciliation** is the supported path.

The guard keys off the reconciliation FKs, never off `source` — the scheduler, importers and the iOS
shortcut all stamp `source`, and it survives a restore that nulls both links (so a restored adjustment is
a plain entry and stays mutable). `create_or_replace` is unaffected: it writes its adjustment through
`expense_repository.create` directly, and its replace step deletes the prior _reconciliation_, cascading
that row's adjustment rather than deleting the entry through the guarded service.

### Stale-detection on retroactive edits

`card_reconciliations.is_stale BOOLEAN NOT NULL DEFAULT FALSE`. A reconciliation's `computed_balance` is `compute_bucket_balance_at(period_end)`, which sums every charge and settlement dated `<= period_end` **from the beginning of the bucket's history**. The period bounds name _which_ statement; they do not scope the arithmetic. The flag therefore keys on `period_end >= <changed date>`, not on the date falling inside `[period_start, period_end]`:

- creating / editing / deleting an `expense_entries` or `card_settlements` row dated on or before `period_end` — **including one dated before the period began**;
- the scheduler back-filling a missed subscription or installment cycle into the bucket;
- reconciling or deleting an **earlier** statement, whose adjustment is itself a dated expense inside this balance.

Only changes that can actually move a balance flag it. Editing an expense's notes or category does not, and a reconciliation that matches to the cent writes no adjustment, so it leaves later statements alone.

The flag renders as an amber badge with an explanatory tooltip in the Reconciliations sub-section, and the reconcile dialog repeats it as a banner. Re-running reconciliation for the period replaces the row and clears the flag.

This guards against the "I forgot to log a January expense, recorded it in May, but reconciled January back in February" case — the reconciliation would silently go wrong otherwise. The `period_end >=` bound is what extends that guarantee to the harder version, where the forgotten expense predates a statement reconciled long afterwards.

### Re-reconcile (replace, never stack)

Uniqueness on `(card_id, currency, period_start, period_end)`. POST is create-or-replace: the prior row deletes, the cascade drops the prior adjustment (FK `ON DELETE CASCADE` from `expense_entries` / `income_entries` back to `card_reconciliations`), and a fresh pair is written atomically. The UI pre-fills the dialog with the prior `statement_balance` and renders a banner: _"Reconciled on {date} — saving replaces this entry."_ The Save button relabels to "Replace reconciliation."

### Statement visibility rule (what shows in the list)

The Reconciliations sub-section doesn't render every walk-back statement unconditionally — that would clutter a fresh card with 12 rows of `$0 · Not reconciled`. The rule:

> Show a statement when **any** of: (a) it has an existing reconciliation, (b) it is the latest closed statement, (c) its `period_end` is at or after the bucket's first activity (earliest expense or settlement date on this card+currency).

Consequences:

- **Fresh card with no activity**: one row, the latest closed statement, so the user can reconcile whenever the first statement actually arrives.
- **Active card**: every statement from first activity through the latest, capped at 12.
- **`$0` statements after first activity**: visible. They're real bank statements with $0 due — the user may want to confirm them (occasional maintenance fees, etc.).
- **Reconciled historical statements**: always shown, even if the period predates first activity (defensive — historical reconciliations are explicit records).

`first_activity_date` is computed via `card_reconciliation_repository.get_first_activity_date(card_id, currency)` — `min(min(expense.date), min(settlement.date))` for the bucket, or `None` when empty.

### Adjustments propagate (running-balance, like a real bank)

The adjustment expense is dated on `period_end` (the closing date) and enters the bucket's running balance from that date forward. **Example:** Mar 2026 reconciled to 40 with computed 0 → +40 expense dated Mar 30. If Apr already had 40 in expenses, Apr's computed balance becomes 80 (= 40 carryover + 40 new). This matches the bank's resumen (`previous balance $40 + new charges $40 = $80 due`) and is the intended behaviour — fees / taxes captured by reconciliation are real outstanding debt that carries forward until settled.

The Reconciliations sub-section's "App balance" column has a tooltip clarifying this: _"Running balance at the statement's closing date. Includes carryover from prior unpaid statements — same as your bank's resumen."_

### UI surface

Reconcile lives only inside the credit-cards table expandable row, as a sibling sub-section to Settlements. Each bucket shows a list of recent statement periods with `Reconciled` / `Not reconciled` / `Stale` badges; clicking a row opens the dialog. The "Last reconciled" marker is the first line of the Reconciliations sub-section per bucket. The Payments Calendar stays read-only (Step 4 contract).

## Where this is implemented

- **Backend:** `credit_card_service.get_card_balances()` returns one `CardBucketBalance(currency, balance)` per currency with activity on each card. `expense_repository.sum_by_credit_card_ids_grouped()` + `card_settlement_repository.sum_by_card_ids_grouped()` return per-currency totals; `compute_card_balances()` (pure function) subtracts settlements from expenses inside each bucket. No cross-currency conversion at this layer. The card's primary currency always appears as a bucket even with zero activity so newly-created cards still render. `_to_response()` in the credit cards router emits `balances: list[CardBucketBalanceResponse]`. Statement-period math: `compute_bucket_balance_at(card_id, currency, as_of_date)` (pure, in `card_reconciliation_service`). Reconciliation orchestration: `card_reconciliation_service.create_or_replace(...)` is atomic — drops prior + cascades, then inserts reconciliation + adjustment, then patches the adjustment back-pointer, then commits. Stale-detection hooks in `expense_service` + `credit_card_service` (settlements) call `card_reconciliation_service.mark_stale_for_date(card_id, currency, date)`. The adjustment row itself is protected by `ensure_not_reconciliation_owned` (`app/domain/reconciliation.py`), called at the top of the four expense/income update+delete service functions.
- **Frontend:** The credit cards table renders one balance line per currency bucket (primary first, others alphabetical). Single-currency cards show a single line — visually identical to the pre-Phase-3 behaviour. The settlement form shows a currency picker only when the card has multiple buckets; otherwise it locks to the primary. The expense form runs a soft confirmation when a credit-card expense uses a currency the card hasn't seen before (catches typos that would create phantom buckets). The expandable row now carries a Reconciliations sub-section beside Settlements: per-bucket list of recent statements with status badges, a "Last reconciled" header, and the reconcile form dialog (pre-fill + banner on replace).
- **DB schema:** `expense_entries.credit_card_id` + `expense_entries.currency`, `card_settlements.credit_card_id` + `card_settlements.currency`. Bucket identity is `(card_id, currency)` — derived at query time, not stored. `card_reconciliations` table with `UNIQUE (card_id, currency, period_start, period_end)`. `expense_entries.reconciliation_id` + `income_entries.reconciliation_id` (BIGINT, nullable, `REFERENCES card_reconciliations(id) ON DELETE CASCADE`; both are also surfaced read-only on `ExpenseResponse` / `IncomeResponse` so clients can tell an adjustment from an authored entry). Category enum values for the adjustments: `expense_category.card_fees_and_taxes` and `expense_category.card_credits_and_refunds` (both directions are expenses — only an expense can move a bucket). `income_category.card_credits_and_refunds` remains declared but is no longer written.
