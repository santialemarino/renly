'use client';

import { TrendingUp, Wallet } from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';

import { Card } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import { LinkCard } from '@/components/link-card';
import { ROUTES } from '@/config/routes';
import type { DashboardLiquidity, DashboardOverview, LiquidityState } from '@/lib/api/dashboard';
import { formatRatePct, formatValue } from '@/lib/utils/format';
import { getLocaleTag } from '@/lib/utils/locale';

const SAVINGS_RATE_HEALTHY = 0.2;
const SAVINGS_RATE_MODERATE = 0.1;
const INCOME_EXPENSE_RATIO_HEALTHY = 1.5;

// Returns color class for savings rate thresholds.
function savingsRateColor(rate: number | null): string {
  if (rate === null) return 'text-muted-foreground';
  if (rate >= SAVINGS_RATE_HEALTHY) return 'text-emerald-600';
  if (rate >= SAVINGS_RATE_MODERATE) return 'text-amber-500';
  return 'text-red-500';
}

// Returns color class for income/expense ratio thresholds.
function ratioColor(ratio: number | null): string {
  if (ratio === null) return 'text-muted-foreground';
  if (ratio >= INCOME_EXPENSE_RATIO_HEALTHY) return 'text-emerald-600';
  if (ratio >= 1) return 'text-amber-500';
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
}

export function DashboardFooter({ overview, liquidity }: DashboardFooterProps) {
  const locale = useLocale();
  const t = useTranslations('dashboard');

  const ratioFormatter = new Intl.NumberFormat(getLocaleTag(locale), {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  const showWindowHint =
    liquidity.actualWindowDays > 0 && liquidity.actualWindowDays < liquidity.incomeWindowDays;

  return (
    <div className="flex flex-col gap-y-4">
      {/* Health indicators row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Card compact>
          <span className="text-paragraph-sm text-muted-foreground">{t('health.savingsRate')}</span>
          <p className={cn('text-heading-3', savingsRateColor(overview.savingsRate))}>
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
          <p className={cn('text-heading-3', ratioColor(overview.incomeExpenseRatio))}>
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
