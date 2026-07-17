'use client';

import { useMemo } from 'react';
import { CircleDot } from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';

import { cn } from '@repo/ui/lib';
import { FormCombobox, type FormComboboxOption } from '@/components/form-combobox';
import type { Installment } from '@/lib/api/installments';
import type { Subscription } from '@/lib/api/subscriptions';
import { formatDateForLocale } from '@/lib/utils/format';

// "Linked to subscription / installment" dropdown on the expense form (Phase 3, follow-up 3a).
// One combined dropdown with two groups (Subscriptions + Installments). Sibling of
// LinkedObligationSelect — mutual exclusivity across the three FKs is enforced one level up
// by the form. Rendered in both CREATE and EDIT modes after Item 10 (the FK is now editable
// on PUT); only Mark Paid hides it via the prefill gate in ExpenseFormDialog. Tri-state
// match model mirrors LinkedObligationSelect:
//   - 'match'    : every comparable plan field is filled on the form AND equals (green dot).
//   - 'mismatch' : at least one filled-on-both-sides field disagrees (no dot, warning fires).
//   - 'unknown'  : a form field needed for comparison is empty (no dot, no warning).
// The 'unknown' state avoids prematurely showing the green dot when the user has only
// filled half the form.

export type MatchStatus = 'match' | 'mismatch' | 'unknown';

export type LinkedSubInstallmentValue =
  | { kind: 'subscription'; id: number }
  | { kind: 'installment'; id: number };

interface LinkedSubInstallmentSelectProps {
  subscriptions: Subscription[];
  installments: Installment[];
  value: LinkedSubInstallmentValue | null;
  formCurrency: string | undefined;
  formPaymentMethod: string | undefined;
  formCreditCardId: number | undefined;
  onChange: (value: LinkedSubInstallmentValue | null) => void;
}

const NONE_VALUE = 'none';

const STATUS_RANK: Record<MatchStatus, number> = { match: 0, unknown: 1, mismatch: 2 };

// Option values are prefixed so a single dropdown can encode both entity types
// without colliding ids (a subscription with id=3 and an installment with id=3 are
// different selections).
function encodeValue(value: LinkedSubInstallmentValue | null): string {
  if (value === null) return NONE_VALUE;
  return value.kind === 'subscription' ? `sub:${value.id}` : `inst:${value.id}`;
}

function decodeValue(raw: string): LinkedSubInstallmentValue | null {
  if (raw === NONE_VALUE) return null;
  const [kind, idStr] = raw.split(':');
  const id = Number(idStr);
  if (!Number.isFinite(id)) return null;
  if (kind === 'sub') return { kind: 'subscription', id };
  if (kind === 'inst') return { kind: 'installment', id };
  return null;
}

// Pure: computes the tri-state match between a plan-like commitment and the form's
// current fields. A field is "comparable" when the plan has a value for it. If the
// form has a value for that comparable field, we check equality; if the form is empty
// for a comparable field, we mark unknown. Plan fields that are null act as wildcards.
// Used for both subscriptions and installments — both expose the same three fields.
// Mirrors obligationMatchStatus; amount is intentionally NOT compared (price can drift
// from the plan's expected value without invalidating the link).
function planMatchStatus(
  plan: {
    currency: string;
    paymentMethod: string | null;
    creditCardId: number | null;
  },
  formCurrency: string | undefined,
  formPaymentMethod: string | undefined,
  formCreditCardId: number | undefined,
): MatchStatus {
  let anyUnknown = false;
  if (plan.currency) {
    if (!formCurrency) anyUnknown = true;
    else if (plan.currency !== formCurrency) return 'mismatch';
  }
  if (plan.paymentMethod) {
    if (!formPaymentMethod) anyUnknown = true;
    else if (plan.paymentMethod !== formPaymentMethod) return 'mismatch';
  }
  if (plan.creditCardId !== null) {
    if (formCreditCardId == null) anyUnknown = true;
    else if (plan.creditCardId !== formCreditCardId) return 'mismatch';
  }
  return anyUnknown ? 'unknown' : 'match';
}

