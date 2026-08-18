# Renly — What It Is and Who It's For

## What is Renly

Renly is a personal web-based financial management app built for the Argentine retail investor. It brings three things that usually live apart -- your investments, your cash and bank balances, and your credit-card debt -- into a single net-worth picture, alongside day-to-day income and expense tracking.

If you've ever tried to hold all of that in a spreadsheet, Renly replaces that spreadsheet with something faster, smarter, and better-looking.

Renly does not connect to your bank, wallet, or broker, and never asks for those credentials. Almost every figure is there because you entered it, imported it, or logged it from the iOS Shortcut. Renly does fill in a few things itself: fetched prices and exchange rates, monthly snapshots of ticker-linked investments once one snapshot with a quantity exists, and the recurring charges of your subscriptions and installment plans (which also move the balance of the account you chose to pay them from). Rather than requiring you to record every movement perfectly, each kind of figure has a way to snap back to the truth: a **snapshot** for an investment, a **reconciliation** for a cash or bank account, a **statement** for a credit card. Those true up a balance, not the history behind it -- see the app's Help page for exactly what a forgotten movement does and does not affect.

## Who it's for

**Primary user:** A 25-to-45-year-old with investments across multiple Argentine brokers -- Cocos Capital, IOL, Balanz, Bull Market, Brubank, or a traditional bank -- who currently consolidates their portfolio in Excel or doesn't do it at all.

**Secondary user:** Anyone who wants to track personal finances (income, expenses, cash and bank balances, credit cards, savings goals) in one place.

## Core values

- **Your whole picture** -- Investments, cash and bank balances, and credit-card debt roll up into a single net-worth figure, instead of living in three places that never agree.
- **Real Argentine context** -- CEDEARs, ARS exchange rates (oficial, MEP, blue), BYMA prices, government bonds like AL30 and GD30. None of this exists in American financial apps.
- **Fast to keep current** -- You shouldn't spend more than a few minutes a month keeping Renly up to date. Smart defaults, CSV/Excel import, auto-pricing, and the iOS Shortcut make this possible.
- **Visual clarity** -- Better than Excel. Actionable metrics, clean charts, and a dashboard that tells you what matters at a glance.
- **Honesty** -- Time-weighted return (TWR) and internal rate of return (IRR) are implemented properly, not approximated, and the app is explicit about where each figure comes from. Renly reflects what you enter; snapshots and reconciliation are how it stays anchored to reality. It never claims a number is authoritative when it is derived from your own entries.
- **Extensibility** -- Each new feature builds on what's already there without breaking anything.
- **Your data stays yours** -- No bank credentials are ever requested or stored, and you can export a copy of your data at any time.

## Product phases

| Phase | Name                | Status  | What it adds                                                                                                                                           |
| ----- | ------------------- | ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1     | Investments         | Built   | Track investments, automatic pricing for stocks/CEDEARs/crypto/bonds, multi-currency support, monthly snapshots, dashboard with returns and allocation |
| 2     | Money Flow          | Built   | Income and expense tracking, financial dashboard, iOS Shortcut for quick expense entry                                                                 |
| 3     | Structured Expenses | Built   | Subscriptions, installment payments, upcoming-payment alerts, iOS Shortcut v2 for logging subscriptions and installments                               |
| 4     | Accounts & Debt     | Built   | Cash, bank, and wallet accounts; credit cards and their statements; transfers between your own accounts; reconciliation; net worth across all three    |
| 5     | Planning            | Planned | Savings goals, future commitments timeline, liquidity alerts                                                                                           |
| 6     | Utilities           | Planned | Return calculators, goal simulators, scenario comparators                                                                                              |
| 7     | Automation          | Planned | Assisted expense capture, broker integrations                                                                                                          |

## How it works

1. **Add what you own and owe** -- Create entries for each investment holding (stocks, CEDEARs, term deposits, crypto, mutual funds, bonds, dollar positions, real estate, or anything else), for each cash, bank, or wallet account, and for each credit card. Already keep your investments, income, or expenses in a spreadsheet? Import that CSV or Excel file from the **Import & Export** page -- Renly maps your columns, previews what it found, and lets you confirm before anything is saved. (Accounts and cards are quick to add by hand, and have no importer of their own.) You can export a copy of your data from the same page at any time.

2. **Prices update automatically** -- For stocks, CEDEARs, crypto, and government bonds, Renly fetches prices from market data providers. You don't need to look up prices yourself.

3. **Monthly snapshots** -- Each month, the app records the value of each investment. For ticker-linked investments, this happens automatically. For others (term deposits, real estate), you enter the value manually.

4. **Track money movements** -- Record when you buy more, sell, deposit, or withdraw. This lets Renly separate market gains from money you added, so your return numbers are accurate.

5. **Reconcile your accounts** -- Whenever you like, enter the balance a cash or bank account actually shows. Renly posts a single dated adjustment so the balance is right from that day on -- no need to have logged every movement in between. Cards work the same way, per statement period.

6. **See your dashboard** -- A unified view shows your net worth, cash flow, returns over time, allocation by category, and performance trends. Switch between ARS and USD (or BRL, EUR, GBP) with one click.

7. **Organize with groups** -- Label investments however you want ("Retirement", "Trading", "Kids") and filter your dashboard by group.

Renly supports five currencies: ARS, USD, BRL, EUR, and GBP. All values are stored in their original currency and converted on the fly using daily exchange rates.

## Technology

Renly is a modern web application with three main components:

- **Frontend** -- Built with Next.js (React). Fast, responsive, works on any device with a browser.
- **Backend** -- Built with Python and FastAPI. Handles all the financial calculations, data storage, and external API integrations.
- **Database** -- PostgreSQL for reliable, structured data storage.

The deployable unit is two Docker images plus an environment contract, so Renly is not tied to any single hosting provider.
