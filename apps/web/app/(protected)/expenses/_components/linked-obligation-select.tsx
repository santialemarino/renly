'use client';

import { useMemo } from 'react';
import { CircleDot } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import type { PaymentObligation } from '@/lib/api/payment-obligations';

// "Linked to obligation" dropdown on the expense form (Phase 3 follow-up to Step E).
// Tri-state match model:
//   - 'match'    : every comparable obligation field is filled on the form AND equals (green dot, no warning).
//   - 'mismatch' : at least one filled-on-both-sides field disagrees (no dot, warning fires).
//   - 'unknown'  : a form field needed for comparison is empty (no dot, no warning — user hasn't said yet).
// The 'unknown' state is what differs from a naive ignore-empty model — it avoids prematurely
// showing the green dot when the user has only filled half the form.
//
// In disabled mode (Mark Paid pre-fill), the dot is suppressed entirely — the selection is
// locked and the visual flicker on field edits would be distracting. The mismatch warning
// still fires so the user sees when their edits diverge from the obligation's expectation.

export type MatchStatus = 'match' | 'mismatch' | 'unknown';

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

// Pure: computes the tri-state match between an obligation and the form's current fields.
// A field is "comparable" when the obligation has a value for it (obligation.X is set).
// If the form has a value for that comparable field, we check equality (mismatch on conflict,
// otherwise match contribution). If the form is empty for a comparable field, we mark unknown.
// Obligation fields that are null act as wildcards — they don't gate anything.
export function obligationMatchStatus(
  obligation: PaymentObligation,
  formCurrency: string | undefined,
  formPaymentMethod: string | undefined,
  formCreditCardId: number | undefined,
): MatchStatus {
  let anyUnknown = false;
  if (obligation.currency) {
    if (!formCurrency) anyUnknown = true;
    else if (obligation.currency !== formCurrency) return 'mismatch';
  }
  if (obligation.paymentMethod) {
    if (!formPaymentMethod) anyUnknown = true;
    else if (obligation.paymentMethod !== formPaymentMethod) return 'mismatch';
  }
  if (obligation.creditCardId !== null) {
    if (formCreditCardId === undefined) anyUnknown = true;
    else if (obligation.creditCardId !== formCreditCardId) return 'mismatch';
  }
  return anyUnknown ? 'unknown' : 'match';
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

  // Sort: 'match' first, then 'unknown', then 'mismatch'. Tiebreak by next_due_date ASC.
  const sorted = useMemo(() => {
    const withStatus = obligations.map((o) => ({
      obligation: o,
      status: obligationMatchStatus(o, formCurrency, formPaymentMethod, formCreditCardId),
    }));
    const rank: Record<MatchStatus, number> = { match: 0, unknown: 1, mismatch: 2 };
    withStatus.sort((a, b) => {
      const rankDiff = rank[a.status] - rank[b.status];
      if (rankDiff !== 0) return rankDiff;
      return a.obligation.nextDueDate.localeCompare(b.obligation.nextDueDate);
    });
    return withStatus;
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
        {sorted.map(({ obligation, status }) => (
          <SelectItem key={obligation.id} value={String(obligation.id)}>
            <div className="flex items-center gap-x-2">
              <CircleDot
                className={cn(
                  'size-3 shrink-0',
                  // Show the green dot ONLY on a confirmed full match. Suppress entirely
                  // in disabled mode (Mark Paid) so field-edit flicker doesn't confuse.
                  !disabled && status === 'match' ? 'text-emerald-500' : 'text-transparent',
                )}
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
