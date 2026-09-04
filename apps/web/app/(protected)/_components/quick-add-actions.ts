'use server';

import { getAccounts, type Account } from '@/lib/api/accounts';
import { getCreditCards, type CreditCard } from '@/lib/api/credit-cards';
import { getGroups, type Group } from '@/lib/api/groups';
import { getInstallments, type Installment } from '@/lib/api/installments';
import { getPaymentObligations, type PaymentObligation } from '@/lib/api/payment-obligations';
import { getSubscriptions, type Subscription } from '@/lib/api/subscriptions';

// Everything the four entry forms offer in a picker, for the global quick-add.
export interface QuickAddContext {
  accounts: Account[];
  creditCards: CreditCard[];
  groups: Group[];
  obligations: PaymentObligation[];
  subscriptions: Subscription[];
  installments: Installment[];
}

/*
 * What the quick-add's forms need, read on demand rather than with every page.
 *
 * A read in an actions file, which is unusual and deliberate — the same shape as
 * `getGroupExpenseContext` and `getAutoChargeMatch`, and for the same reason. The alternative is the
 * protected LAYOUT, which would mean these six reads on every navigation of every protected page, for
 * a dialog most visits never open; and `/expenses` and `/income` already fetch all six themselves, so
 * it would also be duplicated work on the two pages that need them anyway.
 *
 * Every list is the ACTIVE set, because this surface only ever CREATES. The list pages ask for
 * archived rows so a saved entry can still render the name of a since-archived link — there is no
 * saved entry here, and the pickers never OFFER an archived row in any case.
 *
 * Accounts come back in the caller's own scope, which is `getAccounts`' default: a private entry
 * cannot be funded from a group's account at all, and the scope control is how joint money is reached.
 *
 * Each read fails soft to an empty list, which is what every page that renders these pickers already
 * does. The degradation is honest rather than broken: a field with nothing to offer hides itself, so a
 * total failure leaves a form that still records an entry with no links — and no group, which is
 * exactly a solo user's form.
 */
export async function getQuickAddContext(): Promise<QuickAddContext> {
  const [accounts, creditCards, groups, obligations, subscriptions, installments] =
    await Promise.all([
      getAccounts().catch(() => []),
      getCreditCards().catch(() => []),
      getGroups().catch(() => []),
      getPaymentObligations().catch(() => []),
      getSubscriptions().catch(() => []),
      getInstallments().catch(() => []),
    ]);
  return { accounts, creditCards, groups, obligations, subscriptions, installments };
}
