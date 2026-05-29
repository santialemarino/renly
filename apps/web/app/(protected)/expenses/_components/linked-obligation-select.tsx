'use client';

import { useMemo } from 'react';
import { CircleDot } from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';

import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import type { PaymentObligation } from '@/lib/api/payment-obligations';
import { formatDateForLocale } from '@/lib/utils/format';

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
    if (formCreditCardId == null) anyUnknown = true;
    else if (obligation.creditCardId !== formCreditCardId) return 'mismatch';
  }
  return anyUnknown ? 'unknown' : 'match';
}

// Renders one obligation row inside the dropdown. Extracted so the active and the
// archived-currently-linked groups share rendering — the only difference between them
// is the wrapping SelectGroup + label.
function ObligationRow({
  obligation,
  status,
  isSelected,
  disabled,
  locale,
  nextCycleHint,
}: {
  obligation: PaymentObligation;
  status: MatchStatus;
  isSelected: boolean;
  disabled: boolean | undefined;
  locale: string;
  nextCycleHint: (params: { date: string }) => string;
}) {
  // Dot color rules:
  //   - match               -> emerald (positive selection aid, regardless of selection).
  //   - unknown             -> muted (form not fully filled, no signal yet).
  //   - mismatch + selected -> amber (pairs 1:1 with the StyledHint warning below).
  //   - mismatch + unselected -> muted (avoid lighting up the dropdown with amber
  //                              on browse — sort order already deprioritises them).
  //   - disabled mode (Mark Paid) -> dot suppressed entirely so the trigger text
  //                              aligns naturally to the left with no phantom indent.
  const dotColor =
    status === 'match'
      ? 'text-emerald-500'
      : status === 'mismatch' && isSelected
        ? 'text-amber-500'
        : 'text-muted-foreground';
  return (
    <SelectItem value={String(obligation.id)}>
      <div className="flex min-w-0 items-center gap-x-2">
        {!disabled && (
          <CircleDot className={cn('size-3 shrink-0 transition-colors', dotColor)} aria-hidden />
        )}
        <span className="truncate">{obligation.name}</span>
        <span className="text-paragraph-xs text-muted-foreground">
          {nextCycleHint({ date: formatDateForLocale(obligation.nextDueDate, locale) })}
        </span>
      </div>
    </SelectItem>
  );
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
  const locale = useLocale();
  const t = useTranslations('expenses');
  const tCommon = useTranslations('common');

  // Partition into active vs archived. Archived obligations enter via `include_ids` from
  // the page server component when an in-scope expense links to a since-archived row
  // (Phase 3 audit-round-3 follow-up). Active rows go in the main list with the existing
  // match-aware sort; archived rows go in a separate "Currently linked (archived)" group
  // at the bottom — the user can keep or change the link but doesn't browse archived plans
  // for new links.
  const { activeSorted, archivedSorted } = useMemo(() => {
    const rank: Record<MatchStatus, number> = { match: 0, unknown: 1, mismatch: 2 };
    const active: { obligation: PaymentObligation; status: MatchStatus }[] = [];
    const archived: { obligation: PaymentObligation; status: MatchStatus }[] = [];
    for (const o of obligations) {
      const entry = {
        obligation: o,
        status: obligationMatchStatus(o, formCurrency, formPaymentMethod, formCreditCardId),
      };
      (o.isActive ? active : archived).push(entry);
    }
    // Same match-aware sort within each bucket. Archived sort by next_due_date alone
    // matters less (UI groups them under a clear label) but stays consistent.
    const sortBy = (a: (typeof active)[number], b: (typeof active)[number]) => {
      const rankDiff = rank[a.status] - rank[b.status];
      if (rankDiff !== 0) return rankDiff;
      return a.obligation.nextDueDate.localeCompare(b.obligation.nextDueDate);
    };
    active.sort(sortBy);
    archived.sort(sortBy);
    return { activeSorted: active, archivedSorted: archived };
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
        {activeSorted.map(({ obligation, status }) => (
          <ObligationRow
            key={obligation.id}
            obligation={obligation}
            status={status}
            isSelected={obligation.id === value}
            disabled={disabled}
            locale={locale}
            nextCycleHint={(p) => tCommon('nextCycleHint', p)}
          />
        ))}
        {archivedSorted.length > 0 && (
          <SelectGroup>
            <SelectLabel>{t('form.linkedObligation.archivedGroupLabel')}</SelectLabel>
            {archivedSorted.map(({ obligation, status }) => (
              <ObligationRow
                key={obligation.id}
                obligation={obligation}
                status={status}
                isSelected={obligation.id === value}
                disabled={disabled}
                locale={locale}
                nextCycleHint={(p) => tCommon('nextCycleHint', p)}
              />
            ))}
          </SelectGroup>
        )}
      </SelectContent>
    </Select>
  );
}
