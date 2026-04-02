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

### Exchange Rates

Renly stores historical exchange rates updated automatically every day:

- **USD/ARS** in three flavors: oficial (government rate), MEP (financial market rate), and blue (informal market rate) -- sourced from DolarApi
- **USD/BRL, USD/EUR, USD/GBP** -- sourced from Frankfurter (European Central Bank data)

All currency conversions go through USD as a pivot. For example, to convert from BRL to ARS, the app converts BRL to USD first, then USD to ARS. This keeps the system simple while supporting any currency pair.

### Asset Prices

For investments with a ticker (stocks, CEDEARs, crypto, government bonds), Renly stores historical prices fetched from external providers like Yahoo Finance and CoinGecko. These prices power automatic snapshots and let you look up past prices when entering historical data.

### CEDEAR Ratios

CEDEARs have a conversion ratio to their underlying stock. For example, 10 CEDEARs of AAPL.BA might equal 1 share of Apple stock. These ratios are updated monthly from Banco Comafi, the principal issuing entity for stock CEDEARs in Argentina (90%+ of programs). Ratios change only when the underlying stock splits.

### Settings

Each user has personal preferences that control how the app behaves:

- Which currencies to display (primary and secondary)
- Which USD/ARS rate to use for conversions (oficial, MEP, or blue)
- Dashboard period presets and display options

---

## How everything connects

```
User
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
 |-- has --> Settings
 |           (currency preferences, display options)
 |
 |-- has many --> Groups
                  (each group can contain many investments)
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
