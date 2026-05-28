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
import type { Installment } from '@/lib/api/installments';
import type { Subscription } from '@/lib/api/subscriptions';
import { formatDateForLocale } from '@/lib/utils/format';

// "Linked to subscription / installment" dropdown on the expense form (Phase 3, follow-up 3a).
// One combined dropdown with two SelectGroups (Subscriptions + Installments). Sibling of
// LinkedObligationSelect — mutual exclusivity across the three FKs is enforced one level up
// by the form. Tri-state match model mirrors LinkedObligationSelect:
//   - 'match'    : every comparable plan field is filled on the form AND equals (green dot).
//   - 'mismatch' : at least one filled-on-both-sides field disagrees (no dot, warning fires).
//   - 'unknown'  : a form field needed for comparison is empty (no dot, no warning).
// The 'unknown' state avoids prematurely showing the green dot when the user has only
// filled half the form. In CREATE mode the dot stays visible (no disabled-mode here —
// Mark Paid prefill never opens this dropdown, see ExpenseFormDialog).

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

// SelectItem values are prefixed so a single dropdown can encode both entity types
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

// Synthetic "next cycle date" for installments: start_date + (current_installment - 1) months.
// Drift on anchor-day-31 short-month clamping doesn't matter for sort ordering — the items
// still land in roughly-correct calendar order. Returns a YYYY-MM-DD string so it compares
// directly against subscription.nextBillingDate via localeCompare.
function installmentNextChargeDate(installment: Installment): string {
  const start = new Date(installment.startDate + 'T00:00:00Z');
  start.setUTCMonth(start.getUTCMonth() + (installment.currentInstallment - 1));
  return start.toISOString().slice(0, 10);
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

  // Sort within each group: match -> unknown -> mismatch, then next-cycle-date ASC.
  // Two separate sorted lists rather than one merged list — the SelectGroups stay
  // visually distinct (Subscriptions / Installments) so cross-group sorting would
  // muddle the grouping.
  const sortedSubscriptions = useMemo(() => {
    const withStatus = subscriptions.map((s) => ({
      sub: s,
      status: planMatchStatus(s, formCurrency, formPaymentMethod, formCreditCardId),
    }));
    withStatus.sort((a, b) => {
      const rankDiff = STATUS_RANK[a.status] - STATUS_RANK[b.status];
      if (rankDiff !== 0) return rankDiff;
      return a.sub.nextBillingDate.localeCompare(b.sub.nextBillingDate);
    });
    return withStatus;
  }, [subscriptions, formCurrency, formPaymentMethod, formCreditCardId]);

  const sortedInstallments = useMemo(() => {
    const withStatus = installments.map((i) => ({
      inst: i,
      status: planMatchStatus(i, formCurrency, formPaymentMethod, formCreditCardId),
      nextChargeDate: installmentNextChargeDate(i),
    }));
    withStatus.sort((a, b) => {
      const rankDiff = STATUS_RANK[a.status] - STATUS_RANK[b.status];
      if (rankDiff !== 0) return rankDiff;
      return a.nextChargeDate.localeCompare(b.nextChargeDate);
    });
    return withStatus;
  }, [installments, formCurrency, formPaymentMethod, formCreditCardId]);

  const hasSubscriptions = sortedSubscriptions.length > 0;
  const hasInstallments = sortedInstallments.length > 0;

  return (
    <Select value={encodeValue(value)} onValueChange={(v) => onChange(decodeValue(v))}>
      <SelectTrigger className="w-full">
        <SelectValue placeholder={t('form.linkedSubInstallment.placeholder')} />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={NONE_VALUE}>{t('form.linkedSubInstallment.none')}</SelectItem>
        {hasSubscriptions && (
          <SelectGroup>
            <SelectLabel>{t('form.linkedSubInstallment.subscriptionsLabel')}</SelectLabel>
            {sortedSubscriptions.map(({ sub, status }) => {
              const isSelected =
                value !== null && value.kind === 'subscription' && value.id === sub.id;
              return (
                <SelectItem key={`sub-${sub.id}`} value={`sub:${sub.id}`}>
                  <div className="flex min-w-0 items-center gap-x-2">
                    <CircleDot
                      className={cn(
                        'size-3 shrink-0 transition-colors',
                        dotColorClass(status, isSelected),
                      )}
                      aria-hidden
                    />
                    <span className="truncate">{sub.name}</span>
                    {/* Next-cycle date in a muted sub-label so the user can see what
                        they're linking against (Phase 3, follow-up Item 8.1). */}
                    <span className="text-paragraph-xs text-muted-foreground">
                      {t('form.linkedSubInstallment.nextCycleHint', {
                        date: formatDateForLocale(sub.nextBillingDate, locale),
                      })}
                    </span>
                  </div>
                </SelectItem>
              );
            })}
          </SelectGroup>
        )}
        {hasInstallments && (
          <SelectGroup>
            <SelectLabel>{t('form.linkedSubInstallment.installmentsLabel')}</SelectLabel>
            {sortedInstallments.map(({ inst, status, nextChargeDate }) => {
              const isSelected =
                value !== null && value.kind === 'installment' && value.id === inst.id;
              // Progress label matches the installments table convention:
              // `paid / total` where paid = current_installment - 1 (clamped to 0).
              // So "0/10" = none paid yet; "10/10" = fully paid.
              const paid = Math.max(0, inst.currentInstallment - 1);
              return (
                <SelectItem key={`inst-${inst.id}`} value={`inst:${inst.id}`}>
                  <div className="flex min-w-0 items-center gap-x-2">
                    <CircleDot
                      className={cn(
                        'size-3 shrink-0 transition-colors',
                        dotColorClass(status, isSelected),
                      )}
                      aria-hidden
                    />
                    <span className="truncate">
                      {inst.name} ({paid}/{inst.installmentsCount})
                    </span>
                    {/* Next-cuota date in a muted sub-label (Phase 3, follow-up Item 8.1). */}
                    <span className="text-paragraph-xs text-muted-foreground">
                      {t('form.linkedSubInstallment.nextCycleHint', {
                        date: formatDateForLocale(nextChargeDate, locale),
                      })}
                    </span>
                  </div>
                </SelectItem>
              );
            })}
          </SelectGroup>
        )}
      </SelectContent>
    </Select>
  );
}
