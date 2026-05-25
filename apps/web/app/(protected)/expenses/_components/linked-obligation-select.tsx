'use client';

import { useMemo } from 'react';
import { CircleDot } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import type { PaymentObligation } from '@/lib/api/payment-obligations';

// "Linked to obligation" dropdown on the expense form (Phase 3 follow-up to Step E).
// - Sorts active obligations: full match (currency + payment method + card all align) first,
//   then by next due date.
// - Renders a small green dot next to fully-matching obligations as a visual hint.
// - Compute the warning state in the parent so the form can show an inline copy below
//   when the selected obligation's keys don't fully match what the user is entering.

export interface ObligationMismatch {
  differentCurrency: { obligation: string; form: string } | null;
  differentPaymentMethod: { obligation: string | null; form: string } | null;
  differentCard: { obligation: number | null; form: number } | null;
}

interface LinkedObligationSelectProps {
  obligations: PaymentObligation[];
  value: number | null;
  disabled?: boolean;
  formCurrency: string | undefined;
  formPaymentMethod: string | undefined;
  formCreditCardId: number | undefined;
  onChange: (id: number | null) => void;
}

const NONE_VALUE = 'none';

// Pure: returns true iff every non-null obligation key aligns with the corresponding
// form field. A key is "ignored" when EITHER side is empty so we don't penalise users
// for partial form fills (e.g. obligation has no payment_method but the user picked one).
export function isObligationMatch(
  obligation: PaymentObligation,
  formCurrency: string | undefined,
  formPaymentMethod: string | undefined,
  formCreditCardId: number | undefined,
): boolean {
  if (obligation.currency && formCurrency && obligation.currency !== formCurrency) return false;
  if (
    obligation.paymentMethod &&
    formPaymentMethod &&
    obligation.paymentMethod !== formPaymentMethod
  ) {
    return false;
  }
  if (
    obligation.creditCardId !== null &&
    formCreditCardId !== undefined &&
    obligation.creditCardId !== formCreditCardId
  ) {
    return false;
  }
  return true;
}

export function LinkedObligationSelect({
  obligations,
  value,
  disabled,
  formCurrency,
  formPaymentMethod,
  formCreditCardId,
  onChange,
}: LinkedObligationSelectProps) {
  const t = useTranslations('expenses');

  // Sort: matches first, then by next_due_date ASC.
  const sorted = useMemo(() => {
    const withScore = obligations.map((o) => ({
      obligation: o,
      matches: isObligationMatch(o, formCurrency, formPaymentMethod, formCreditCardId),
    }));
    withScore.sort((a, b) => {
      if (a.matches !== b.matches) return a.matches ? -1 : 1;
      return a.obligation.nextDueDate.localeCompare(b.obligation.nextDueDate);
    });
    return withScore;
  }, [obligations, formCurrency, formPaymentMethod, formCreditCardId]);

  return (
    <Select
      value={value !== null ? String(value) : NONE_VALUE}
      onValueChange={(v) => onChange(v === NONE_VALUE ? null : Number(v))}
      disabled={disabled}
    >
      <SelectTrigger className="w-full">
        <SelectValue placeholder={t('form.linkedObligation.placeholder')} />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={NONE_VALUE}>{t('form.linkedObligation.none')}</SelectItem>
        {sorted.map(({ obligation, matches }) => (
          <SelectItem key={obligation.id} value={String(obligation.id)}>
            <div className="flex items-center gap-x-2">
              <CircleDot
                className={cn('size-3 shrink-0', matches ? 'text-emerald-500' : 'text-transparent')}
                aria-hidden
              />
              <span>{obligation.name}</span>
            </div>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

// Builds the mismatch struct used by the form to render the inline warning.
// Returns null when the obligation fully matches OR no obligation is selected.
export function computeObligationMismatch(
  obligation: PaymentObligation | undefined,
  formCurrency: string | undefined,
  formPaymentMethod: string | undefined,
  formCreditCardId: number | undefined,
): ObligationMismatch | null {
  if (!obligation) return null;
  const mismatch: ObligationMismatch = {
    differentCurrency: null,
    differentPaymentMethod: null,
    differentCard: null,
  };
  if (obligation.currency && formCurrency && obligation.currency !== formCurrency) {
    mismatch.differentCurrency = { obligation: obligation.currency, form: formCurrency };
  }
  if (
    obligation.paymentMethod &&
    formPaymentMethod &&
    obligation.paymentMethod !== formPaymentMethod
  ) {
    mismatch.differentPaymentMethod = {
      obligation: obligation.paymentMethod,
      form: formPaymentMethod,
    };
  }
  if (
    obligation.creditCardId !== null &&
    formCreditCardId !== undefined &&
    obligation.creditCardId !== formCreditCardId
  ) {
    mismatch.differentCard = { obligation: obligation.creditCardId, form: formCreditCardId };
  }
  if (!mismatch.differentCurrency && !mismatch.differentPaymentMethod && !mismatch.differentCard) {
    return null;
  }
  return mismatch;
}
