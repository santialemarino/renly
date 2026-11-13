// `import type` and it has to stay that way: lib/api/accounts is `server-only`, while this module is
// reached from a client component. A type import is erased at compile time, so it carries nothing into
// the client bundle; turning it into a value import would break the build.
import type { Account } from '@/lib/api/accounts';
import type { AccountType } from '@/lib/constants/accounts';
import type { PaymentMethod } from '@/lib/constants/categories';

/*
 * What the global quick-add can honestly pre-fill — §8.2 asks for "date, currency, account and scope
 * pre-filled" and defines none of the four, so each rule is stated here once.
 *
 * Pure, and under lib/ for the reason every rule in this app is: the quick-add's forms render Radix
 * primitives, which cannot be mounted in the web unit suite at all, so a rule living inside one is a
 * rule nothing tests.
 *
 * The two fields with no rule to state are not here. The DATE is today in the user's stored timezone
 * (`todayInTimezone`, which every other dated form already uses), and the SCOPE is always private —
 * fail-closed, and the only value that adds no friction for a solo user, which is every public user at
 * launch.
 */

/*
 * The currency the quick-add opens on: the user's PRIMARY setting, and only when the entry forms'
 * picker would actually offer it. An empty string means "ask", which is the private forms' own default.
 *
 * The active DISPLAY currency is deliberately not the source. It is a viewing lens rather than a fact
 * about money — it can read `original`, which is no currency at all — and letting what somebody is
 * looking at decide what they SPENT is the conflation this initiative's "a filter is never a mode" rule
 * exists to prevent.
 *
 * The supported-set check is load-bearing, not padding. `PUT /settings` takes `primary_currency` as a
 * bare string and the preferences picker offers the whole ISO list, while every entry form restricts
 * its own picker to the API's convertible set — so a user whose primary is JPY would meet a form seeded
 * with a currency its picker cannot show and the API answers 422 for. An UNLOADED set (undefined) is
 * not an empty one: the picker degrades to the full ISO list in that case, so the primary is on offer
 * and pre-filling it is right.
 *
 * There is no guard for an unset primary and there should not be: an empty string is already the "ask"
 * answer, so it falls out of both branches unchanged. A guard that cannot change an answer is a branch
 * no test can reach.
 */
export function quickAddCurrency(
  primaryCurrency: string,
  supportedCurrencies: string[] | undefined,
): string {
  if (supportedCurrencies && !supportedCurrencies.includes(primaryCurrency)) return '';
  return primaryCurrency;
}

/*
 * The funding account the quick-add opens on: one, and only when the currency leaves exactly ONE
 * active account to choose from — the only reading of "the account" that cannot be wrong.
 *
 * Not the most recent and not the first alphabetically. An account link MOVES a balance, so both of
 * those would attach a cash leg to every entry on a guess; with a single candidate there is nothing to
 * guess, and the pick is still on screen and overridable before anything is saved.
 *
 * Archived accounts are excluded because the picker never offers one. A currency-less call answers null
 * too — an entry's amount and its account carry one denomination, so "the only account you have" is not
 * the claim "the only account this entry could use" — and it needs no guard of its own: no account's
 * currency is the empty string, so the filter already returns nothing.
 */
export function soleEligibleAccountId(accounts: Account[], currency: string): number | null {
  // Destructured rather than indexed by length, so there is no `eligible[0]` that TypeScript thinks
  // could be undefined and no branch that can never be taken.
  const [only, ...rest] = accounts.filter(
    (account) => account.isActive && account.currency === currency,
  );
  return only && rest.length === 0 ? only.id : null;
}

/*
 * The account type each payment method draws from. Cash comes out of a cash account; a debit card and a
 * transfer move money out of a bank account. A credit-card charge has no entry here on purpose: it
 * raises the card's balance and only draws cash later, at settlement, so it never names an account (the
 * API refuses the pairing).
 */
const ACCOUNT_TYPE_BY_METHOD: Partial<Record<PaymentMethod, AccountType>> = {
  cash: 'cash',
  debit: 'bank',
  transfer: 'bank',
};

/*
 * The account an expense's "Paid from" opens on: the one active account of the type its payment method
 * draws from, in its currency — and nothing when there is no method yet, when the method is a card, or
 * when the type and currency leave anything other than exactly one account.
 *
 * The method matters as much as the currency. Pre-filling the only ARS account whatever the method put
 * a bank account under a cash expense, which then moved the bank balance for money that left a wallet.
 * Both the quick-add and the /expenses Add button open the same form, which applies this rule itself, so
 * the two doors agree.
 */
export function methodMatchedAccountId(
  accounts: Account[],
  currency: string,
  paymentMethod: PaymentMethod | undefined,
): number | null {
  const type = paymentMethod ? ACCOUNT_TYPE_BY_METHOD[paymentMethod] : undefined;
  if (!type) return null;
  return soleEligibleAccountId(
    accounts.filter((account) => account.type === type),
    currency,
  );
}
