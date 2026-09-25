'use client';

import { useRouter } from 'next/navigation';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslations } from 'next-intl';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';

import { Button, Hint, Separator } from '@repo/ui/components';
import { saveAlerts } from '@/app/(protected)/alerts/alerts-actions';
import {
  buildAlertsFormSchema,
  type AlertsFormValues,
} from '@/app/(protected)/alerts/alerts-form-schema';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { IntegerInput } from '@/components/integer-input';
import { LocaleAmountInput } from '@/components/locale-amount-input';
import { InfoHint } from '@/components/styled-hint';
import type { SettingsData } from '@/lib/api/settings';
import {
  COLLECTION_WARNING_PCT_RANGE,
  ENV_COLLECTION_WARNING_PCT,
  ENV_MAX_COLLECTIONS,
  MAX_COLLECTIONS_RANGE,
} from '@/lib/constants/collections';
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
    maxCollectionsInvalidMsg: t('form.maxCollections.invalidRange', {
      min: MAX_COLLECTIONS_RANGE[0],
      max: MAX_COLLECTIONS_RANGE[1],
    }),
    collectionWarningPctInvalidMsg: t('form.collectionWarningPct.invalidRange', {
      min: COLLECTION_WARNING_PCT_RANGE[0],
      max: COLLECTION_WARNING_PCT_RANGE[1],
    }),
    liquidityThresholdInvalidMsg: t('form.liquidityThreshold.invalidRange'),
    savingsRateInvalidMsg: t('form.savingsRate.invalidRange'),
    incomeExpenseRatioInvalidMsg: t('form.incomeExpenseRatio.invalidRange'),
  });

  const form = useForm<AlertsFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      maxCollections: initialSettings.maxCollections?.toString() ?? '',
      collectionWarningPct: initialSettings.collectionWarningPct?.toString() ?? '',
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
        maxCollections: toIntOrNull(values.maxCollections),
        collectionWarningPct: toIntOrNull(values.collectionWarningPct),
        liquidityThresholdPct: toIntOrNull(values.liquidityThresholdPct),
        savingsRateHealthyPct: toIntOrNull(values.savingsRateHealthyPct),
        savingsRateModeratePct: toIntOrNull(values.savingsRateModeratePct),
        incomeExpenseRatioHealthy: toFloatOrNull(values.incomeExpenseRatioHealthy),
      });

      form.reset(values);
      router.refresh();
      toast.success(t('form.saveSuccess'), { id: 'alerts-save' });
    } catch {
      toast.error(t('form.saveError'), { id: 'alerts-save' });
    }
  }

  return (
    <Form {...form}>
      <form
        noValidate
        onSubmit={form.handleSubmit(onSubmit)}
        className="flex flex-col w-full gap-y-6 lg:gap-y-10"
      >
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-12 gap-y-8">
          {/* Left column — Account limits */}
          <div className="flex flex-col max-w-md gap-y-3">
            <h3 className="text-paragraph-sm-semibold text-muted-foreground">
              {t('form.sectionAccountLimits')}
            </h3>

            <FormField
              control={form.control}
              name="maxCollections"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t('form.maxCollections.label')}</FormLabel>
                  <Hint>{t('form.maxCollections.hint')}</Hint>
                  <FormControl>
                    <IntegerInput {...field} surface placeholder={String(ENV_MAX_COLLECTIONS)} />
                  </FormControl>
                  <FormMessage />
                  <InfoHint>
                    {t('form.maxCollections.default', { value: String(ENV_MAX_COLLECTIONS) })}
                  </InfoHint>
                </FormItem>
              )}
            />

            <Separator />

            <FormField
              control={form.control}
              name="collectionWarningPct"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t('form.collectionWarningPct.label')}</FormLabel>
                  <Hint>{t('form.collectionWarningPct.hint')}</Hint>
                  <FormControl>
                    <IntegerInput
                      {...field}
                      surface
                      placeholder={
                        ENV_COLLECTION_WARNING_PCT != null
                          ? String(ENV_COLLECTION_WARNING_PCT)
                          : undefined
                      }
                    />
                  </FormControl>
                  <FormMessage />
                  <InfoHint>
                    {ENV_COLLECTION_WARNING_PCT != null
                      ? t('form.collectionWarningPct.default', {
                          value: String(ENV_COLLECTION_WARNING_PCT),
                        })
                      : t('form.collectionWarningPct.noDefault')}
                  </InfoHint>
                </FormItem>
              )}
            />
          </div>

          {/* Right column — Financial health */}
          <div className="flex flex-col max-w-md gap-y-3">
            <h3 className="text-paragraph-sm-semibold text-muted-foreground">
              {t('form.sectionFinancialHealth')}
            </h3>

            <FormField
              control={form.control}
              name="liquidityThresholdPct"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t('form.liquidityThreshold.label')}</FormLabel>
                  <Hint>{t('form.liquidityThreshold.hint')}</Hint>
                  <FormControl>
                    <IntegerInput
                      {...field}
                      surface
                      placeholder={String(ENV_LIQUIDITY_THRESHOLD_PCT)}
                    />
                  </FormControl>
                  <FormMessage />
                  <InfoHint>
                    {t('form.liquidityThreshold.default', {
                      value: String(ENV_LIQUIDITY_THRESHOLD_PCT),
                    })}
                  </InfoHint>
                </FormItem>
              )}
            />

            <Separator />

            <FormField
              control={form.control}
              name="savingsRateHealthyPct"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t('form.savingsRateHealthy.label')}</FormLabel>
                  <Hint>{t('form.savingsRateHealthy.hint')}</Hint>
                  <FormControl>
                    <IntegerInput
                      {...field}
                      surface
                      placeholder={String(ENV_SAVINGS_RATE_HEALTHY_PCT)}
                    />
                  </FormControl>
                  <FormMessage />
                  <InfoHint>
                    {t('form.savingsRateHealthy.default', {
                      value: String(ENV_SAVINGS_RATE_HEALTHY_PCT),
                    })}
                  </InfoHint>
                </FormItem>
              )}
            />

            <Separator />

            <FormField
              control={form.control}
              name="savingsRateModeratePct"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t('form.savingsRateModerate.label')}</FormLabel>
                  <Hint>{t('form.savingsRateModerate.hint')}</Hint>
                  <FormControl>
                    <IntegerInput
                      {...field}
                      surface
                      placeholder={String(ENV_SAVINGS_RATE_MODERATE_PCT)}
                    />
                  </FormControl>
                  <FormMessage />
                  <InfoHint>
                    {t('form.savingsRateModerate.default', {
                      value: String(ENV_SAVINGS_RATE_MODERATE_PCT),
                    })}
                  </InfoHint>
                </FormItem>
              )}
            />

            <Separator />

            <FormField
              control={form.control}
              name="incomeExpenseRatioHealthy"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t('form.incomeExpenseRatio.label')}</FormLabel>
                  <Hint>{t('form.incomeExpenseRatio.hint')}</Hint>
                  <FormControl>
                    <LocaleAmountInput
                      {...field}
                      maxDecimals={2}
                      placeholder={String(ENV_INCOME_EXPENSE_RATIO_HEALTHY)}
                    />
                  </FormControl>
                  <FormMessage />
                  <InfoHint>
                    {t('form.incomeExpenseRatio.default', {
                      value: String(ENV_INCOME_EXPENSE_RATIO_HEALTHY),
                    })}
                  </InfoHint>
                </FormItem>
              )}
            />
          </div>
        </div>

        <Button
          blue
          type="submit"
          className="w-full max-w-md lg:max-w-full"
          disabled={form.formState.isSubmitting}
        >
          {form.formState.isSubmitting ? t('form.cta.loading') : t('form.cta.label')}
        </Button>
      </form>
    </Form>
  );
}
