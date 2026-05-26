'use client';

import { useRouter } from 'next/navigation';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslations } from 'next-intl';
import { Controller, useForm } from 'react-hook-form';
import { toast } from 'sonner';

import { Button, Hint, Label, Separator } from '@repo/ui/components';
import { saveAlerts } from '@/app/(protected)/alerts/alerts-actions';
import {
  buildAlertsFormSchema,
  type AlertsFormValues,
} from '@/app/(protected)/alerts/alerts-form-schema';
import { IntegerInput } from '@/components/integer-input';
import { LocaleAmountInput } from '@/components/locale-amount-input';
import { InfoHint } from '@/components/styled-hint';
import type { SettingsData } from '@/lib/api/settings';
import { ENV_GROUP_WARNING_PCT, ENV_MAX_GROUPS } from '@/lib/constants/groups';
import {
  ENV_INCOME_EXPENSE_RATIO_HEALTHY,
  ENV_SAVINGS_RATE_HEALTHY_PCT,
  ENV_SAVINGS_RATE_MODERATE_PCT,
} from '@/lib/constants/health-thresholds';
import { ENV_LIQUIDITY_THRESHOLD_PCT } from '@/lib/constants/liquidity';

interface AlertsFormProps {
  initialSettings: SettingsData;
}

export function AlertsForm({ initialSettings }: AlertsFormProps) {
  const t = useTranslations('alerts');

  const router = useRouter();

  const schema = buildAlertsFormSchema({
    maxGroupsInvalidMsg: t('form.maxGroups.invalidRange'),
    groupWarningPctInvalidMsg: t('form.groupWarningPct.invalidRange'),
    liquidityThresholdInvalidMsg: t('form.liquidityThreshold.invalidRange'),
    savingsRateInvalidMsg: t('form.savingsRate.invalidRange'),
    incomeExpenseRatioInvalidMsg: t('form.incomeExpenseRatio.invalidRange'),
  });

  const {
    control,
    handleSubmit,
    reset,
    formState: { isSubmitting },
  } = useForm<AlertsFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      maxGroups: initialSettings.maxGroups?.toString() ?? '',
      groupWarningPct: initialSettings.groupWarningPct?.toString() ?? '',
      liquidityThresholdPct: initialSettings.liquidityThresholdPct?.toString() ?? '',
      savingsRateHealthyPct: initialSettings.savingsRateHealthyPct?.toString() ?? '',
      savingsRateModeratePct: initialSettings.savingsRateModeratePct?.toString() ?? '',
      incomeExpenseRatioHealthy: initialSettings.incomeExpenseRatioHealthy?.toString() ?? '',
    },
  });

  async function onSubmit(values: AlertsFormValues) {
    try {
      const toIntOrNull = (raw?: string): number | null => {
        if (!raw) return null;
        const n = parseInt(raw, 10);
        return Number.isNaN(n) ? null : n;
      };
      const toFloatOrNull = (raw?: string): number | null => {
        if (!raw) return null;
        const n = Number(raw);
        return Number.isNaN(n) ? null : n;
      };

      await saveAlerts({
        maxGroups: toIntOrNull(values.maxGroups),
        groupWarningPct: toIntOrNull(values.groupWarningPct),
        liquidityThresholdPct: toIntOrNull(values.liquidityThresholdPct),
        savingsRateHealthyPct: toIntOrNull(values.savingsRateHealthyPct),
        savingsRateModeratePct: toIntOrNull(values.savingsRateModeratePct),
        incomeExpenseRatioHealthy: toFloatOrNull(values.incomeExpenseRatioHealthy),
      });

      reset(values);
      router.refresh();
      toast.success(t('form.saveSuccess'), { id: 'alerts-save' });
    } catch {
      toast.error(t('form.saveError'), { id: 'alerts-save' });
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col w-full gap-y-6 lg:gap-y-10">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-12 gap-y-8">
        {/* Left column — Account limits */}
        <div className="flex flex-col max-w-md gap-y-3">
          <h3 className="text-paragraph-sm-semibold text-muted-foreground">
            {t('form.sectionAccountLimits')}
          </h3>

          <div className="flex flex-col gap-y-2">
            <Label>{t('form.maxGroups.label')}</Label>
            <Hint>{t('form.maxGroups.hint')}</Hint>
            <Controller
              name="maxGroups"
              control={control}
              render={({ field }) => (
                <IntegerInput {...field} surface placeholder={String(ENV_MAX_GROUPS)} />
              )}
            />
            <InfoHint>{t('form.maxGroups.default', { value: String(ENV_MAX_GROUPS) })}</InfoHint>
          </div>

          <Separator />

          <div className="flex flex-col gap-y-2">
            <Label>{t('form.groupWarningPct.label')}</Label>
            <Hint>{t('form.groupWarningPct.hint')}</Hint>
            <Controller
              name="groupWarningPct"
              control={control}
              render={({ field }) => (
                <IntegerInput
                  {...field}
                  surface
                  placeholder={
                    ENV_GROUP_WARNING_PCT != null ? String(ENV_GROUP_WARNING_PCT) : undefined
                  }
                />
              )}
            />
            <InfoHint>
              {ENV_GROUP_WARNING_PCT != null
                ? t('form.groupWarningPct.default', { value: String(ENV_GROUP_WARNING_PCT) })
                : t('form.groupWarningPct.noDefault')}
            </InfoHint>
          </div>
        </div>

        {/* Right column — Financial health */}
        <div className="flex flex-col max-w-md gap-y-3">
          <h3 className="text-paragraph-sm-semibold text-muted-foreground">
            {t('form.sectionFinancialHealth')}
          </h3>

          <div className="flex flex-col gap-y-2">
            <Label>{t('form.liquidityThreshold.label')}</Label>
            <Hint>{t('form.liquidityThreshold.hint')}</Hint>
            <Controller
              name="liquidityThresholdPct"
              control={control}
              render={({ field }) => (
                <IntegerInput
                  {...field}
                  surface
                  placeholder={String(ENV_LIQUIDITY_THRESHOLD_PCT)}
                />
              )}
            />
            <InfoHint>
              {t('form.liquidityThreshold.default', {
                value: String(ENV_LIQUIDITY_THRESHOLD_PCT),
              })}
            </InfoHint>
          </div>

          <Separator />

          <div className="flex flex-col gap-y-2">
            <Label>{t('form.savingsRateHealthy.label')}</Label>
            <Hint>{t('form.savingsRateHealthy.hint')}</Hint>
            <Controller
              name="savingsRateHealthyPct"
              control={control}
              render={({ field }) => (
                <IntegerInput
                  {...field}
                  surface
                  placeholder={String(ENV_SAVINGS_RATE_HEALTHY_PCT)}
                />
              )}
            />
            <InfoHint>
              {t('form.savingsRateHealthy.default', {
                value: String(ENV_SAVINGS_RATE_HEALTHY_PCT),
              })}
            </InfoHint>
          </div>

          <Separator />

          <div className="flex flex-col gap-y-2">
            <Label>{t('form.savingsRateModerate.label')}</Label>
            <Hint>{t('form.savingsRateModerate.hint')}</Hint>
            <Controller
              name="savingsRateModeratePct"
              control={control}
              render={({ field }) => (
                <IntegerInput
                  {...field}
                  surface
                  placeholder={String(ENV_SAVINGS_RATE_MODERATE_PCT)}
                />
              )}
            />
            <InfoHint>
              {t('form.savingsRateModerate.default', {
                value: String(ENV_SAVINGS_RATE_MODERATE_PCT),
              })}
            </InfoHint>
          </div>

          <Separator />

          <div className="flex flex-col gap-y-2">
            <Label>{t('form.incomeExpenseRatio.label')}</Label>
            <Hint>{t('form.incomeExpenseRatio.hint')}</Hint>
            <Controller
              name="incomeExpenseRatioHealthy"
              control={control}
              render={({ field }) => (
                <LocaleAmountInput
                  {...field}
                  maxDecimals={2}
                  placeholder={String(ENV_INCOME_EXPENSE_RATIO_HEALTHY)}
                />
              )}
            />
            <InfoHint>
              {t('form.incomeExpenseRatio.default', {
                value: String(ENV_INCOME_EXPENSE_RATIO_HEALTHY),
              })}
            </InfoHint>
          </div>
        </div>
      </div>

      <Button blue type="submit" className="w-full max-w-md lg:max-w-full" disabled={isSubmitting}>
        {isSubmitting ? t('form.cta.loading') : t('form.cta.label')}
      </Button>
    </form>
  );
}
