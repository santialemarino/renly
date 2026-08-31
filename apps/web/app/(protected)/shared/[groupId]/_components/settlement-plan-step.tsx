'use client';

import { useTranslations } from 'next-intl';

import { Checkbox } from '@repo/ui/components';
import { WizardConfirmRow } from '@/app/(protected)/shared/_components/wizard-shell';
import {
  bucketOutOfReach,
  bucketPartlyCleared,
  plannedRows,
} from '@/app/(protected)/shared/settlement-rules';
import type { GroupSettlementPlan } from '@/lib/api/group-settlements';
import { useFormatters } from '@/lib/i18n/formatters';

interface SettlementPlanStepProps {
  plan: GroupSettlementPlan;
  // Toggling re-asks the server for a plan over the smaller set rather than recomputing here: which
  // bucket a partial excess fills, and what it costs, are the server's answers and only its answers.
  onToggle: (currency: string, selected: boolean) => void;
  pending: boolean;
}

/*
 * What a payment bigger than its own bucket would do, before it does it.
 *
 * §5's rule is that a cross-currency cascade is never silent, and this is the whole of what that means
 * in the surface: the payer sees which balances the extra reaches, what it costs in the currency they
 * are actually paying, and what is left over — and confirms it, or unticks a bucket and sees the plan
 * again.
 *
 * Every figure here comes from the server. Unticking sends the smaller set back and renders whatever
 * comes returns; nothing is recomputed locally, because the excess re-flows when a bucket leaves the
 * set and a client that predicted the new plan would be a second implementation of the allocation.
 *
 * Two currencies live in each row and they are never mixed: the balance being cleared is in ITS OWN
 * currency, and what it costs is in the one being paid. Both name their currency for that reason.
 */
export function SettlementPlanStep({ plan, onToggle, pending }: SettlementPlanStepProps) {
  const t = useTranslations('shared');
  const fmt = useFormatters();

  const rows = plannedRows(plan);

  return (
    <div className="flex flex-col min-w-0 gap-y-4">
      <p className="text-paragraph-sm text-muted-foreground">
        {t('settlements.plan.intro', {
          excess: fmt.amount(plan.excess, plan.currency),
          currency: plan.currency,
        })}
      </p>

      <ul className="flex flex-col gap-y-1">
        {plan.buckets.map((bucket) => (
          <li key={bucket.currency}>
            <label
              className={`flex items-start p-3 gap-x-3 border border-border rounded-1.5xl transition-colors ${
                pending ? 'opacity-60' : 'hover:bg-muted/40'
              }`}
            >
              <Checkbox
                checked={bucket.selected}
                onCheckedChange={(checked) => onToggle(bucket.currency, checked === true)}
                disabled={pending}
                className="mt-0.5"
              />
              <span className="flex flex-col min-w-0 gap-y-0.5">
                <span className="text-paragraph-sm-medium text-foreground">
                  {t('settlements.plan.owed', {
                    amount: fmt.amount(bucket.outstanding, bucket.currency),
                    currency: bucket.currency,
                  })}
                </span>
                {/*
                 * Three states, and each is a different fact rather than a variation in wording: it
                 * clears entirely, it clears partly because the excess ran out inside it, or it was
                 * offered and never reached. Leaving the last one blank reads as a bug.
                 */}
                <span className="text-paragraph-xs text-muted-foreground">
                  {!bucket.selected
                    ? t('settlements.plan.skipped')
                    : bucketOutOfReach(bucket)
                      ? t('settlements.plan.outOfReach', {
                          cost: fmt.amount(bucket.cost, plan.currency),
                          currency: plan.currency,
                        })
                      : bucketPartlyCleared(bucket)
                        ? t('settlements.plan.partly', {
                            amount: fmt.amount(bucket.amount, bucket.currency),
                            bucketCurrency: bucket.currency,
                            cost: fmt.amount(bucket.appliedCost, plan.currency),
                            currency: plan.currency,
                          })
                        : t('settlements.plan.clears', {
                            cost: fmt.amount(bucket.appliedCost, plan.currency),
                            currency: plan.currency,
                          })}
                </span>
              </span>
            </label>
          </li>
        ))}
      </ul>

      {/*
       * The rows that will actually be written, named one by one. A payment that becomes several
       * settlements is surprising enough that saying so beforehand is the honest thing — and these
       * figures are read from the plan, never re-derived, so what is confirmed is what is recorded.
       */}
      <dl className="flex flex-col p-4 gap-y-3 bg-muted/30 border border-border rounded-1.5xl">
        <p className="text-paragraph-xs-medium uppercase tracking-wide text-muted-foreground">
          {t('settlements.plan.willRecord', { count: rows.length })}
        </p>
        {rows.map((row) => (
          <WizardConfirmRow
            key={row.currency}
            label={t('settlements.plan.rowLabel', { currency: row.currency })}
            value={`${fmt.amount(row.amount, row.currency)} ${row.currency}`}
          />
        ))}
      </dl>

      {/*
       * A leftover is a credit, not an error: money handed over that no ticked balance absorbed. It
       * flips the bucket being paid, so the payee ends up owing it — which is worth a sentence,
       * because it is the one outcome somebody would not expect from paying a debt.
       */}
      {Number(plan.leftover) > 0 && (
        <p className="text-paragraph-sm text-amber-600">
          {t('settlements.plan.leftover', {
            amount: fmt.amount(plan.leftover, plan.currency),
            currency: plan.currency,
          })}
        </p>
      )}

      {plan.skippedCurrencies.length > 0 && (
        <p className="text-paragraph-sm text-muted-foreground">
          {t('settlements.plan.skippedCurrencies', {
            currencies: fmt.list(plan.skippedCurrencies),
          })}
        </p>
      )}
    </div>
  );
}
