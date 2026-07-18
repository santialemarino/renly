'use client';

import { useMemo } from 'react';
import { CircleDot } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { cn } from '@repo/ui/lib';
import { FormCombobox, type FormComboboxOption } from '@/components/form-combobox';
import type { PaymentObligation } from '@/lib/api/payment-obligations';
import { useFormatters } from '@/lib/i18n/formatters';

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

// Renders the content of one obligation row (used as a FormCombobox option's `render`). Extracted so
// the active and the archived-currently-linked groups share rendering — the only difference between
// them is the option's `group` heading.
function ObligationRowContent({
  obligation,
  status,
  isSelected,
  disabled,
  nextCycleHint,
}: {
  obligation: PaymentObligation;
  status: MatchStatus;
  isSelected: boolean;
  disabled: boolean | undefined;
  nextCycleHint: (params: { date: string }) => string;
}) {
  const fmt = useFormatters();
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
    <div className="flex min-w-0 items-center gap-x-2">
      {!disabled && (
        <CircleDot className={cn('size-3 shrink-0 transition-colors', dotColor)} aria-hidden />
      )}
      <span className="truncate">{obligation.name}</span>
      <span className="text-paragraph-xs text-muted-foreground">
        {nextCycleHint({ date: fmt.date(obligation.nextDueDate) })}
      </span>
    </div>
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
  const t = useTranslations('expenses');
  const tCommon = useTranslations('common');

  // Partition into active vs archived. Archived obligations enter via `include_ids` from
  // the page server component when an in-scope expense links to a since-archived row
  // (Phase 3 audit-round-3 follow-up). The server-side fetch is page-wide — it pulls in
  // ALL archived obligations linked by any expense in scope — but the dropdown only
  // surfaces the one the CURRENT row is actually linked to (via `value`). Without this
  // filter, opening Expense A's edit would show archived plans linked to Expense B in
  // the same list, and the "Currently linked (archived)" label would be a half-truth.
  const { activeSorted, archivedSorted } = useMemo(() => {
    const rank: Record<MatchStatus, number> = { match: 0, unknown: 1, mismatch: 2 };
    const active: { obligation: PaymentObligation; status: MatchStatus }[] = [];
    const archived: { obligation: PaymentObligation; status: MatchStatus }[] = [];
    for (const o of obligations) {
      const entry = {
        obligation: o,
        status: obligationMatchStatus(o, formCurrency, formPaymentMethod, formCreditCardId),
      };
      // Archived plans only render when they match the row's current FK — otherwise
      // they're dropped entirely (active plans in the wider fetch are unaffected).
      if (o.isActive) {
        active.push(entry);
      } else if (value !== null && o.id === value) {
        archived.push(entry);
      }
    }
    const sortBy = (a: (typeof active)[number], b: (typeof active)[number]) => {
      const rankDiff = rank[a.status] - rank[b.status];
      if (rankDiff !== 0) return rankDiff;
      return a.obligation.nextDueDate.localeCompare(b.obligation.nextDueDate);
    };
    active.sort(sortBy);
    archived.sort(sortBy);
    return { activeSorted: active, archivedSorted: archived };
  }, [obligations, value, formCurrency, formPaymentMethod, formCreditCardId]);

  const archivedGroupLabel = t('form.linkedObligation.archivedGroupLabel');
  const toOption = (
    { obligation, status }: { obligation: PaymentObligation; status: MatchStatus },
    group?: string,
  ): FormComboboxOption => ({
    value: String(obligation.id),
    label: obligation.name,
    group,
    render: (
      <ObligationRowContent
        obligation={obligation}
        status={status}
        isSelected={obligation.id === value}
        disabled={disabled}
        nextCycleHint={(p) => tCommon('nextCycleHint', p)}
      />
    ),
  });

  const options: FormComboboxOption[] = [
    { value: NONE_VALUE, label: t('form.linkedObligation.none') },
    ...activeSorted.map((entry) => toOption(entry)),
    ...archivedSorted.map((entry) => toOption(entry, archivedGroupLabel)),
  ];

  return (
    <FormCombobox
      value={value !== null ? String(value) : NONE_VALUE}
      onValueChange={(v) => onChange(v === NONE_VALUE ? null : Number(v))}
      disabled={disabled}
      placeholder={t('form.linkedObligation.placeholder')}
      options={options}
    />
  );
}
