# Investment Categories

Renly supports 10 investment categories. Each one represents a different type of financial holding you might have. Some categories support automatic pricing (the app fetches current prices for you), while others require manual entry.

---

## Categories at a glance

| Category           | Auto-priced | Price source        | Typical currency |
| ------------------ | ----------- | ------------------- | ---------------- |
| Stocks             | Yes         | Yahoo Finance       | USD              |
| CEDEARs            | Yes         | Yahoo Finance (.BA) | ARS              |
| Crypto             | Yes         | CoinGecko           | USD              |
| Government Bonds   | Yes         | Yahoo Finance (.BA) | ARS or USD       |
| Corporate Bonds    | No          | Manual              | ARS or USD       |
| FCI (Mutual Funds) | No          | Manual              | ARS              |
| Dollars            | No          | Manual              | USD              |
| Real Estate        | No          | Manual              | USD              |
| Term Deposit       | No          | Manual              | ARS              |
| Other              | No          | Manual              | Any              |

---

## Stocks

US-listed stocks traded on American exchanges (NYSE, NASDAQ). Examples: AAPL (Apple), MSFT (Microsoft), GOOGL (Alphabet), AMZN (Amazon).

When you add a stock and provide its ticker symbol, Renly fetches prices automatically from Yahoo Finance. You'll see updated values without entering them yourself.

**Ticker:** Yes (e.g., `AAPL`)
**Price history:** Yes -- daily historical prices are available.

## CEDEARs

CEDEARs (Certificados de Deposito Argentinos) are certificates traded on BYMA (the Argentine stock exchange) that represent shares of foreign companies. They let you invest in Apple, Google, or Tesla without needing a US brokerage account.

Renly fetches CEDEAR prices from Yahoo Finance using the `.BA` suffix (e.g., `AAPL.BA` for Apple's CEDEAR).

**Ticker:** Yes (e.g., `AAPL.BA`)
**Price history:** Yes -- daily historical prices are available.

### CEDEAR ratios

Each CEDEAR has a conversion ratio to the underlying stock. For example, if the ratio for AAPL.BA is 10:1, it means you need 10 CEDEARs to equal one share of Apple stock. These ratios matter for understanding the real value of your position.

Renly fetches CEDEAR ratios monthly from Banco Comafi, the principal issuing entity for stock CEDEARs in Argentina (authorized by CNV, 90%+ of programs). Ratios can change when the underlying stock splits.

## Crypto

Cryptocurrencies like Bitcoin (BTC), Ethereum (ETH), Solana (SOL), etc. Prices are fetched from CoinGecko.

**Ticker:** Yes (e.g., `BTC`, `ETH`)
**Price history:** No -- only the latest price is fetched. Historical values come from your monthly snapshots.

## Government Bonds

Argentine sovereign bonds traded on BYMA, such as AL30 (Bonar 2030) and GD30 (Global 2030). These are denominated in ARS or USD depending on the series.

Renly fetches bond prices from Yahoo Finance using the `.BA` suffix (e.g., `AL30.BA`).

**Ticker:** Yes (e.g., `AL30.BA`, `GD30.BA`)
**Price history:** Yes -- daily historical prices are available.

## Corporate Bonds

Corporate bonds (Obligaciones Negociables, or ONs) issued by Argentine companies. Examples: YPF, Pampa Energia, Telecom Argentina.

These are currently manual-entry only. Reliable, automated price feeds for Argentine corporate bonds are not yet available through free APIs.

**Ticker:** No
**Price history:** No -- you enter values yourself each month.

## FCI (Mutual Funds)

Fondos Comunes de Inversion, Argentine mutual funds. Each FCI has a CAFCI code (the industry registry), but the CAFCI API currently returns authentication errors, so automatic pricing is not available.

You enter the value of your FCI position manually each month. The ticker field accepts a CAFCI code for reference, but it is not used for price fetching at this time.

**Ticker:** Yes (CAFCI code, for reference only)
**Price history:** No -- manual entry required.

## Dollars

Physical or digital dollar positions. This is for tracking money held in US dollars -- in a bank account, under the mattress, or in a broker's money market account.

**Ticker:** No
**Price history:** No -- you enter the amount yourself.

## Real Estate

Real estate investments: properties, land, or REITs (if not publicly traded). You track these by entering their estimated value periodically.

**Ticker:** No
**Price history:** No -- you enter the estimated value yourself.

## Term Deposit

Fixed-term deposits (plazos fijos) at banks. These have a known value at maturity, and you update them monthly as interest accrues or as you renew.

**Ticker:** No
**Price history:** No -- you enter the current value yourself.

## Other

Anything that doesn't fit the categories above: collectibles, private equity, loans to friends, art, etc.

**Ticker:** No
**Price history:** No -- you enter the value yourself.

---

## How automatic pricing works

For investments with a ticker (stocks, CEDEARs, crypto, government bonds), Renly:

1. **Fetches prices daily** from the relevant market data provider (Yahoo Finance or CoinGecko).
2. **Generates automatic snapshots** at the end of each month. If you hold 50 shares of AAPL and the price on January 31st is $182.50, the app creates a snapshot with a value of $9,125.00 automatically.
3. **Lets you look up prices** when entering past data. If you're entering a snapshot for November 2025, the app can fetch the price from that date so you don't have to look it up yourself.

## What "manual entry" means

For investments without automatic pricing (corporate bonds, FCI, dollars, real estate, term deposits, other), you enter the value yourself. Typically this means:

- Once a month, you go to the data entry screen.
- You see all your investments listed with their previous values as placeholders.
- You type in the current value for anything that changed.
- Hit save. That's it.

The goal is to make this fast -- you should only need to update numbers that actually changed.
