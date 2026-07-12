# Understanding Your Metrics

This page explains every number you see on the Renly dashboard. Each metric is designed to answer a specific question about your investments.

---

## Current value

**What it answers:** "How much is my portfolio worth right now?"

The sum of the latest snapshot value for each of your investments, converted to your chosen display currency. If you have 3 investments worth $5,000, $3,000, and $2,000, your current value is $10,000.

## Invested capital

**What it answers:** "How much money have I actually put in?"

The total of all your deposits and purchases, minus all your withdrawals and sales. This is the net amount of money you've moved into your investments.

Example: You deposited $8,000 over the past year and withdrew $1,000. Your invested capital is $7,000.

## Absolute gain or loss

**What it answers:** "Am I up or down in dollar terms?"

Simply: current value minus invested capital.

- You put in $7,000 (invested capital)
- You now have $10,000 (current value)
- You've gained $3,000

If you had $6,500 instead, you'd have a loss of -$500.

## Period return

**What it answers:** "How much did my investment grow this month, ignoring any money I added or removed?"

This is the return between two consecutive snapshots, adjusted for cash flows. Without this adjustment, depositing $1,000 in the middle of the month would look like a $1,000 "gain," which is misleading.

**How it works:**

Take the current value, subtract any net deposits/withdrawals during the period, and compare to the previous value.

`return = (current_value - net_cash_flows) / previous_value - 1`

**Example:** Your investment was worth $10,000 last month. This month it's worth $11,500, and you deposited $1,000 during the month. The period return is:

`($11,500 - $1,000) / $10,000 - 1 = $10,500 / $10,000 - 1 = +5.0%`

The investment grew 5%, and the remaining $1,000 increase came from the money you added.

## Time-Weighted Return (TWR)

**What it answers:** "How did the investment itself perform, regardless of when I added or removed money?"

Imagine you had invested exactly $1 at the very beginning and never touched it. TWR tells you what your return would be. It measures the investment's performance, not your personal result.

**How it works:**

TWR chains together all the period returns by multiplying them:

`TWR = (1 + r1) x (1 + r2) x (1 + r3) x ... - 1`

**Example:**

- Month 1: +5%
- Month 2: -2%
- Month 3: +4%

`TWR = 1.05 x 0.98 x 1.04 - 1 = 1.0702 - 1 = +7.02%`

TWR does **not** depend on when you deposited or withdrew money. Two people who invested in the same stock over the same period will see the same TWR, even if one person added money at different times.

## Money-Weighted Return (IRR)

**What it answers:** "At what rate did my actual money grow, considering when I added and removed it?"

This is also called XIRR (extended internal rate of return). Unlike TWR, IRR **does** depend on timing. If you deposited a large sum right before a good month, your IRR will be higher than someone who deposited the same total but spread it out evenly.

IRR finds the annual interest rate that would make all your cash flows (deposits, withdrawals, and final value) balance out to zero. Think of it as: "what savings account interest rate would have given me the same result, given the exact dates I moved money in and out?"

**Key difference from TWR:** If you deposited $5,000 right before a +10% month, your IRR benefits from the good timing. TWR doesn't care -- it treats the investment the same regardless.

IRR is annualized, meaning it's expressed as a yearly rate even if your investment has only been open for a few months.

Because IRR is annualized, Renly only shows it once your cashflow history spans at least 30
days. Annualizing just a few days of data would produce absurd numbers (a good week extrapolated
to a year looks like millions of percent), so shorter histories show "—" instead.

## When to use TWR vs. IRR

| Question                                 | Use                                                       |
| ---------------------------------------- | --------------------------------------------------------- |
| "How did this stock/fund/bond perform?"  | TWR                                                       |
| "How did **my money** actually do?"      | IRR                                                       |
| "Should I compare two investments?"      | TWR (fair comparison, ignoring deposit timing)            |
| "Did my deposit timing help or hurt me?" | Compare TWR and IRR -- if IRR > TWR, your timing was good |

## Metrics with a date filter

When you pick a period on the investor dashboard (a preset like "This year" or a custom range),
the headline cards switch from all-time to period metrics:

- **Value at period end** — what the portfolio was worth at the end of the selected period.
- **Invested** — the net money you moved in during the period. A new investment's starting
  value counts as money in (it entered the portfolio during the period).
- **Period gain** — end value − start value − net money moved in during the period. This
  isolates what the period itself earned you, regardless of how much was already there.
- **TWR and IRR** are measured inside the period only.

Without a date filter, the cards show all-time values: current value, total net invested, and
current value minus invested.

## "vs last month"