// Same helper, exported for the form's selected-item mismatch warning. Accepts either
// a Subscription or an Installment — the comparable fields have identical shape.
export function subInstallmentMatchStatus(
  plan: Subscription | Installment,
  formCurrency: string | undefined,
  formPaymentMethod: string | undefined,
  formCreditCardId: number | undefined,
): MatchStatus {
  return planMatchStatus(plan, formCurrency, formPaymentMethod, formCreditCardId);
}

// Next cuota date for installments — reads the server-computed `next_cuota_date` so the
// dropdown sort matches the installments table + the SQL `make_interval` ordering exactly,
// including month-end clamping (Jan 31 + 1 month → Feb 28). Falls back to start_date when
// the field is null (fully-paid plans, which shouldn't surface here because the dropdown
// is fed active-only, but the guard keeps the sort comparator total).
function installmentNextChargeDate(installment: Installment): string {
  return installment.nextCuotaDate ?? installment.startDate;
}

// Dot color rules:
//   - match               -> emerald (positive selection aid, regardless of selection).
//   - unknown             -> muted (form not fully filled, no signal yet).
//   - mismatch + selected -> amber (pairs 1:1 with the StyledHint warning below).
//   - mismatch + unselected -> muted (avoid lighting up the dropdown with amber on
//                              browse — sort order already deprioritises them).
function dotColorClass(status: MatchStatus, isSelected: boolean): string {
  if (status === 'match') return 'text-emerald-500';
  if (status === 'mismatch' && isSelected) return 'text-amber-500';
  return 'text-muted-foreground';
}

