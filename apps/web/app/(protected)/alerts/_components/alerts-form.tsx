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
import { InfoHint } from '@/components/styled-hint';
import type { SettingsData } from '@/lib/api/settings';
import { ENV_GROUP_WARNING_PCT, ENV_MAX_GROUPS } from '@/lib/constants/groups';
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
    },
  });

  async function onSubmit(values: AlertsFormValues) {
    try {
      const maxGroupsNum = values.maxGroups ? parseInt(values.maxGroups, 10) : null;
      const warningPctNum = values.groupWarningPct ? parseInt(values.groupWarningPct, 10) : null;
      const liquidityNum = values.liquidityThresholdPct
        ? parseInt(values.liquidityThresholdPct, 10)
        : null;

      await saveAlerts({
        maxGroups: !isNaN(maxGroupsNum!) ? maxGroupsNum : null,
        groupWarningPct: !isNaN(warningPctNum!) ? warningPctNum : null,
        liquidityThresholdPct: !isNaN(liquidityNum!) ? liquidityNum : null,
      });

      reset({
        maxGroups: maxGroupsNum?.toString() ?? '',
        groupWarningPct: warningPctNum?.toString() ?? '',
        liquidityThresholdPct: liquidityNum?.toString() ?? '',
      });
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
        </div>
      </div>

      <Button blue type="submit" className="w-full max-w-md lg:max-w-full" disabled={isSubmitting}>
        {isSubmitting ? t('form.cta.loading') : t('form.cta.label')}
      </Button>
    </form>
  );
}
