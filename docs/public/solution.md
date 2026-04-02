# Renly — What It Is and Who It's For

## What is Renly

Renly is a personal web-based financial management app built for the Argentine retail investor. It started as an investment tracker and is expanding into income/expense management, subscriptions, budgeting, and financial planning.

If you've ever tried to track your portfolio across multiple brokers in a spreadsheet, Renly replaces that spreadsheet with something faster, smarter, and better-looking.

## Who it's for

**Primary user:** A 25-to-45-year-old with investments across multiple Argentine brokers -- Cocos Capital, IOL, Balanz, Bull Market, Brubank, or a traditional bank -- who currently consolidates their portfolio in Excel or doesn't do it at all.

**Secondary user:** Anyone who wants to track personal finances (income, expenses, savings goals) in one place.

## Core values

- **Fast data entry** -- You shouldn't spend more than 15 minutes a month entering investment data. Batch entry, smart defaults, and auto-pricing make this possible.
- **Visual clarity** -- Better than Excel. Actionable metrics, clean charts, and a dashboard that tells you what matters at a glance.
- **Reliability** -- The numbers are always correct. Time-weighted return (TWR) and internal rate of return (IRR) are implemented properly, not approximated.
- **Real Argentine context** -- CEDEARs, ARS exchange rates (oficial, MEP, blue), BYMA prices, government bonds like AL30 and GD30. None of this exists in American financial apps.
- **Extensibility** -- Each new feature builds on what's already there without breaking anything.

## Product phases

| Phase | Name                | What it adds                                                                                                                                           |
| ----- | ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1     | Investments         | Track investments, automatic pricing for stocks/CEDEARs/crypto/bonds, multi-currency support, monthly snapshots, dashboard with returns and allocation |
| 2     | Money Flow          | Income and expense tracking, financial dashboard, iOS Shortcut for quick expense entry                                                                 |
| 3     | Structured Expenses | Subscriptions, installment payments, monthly budgets, alerts                                                                                           |
| 4     | Planning            | Savings goals, future commitments timeline, liquidity alerts                                                                                           |
| 5     | Utilities           | Return calculators, goal simulators, scenario comparators                                                                                              |
| 6     | Automation          | Email parsing for automatic expense capture, broker integrations                                                                                       |

## How it works

1. **Add your investments** -- Create entries for each holding: stocks, CEDEARs, term deposits, crypto, mutual funds, bonds, dollar positions, real estate, or anything else.

2. **Prices update automatically** -- For stocks, CEDEARs, crypto, and government bonds, Renly fetches prices from market data providers. You don't need to look up prices yourself.

3. **Monthly snapshots** -- Each month, the app records the value of each investment. For ticker-linked investments, this happens automatically. For others (term deposits, real estate), you enter the value manually.

4. **Track money movements** -- Record when you buy more, sell, deposit, or withdraw. This lets Renly separate market gains from money you added, so your return numbers are accurate.

5. **See your dashboard** -- A unified view shows your total portfolio value, returns over time, allocation by category, and performance trends. Switch between ARS and USD (or BRL, EUR, GBP) with one click.

6. **Organize with groups** -- Label investments however you want ("Retirement", "Trading", "Kids") and filter your dashboard by group.

Renly supports five currencies: ARS, USD, BRL, EUR, and GBP. All values are stored in their original currency and converted on the fly using daily exchange rates.

## Technology

Renly is a modern web application with three main components:

- **Frontend** -- Built with Next.js (React). Fast, responsive, works on any device with a browser.
- **Backend** -- Built with Python and FastAPI. Handles all the financial calculations, data storage, and external API integrations.
- **Database** -- PostgreSQL for reliable, structured data storage.

Deployed on Vercel (frontend), Railway (backend), and Supabase (database hosting).