export function LinkedSubInstallmentSelect({
  subscriptions,
  installments,
  value,
  formCurrency,
  formPaymentMethod,
  formCreditCardId,
  onChange,
}: LinkedSubInstallmentSelectProps) {
  const locale = useLocale();
  const t = useTranslations('expenses');
  const tCommon = useTranslations('common');

  // Sort within each group: match -> unknown -> mismatch, then next-cycle-date ASC.
  // Active and archived go in separate buckets — archived plans enter via `include_ids`
  // when an in-scope expense links to a since-archived row (Phase 3 audit-round-3
  // follow-up). The server-side fetch is page-wide — it pulls in ALL archived plans
  // linked by any expense in scope — but the dropdown only surfaces the archived plan
  // the CURRENT row is actually linked to (via `value`). Without this filter, opening
  // Expense A's edit would show archived plans linked to Expense B, and the "Currently
  // linked (archived)" label would be a half-truth.
  const sortedSubscriptions = useMemo(() => {
    const isCurrentArchivedSub = (id: number) =>
      value !== null && value.kind === 'subscription' && value.id === id;
    const active: { sub: Subscription; status: MatchStatus }[] = [];
    const archived: { sub: Subscription; status: MatchStatus }[] = [];
    for (const s of subscriptions) {
      const entry = {
        sub: s,
        status: planMatchStatus(s, formCurrency, formPaymentMethod, formCreditCardId),
      };
      if (s.isActive) {
        active.push(entry);
      } else if (isCurrentArchivedSub(s.id)) {
        archived.push(entry);
      }
    }
    const sortBy = (a: (typeof active)[number], b: (typeof active)[number]) => {
      const rankDiff = STATUS_RANK[a.status] - STATUS_RANK[b.status];
      if (rankDiff !== 0) return rankDiff;
      return a.sub.nextBillingDate.localeCompare(b.sub.nextBillingDate);
    };
    active.sort(sortBy);
    archived.sort(sortBy);
    return { active, archived };
  }, [subscriptions, value, formCurrency, formPaymentMethod, formCreditCardId]);

  const sortedInstallments = useMemo(() => {
    const isCurrentArchivedInst = (id: number) =>
      value !== null && value.kind === 'installment' && value.id === id;
    const active: { inst: Installment; status: MatchStatus; nextChargeDate: string }[] = [];
    const archived: { inst: Installment; status: MatchStatus; nextChargeDate: string }[] = [];
    for (const i of installments) {
      const entry = {
        inst: i,
        status: planMatchStatus(i, formCurrency, formPaymentMethod, formCreditCardId),
        nextChargeDate: installmentNextChargeDate(i),
      };
      if (i.isActive) {
        active.push(entry);
      } else if (isCurrentArchivedInst(i.id)) {
        archived.push(entry);
      }
    }
    const sortBy = (a: (typeof active)[number], b: (typeof active)[number]) => {
      const rankDiff = STATUS_RANK[a.status] - STATUS_RANK[b.status];
      if (rankDiff !== 0) return rankDiff;
      return a.nextChargeDate.localeCompare(b.nextChargeDate);
    };
    active.sort(sortBy);
    archived.sort(sortBy);
    return { active, archived };
  }, [installments, value, formCurrency, formPaymentMethod, formCreditCardId]);

  const hasActiveSubscriptions = sortedSubscriptions.active.length > 0;
  const hasActiveInstallments = sortedInstallments.active.length > 0;
  const hasArchivedLinked =
    sortedSubscriptions.archived.length + sortedInstallments.archived.length > 0;

  // Row content for a subscription / installment (used as a FormCombobox option's `render`); rendered
  // in both the active and the archived groups, which differ only by the option's `group` heading.
  const subRowContent = (sub: Subscription, status: MatchStatus) => {
    const isSelected = value !== null && value.kind === 'subscription' && value.id === sub.id;
    return (
      <div className="flex min-w-0 items-center gap-x-2">
        <CircleDot
          className={cn('size-3 shrink-0 transition-colors', dotColorClass(status, isSelected))}
          aria-hidden
        />
        <span className="truncate">{sub.name}</span>
        <span className="text-paragraph-xs text-muted-foreground">
          {tCommon('nextCycleHint', { date: formatDateForLocale(sub.nextBillingDate, locale) })}
        </span>
      </div>
    );
  };
  const instRowContent = (inst: Installment, status: MatchStatus, nextChargeDate: string) => {
    const isSelected = value !== null && value.kind === 'installment' && value.id === inst.id;
    return (
      <div className="flex min-w-0 items-center gap-x-2">
        <CircleDot
          className={cn('size-3 shrink-0 transition-colors', dotColorClass(status, isSelected))}
          aria-hidden
        />
        <span className="truncate">{installmentLabel(inst)}</span>
        <span className="text-paragraph-xs text-muted-foreground">
          {tCommon('nextCycleHint', { date: formatDateForLocale(nextChargeDate, locale) })}
        </span>
      </div>
    );
  };

  const subscriptionsLabel = t('form.linkedSubInstallment.subscriptionsLabel');
  const installmentsLabel = t('form.linkedSubInstallment.installmentsLabel');
  const archivedGroupLabel = t('form.linkedSubInstallment.archivedGroupLabel');
  const subOption = (
    { sub, status }: { sub: Subscription; status: MatchStatus },
    group: string,
  ): FormComboboxOption => ({
    value: `sub:${sub.id}`,
    label: sub.name,
    group,
    render: subRowContent(sub, status),
  });
  const instOption = (
    {
      inst,
      status,
      nextChargeDate,
    }: { inst: Installment; status: MatchStatus; nextChargeDate: string },
    group: string,
  ): FormComboboxOption => ({
    value: `inst:${inst.id}`,
    label: installmentLabel(inst),
    group,
    render: instRowContent(inst, status, nextChargeDate),
  });

  const options: FormComboboxOption[] = [
    { value: NONE_VALUE, label: t('form.linkedSubInstallment.none') },
    ...(hasActiveSubscriptions
      ? sortedSubscriptions.active.map((entry) => subOption(entry, subscriptionsLabel))
      : []),
    ...(hasActiveInstallments
      ? sortedInstallments.active.map((entry) => instOption(entry, installmentsLabel))
      : []),
    ...(hasArchivedLinked
      ? [
          ...sortedSubscriptions.archived.map((entry) => subOption(entry, archivedGroupLabel)),
          ...sortedInstallments.archived.map((entry) => instOption(entry, archivedGroupLabel)),
        ]
      : []),
  ];

  return (
    <FormCombobox
      value={encodeValue(value)}
      onValueChange={(v) => onChange(decodeValue(v))}
      placeholder={t('form.linkedSubInstallment.placeholder')}
      options={options}
    />
  );
}

// Progress label matches the installments table convention: `name (paid/total)` where
// paid = current_installment - 1 (clamped to 0). Used for the row content, the trigger, and search.
function installmentLabel(inst: Installment): string {
  const paid = Math.max(0, inst.currentInstallment - 1);
  return `${inst.name} (${paid}/${inst.installmentsCount})`;
}
