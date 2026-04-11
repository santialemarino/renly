'use client';

import { TrendingUp, Wallet } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { Card } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import { LinkCard } from '@/components/link-card';
import { ROUTES } from '@/config/routes';
import type { DashboardOverview } from '@/lib/api/dashboard';
import { formatRatePct } from '@/lib/utils/format';

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

interface DashboardFooterProps {
  overview: DashboardOverview;
}

export function DashboardFooter({ overview }: DashboardFooterProps) {
  const t = useTranslations('dashboard');

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {/* Health indicators */}
      <Card compact>
        <span className="text-paragraph-sm text-muted-foreground">{t('health.savingsRate')}</span>
        <p className={cn('text-heading-3', savingsRateColor(overview.savingsRate))}>
          {overview.savingsRate !== null ? formatRatePct(overview.savingsRate) : '—'}
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
            ? `${overview.incomeExpenseRatio.toFixed(2)}x`
            : '—'}
        </p>
        <span className="text-paragraph-xs text-muted-foreground">
          {t('health.incomeExpenseRatioHint')}
        </span>
      </Card>

      {/* Detail dashboard links */}
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
  );
}
