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
2. Your bank balance decreases by the same amount.
3. Net effect on patrimony: zero (asset decreased, liability decreased equally).
4. No new expense is created -- the expense was already recorded when you bought the item.

This is why settlements are stored in their own table (`card_settlements`), not as expenses.

## Balance calculation

```
card_balance = sum(expenses where credit_card_id = card.id) - sum(settlements for card)
```

The balance is **computed at query time**, not stored. This means:

- Deleting an expense linked to a card automatically reduces the balance.
- Deleting a settlement automatically increases the balance.
- No balance column to keep in sync -- it's always correct.

The backend computes this in two batch queries (`expense_repository.sum_by_credit_card_ids()` + `card_settlement_repository.sum_by_card_ids()`) to avoid N+1 when listing multiple cards.

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

## Where this is implemented

- **Backend:** `credit_card_service.get_card_balance()` and `get_card_balances()` compute balance from two batch queries. `_to_response()` in the credit cards router builds the response with the computed balance.
- **Frontend:** The credit cards table shows the computed balance per card. Expandable rows show settlement history with add/delete.
- **DB schema:** `expense_entries.credit_card_id` FK links expenses to cards. `card_settlements.credit_card_id` FK links settlements to cards. Balance computed at query time from these two tables.
