'use client';

import { TrendingUp, Wallet } from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';

import { Card } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import { LinkCard } from '@/app/(protected)/dashboard/_components/link-card';
import { ROUTES } from '@/config/routes';
import type { DashboardLiquidity, DashboardOverview, LiquidityState } from '@/lib/api/dashboard';
import { INCOME_EXPENSE_RATIO_BREAKEVEN } from '@/lib/constants/health-thresholds';
import { formatRatePct, formatValue } from '@/lib/utils/format';
import { getLocaleTag } from '@/lib/utils/locale';

// Returns color class for savings rate, comparing the raw ratio (e.g. 0.20) against the user's
// healthy / moderate thresholds (stored as integer percents like 20 / 10).
function savingsRateColor(rate: number | null, healthyPct: number, moderatePct: number): string {
  if (rate === null) return 'text-muted-foreground';
  const ratePct = rate * 100;
  if (ratePct >= healthyPct) return 'text-emerald-600';
  if (ratePct >= moderatePct) return 'text-amber-500';
  return 'text-red-500';
}

// Returns color class for income/expense ratio against the user's healthy threshold + the
// hardcoded break-even point (mathematical constant — ratio of 1 means break-even).
function ratioColor(ratio: number | null, healthy: number): string {
  if (ratio === null) return 'text-muted-foreground';
  if (ratio >= healthy) return 'text-emerald-600';
  if (ratio >= INCOME_EXPENSE_RATIO_BREAKEVEN) return 'text-amber-500';
  return 'text-red-500';
}

// Returns color class for the liquidity state. Backend classifies; frontend maps to colour.
function liquidityColor(state: LiquidityState): string {
  if (state === 'healthy') return 'text-emerald-600';
  if (state === 'caution') return 'text-amber-500';
  if (state === 'at_risk') return 'text-red-500';
  return 'text-muted-foreground';
}

interface DashboardFooterProps {
  overview: DashboardOverview;
  liquidity: DashboardLiquidity;
  savingsRateHealthyPct: number;
  savingsRateModeratePct: number;
  incomeExpenseRatioHealthy: number;
}

export function DashboardFooter({
  overview,
  liquidity,
  savingsRateHealthyPct,
  savingsRateModeratePct,
  incomeExpenseRatioHealthy,
}: DashboardFooterProps) {
  const locale = useLocale();
  const t = useTranslations('dashboard');

  const ratioFormatter = new Intl.NumberFormat(getLocaleTag(locale), {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  const showWindowHint =
    liquidity.actualWindowDays > 0 && liquidity.actualWindowDays < liquidity.incomeWindowDays;
  const skippedCount = liquidity.skippedEntities.length;

  return (
    <div className="flex flex-col gap-y-4">
      {/* Health indicators row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Card compact>
          <span className="text-paragraph-sm text-muted-foreground">{t('health.savingsRate')}</span>
          <p
            className={cn(
              'text-heading-3',
              savingsRateColor(overview.savingsRate, savingsRateHealthyPct, savingsRateModeratePct),
            )}
          >
            {overview.savingsRate !== null ? formatRatePct(overview.savingsRate, locale) : '—'}
          </p>
          <span className="text-paragraph-xs text-muted-foreground">
            {t('health.savingsRateHint')}
          </span>
        </Card>

        <Card compact>
          <span className="text-paragraph-sm text-muted-foreground">
            {t('health.incomeExpenseRatio')}
          </span>
          <p
            className={cn(
              'text-heading-3',
              ratioColor(overview.incomeExpenseRatio, incomeExpenseRatioHealthy),
            )}
          >
            {overview.incomeExpenseRatio !== null
              ? `${ratioFormatter.format(overview.incomeExpenseRatio)}x`
              : '—'}
          </p>
          <span className="text-paragraph-xs text-muted-foreground">
            {t('health.incomeExpenseRatioHint')}
          </span>
        </Card>

        <Card compact>
          <span className="text-paragraph-sm text-muted-foreground">{t('health.liquidity')}</span>
          <p className={cn('text-heading-3', liquidityColor(liquidity.state))}>
            {liquidity.ratio !== null ? formatRatePct(liquidity.ratio, locale) : '—'}
          </p>
          {liquidity.ratio !== null ? (
            <>
              <span className="text-paragraph-xs text-muted-foreground">
                {t('health.liquidityBreakdown', {
                  commitments: formatValue(liquidity.fixedMonthlyCommitments, { locale }),
                  income: formatValue(liquidity.monthlyIncome, { locale }),
                })}
              </span>
              <span className="text-paragraph-mini text-muted-foreground">
                {t('health.liquidityThresholdHint', { pct: String(liquidity.threshold) })}
                {showWindowHint && (
                  <>
                    {' · '}
                    {t('health.liquidityActualDaysHint', {
                      days: String(liquidity.actualWindowDays),
                    })}
                  </>
                )}
                {skippedCount > 0 && (
                  <>
                    {' · '}
                    {t('health.liquiditySkippedHint', { count: skippedCount })}
                  </>
                )}
              </span>
            </>
          ) : (
            <span className="text-paragraph-xs text-muted-foreground">
              {liquidity.monthlyIncome === 0 && liquidity.actualWindowDays === 0
                ? t('health.liquidityZeroIncomeHint')
                : t('health.liquidityHint')}
            </span>
          )}
        </Card>
      </div>

      {/* Detail dashboard links */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <LinkCard
          href={ROUTES.financeDashboard}
          icon={Wallet}
          label={t('links.finances')}
          hint={t('links.financesHint')}
        />

        <LinkCard
          href={ROUTES.investorDashboard}
          icon={TrendingUp}
          label={t('links.investments')}
          hint={t('links.investmentsHint')}
        />
      </div>
    </div>
  );
}