The small change indicator under the gain card compares the latest portfolio value against the
portfolio value at the end of the previous month, both taken from the same monthly series as the
evolution chart (in your display currency). If all your data is within a single month, there is
no previous month to compare against and the indicator is hidden.

## Distribution and allocation

**What it answers:** "What percentage of my portfolio is in each category or group?"

If your portfolio is worth $10,000 and you have $4,000 in stocks, $3,000 in CEDEARs, and $3,000 in crypto, your allocation is:

- Stocks: 40%
- CEDEARs: 30%
- Crypto: 30%

You can view allocation by **category** (stocks, CEDEARs, bonds, etc.) or by **group** (Retirement, Trading, Kids, etc.).

## Dashboard composition and finance comparisons

**Net worth composition (assets vs. liabilities).** The composition donut on the main dashboard sizes each slice by its value, and the percentages are shares of the values actually shown — your asset categories plus a "liabilities" slice when you carry a card balance. When you have a net card credit (the card owes you), there is no liabilities slice and your asset percentages add up to exactly 100%.

**Uncategorized entries.** The expense and income breakdown donuts on the finance dashboard now include an "Uncategorized" slice for entries you left without a category, so the donut always adds up to the same total as the summary card above it.

**"vs previous period."** The change indicators on the finance dashboard compare your selected period against the period of the same length immediately before it — ending the day before your window starts, with no shared day. A June 1–30 view compares against May 2–31.

## Liquidity

**What it answers:** "What share of my income is already committed to fixed monthly costs?"

Renly's liquidity card shows the ratio of your **fixed monthly commitments** to your **monthly income**:

`liquidity = fixed_monthly_commitments / monthly_income`

A higher number means more of your income is already spoken for by recurring costs. Above your configured threshold, the card turns amber; well above it, the card turns red.

**What counts as a fixed monthly commitment:**

- Every active **subscription** (Netflix, Spotify, gym) — amortised to its monthly equivalent (an annual plan counts as `amount / 12` per month, a biweekly plan as `amount × 26 / 12`).
- Every active **installment plan** — contributes one monthly cuota until the plan finishes.
- Every recurring **payment obligation** (electricity, ABL, internet) — amortised by recurrence (a bimonthly bill counts as `amount / 2` per month, quarterly as `/ 3`, annual as `/ 12`). One-off obligations don't count.
- Credit cards **with `monthly_payment` set** — revolving-debt users state the typical amount they pay each month; that value counts as a fixed commitment. Cards without `monthly_payment` (pay-in-full users) are excluded. Card-funded subscriptions and installments are always counted via their own rows, regardless of `monthly_payment`.

**What counts as monthly income:**

The total income you logged over the last **90 days**, normalised to 30 days. For new users who haven't been logging income for 90 days yet, Renly uses your actual elapsed history (so 17 days of data → multiplied by 30/17 to reach a monthly figure). With fewer than 7 days of history, the card shows "—" with a hint to log income.

**The four states:**

| State   | When                                             | Colour    |
| ------- | ------------------------------------------------ | --------- |
| Healthy | Ratio is below your threshold                    | Green     |
| Caution | Ratio is at or just above your threshold (≤10pp) | Amber     |
| At risk | Ratio is more than 10pp above your threshold     | Red       |
| Unknown | No income logged in the window, or ≥0 history    | Muted "—" |

**Configuring the threshold:** Set `liquidity_threshold_pct` (1–99) in [Settings → Alerts & limits](data-model.md). The default is 40% — a common rule-of-thumb for personal finance. Adjust higher if your fixed costs naturally run higher (Argentine residents with installments + utilities often land in the 50–60% band), or lower if you want a tighter safety margin.

**Cross-currency:** the ratio is computed in your display currency. Commitments and income are converted to that currency at today's rate before the division. When the currency switcher is on "Original," the card falls back to your primary currency (the same fallback the rest of the dashboard already uses).

---

## Note on currency conversion

All currency conversions use **today's exchange rate**, not the historical rate from the snapshot's date. This means a snapshot from January 2025 displayed in ARS uses today's USD/ARS rate, not January 2025's rate.

This is a deliberate design choice: it answers "what is this worth to me today?" rather than "what was it worth back then in local currency?" It keeps all values comparable across time when viewed in a single currency.

## Skipped investments

If Renly can't convert an investment's currency to your display currency (for example, you're viewing in BRL but the exchange rate service is temporarily unavailable), that investment is **excluded** from portfolio totals rather than shown with an incorrect value.

When this happens, the dashboard flags which investments were skipped so you know the totals are incomplete. This prevents silent errors in your numbers.
