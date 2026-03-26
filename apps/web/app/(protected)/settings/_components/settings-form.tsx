'use client';

import { useRouter } from 'next/navigation';
import { zodResolver } from '@hookform/resolvers/zod';
import { AlertTriangle } from 'lucide-react';
import { AnimatePresence, motion } from 'motion/react';
import { useTranslations } from 'next-intl';
import { Controller, useForm } from 'react-hook-form';
import { toast } from 'sonner';

import { Button, Hint, Input, Label, Separator } from '@repo/ui/components';
import { CurrencyCombobox } from '@/app/(protected)/_components/currency-combobox';
import { saveSettings } from '@/app/(protected)/settings/settings-actions';
import {
  buildSettingsFormSchema,
  type SettingsFormValues,
} from '@/app/(protected)/settings/settings-form-schema';
import { InfoHint, WarningHint } from '@/components/styled-hint';
import type { SettingsData } from '@/lib/api/settings';
import { ANIMATION_DEFAULT } from '@/lib/constants/animations';
import { PERIOD_PRESETS } from '@/lib/constants/period-presets';
import { isCurrencySupported } from '@/lib/utils/currency';

// Localizes a canonical preset code (e.g. "1Y") for display using the year suffix from translations.
function localizePreset(code: string | undefined, yearSuffix: string): string {
  if (!code) return '';
  return code.replace(/Y$/i, yearSuffix);
}

interface SettingsFormProps {
  initialSettings: SettingsData;
}

const fallbackPrimary = process.env.NEXT_PUBLIC_FALLBACK_PRIMARY_CURRENCY ?? 'ARS';
const fallbackSecondary = process.env.NEXT_PUBLIC_FALLBACK_SECONDARY_CURRENCY ?? 'USD';

export function SettingsForm({ initialSettings }: SettingsFormProps) {
  const t = useTranslations('settings');
  const tCommon = useTranslations('common');
  const router = useRouter();

  const yearSuffix = tCommon('period.yearSuffix');
  const schema = buildSettingsFormSchema(t('form.periodPresets.invalidFormat'));

  const {
    control,
    handleSubmit,
    watch,
    reset,
    formState: { isSubmitting, errors },
  } = useForm<SettingsFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      primaryCurrency: initialSettings.primaryCurrency ?? fallbackPrimary,
      secondaryCurrency: initialSettings.secondaryCurrency ?? fallbackSecondary,
      periodPreset1: localizePreset(initialSettings.periodPresets?.[0], yearSuffix),
      periodPreset2: localizePreset(initialSettings.periodPresets?.[1], yearSuffix),
      periodPreset3: localizePreset(initialSettings.periodPresets?.[2], yearSuffix),
      periodPreset4: localizePreset(initialSettings.periodPresets?.[3], yearSuffix),
    },
  });

  const primaryCurrency = watch('primaryCurrency');
  const secondaryCurrency = watch('secondaryCurrency');

  const primaryUnsupported = primaryCurrency && !isCurrencySupported(primaryCurrency);
  const secondaryUnsupported = secondaryCurrency && !isCurrencySupported(secondaryCurrency);

  function handleCurrencyChange(value: string | null, onChange: (v: string | null) => void) {
    onChange(value);
    if (value && !isCurrencySupported(value)) {
      toast.warning(tCommon('currency.unsupportedSelect', { currency: value }));
    }
  }

  async function onSubmit(values: SettingsFormValues) {
    try {
      const presets = [
        values.periodPreset1,
        values.periodPreset2,
        values.periodPreset3,
        values.periodPreset4,
      ]
        .filter((v): v is string => !!v)
        .map((v) => v.toUpperCase().replace(/A$/, 'Y'));
      await saveSettings(
        values.primaryCurrency,
        values.secondaryCurrency ?? null,
        presets.length > 0 ? presets : null,
      );
      // Reset form with localized canonical values so inputs update immediately.
      reset({
        primaryCurrency: values.primaryCurrency,
        secondaryCurrency: values.secondaryCurrency,
        periodPreset1: localizePreset(presets[0], yearSuffix),
        periodPreset2: localizePreset(presets[1], yearSuffix),
        periodPreset3: localizePreset(presets[2], yearSuffix),
        periodPreset4: localizePreset(presets[3], yearSuffix),
      });
      router.refresh();
      toast.success(t('form.saveSuccess'), { id: 'settings-save' });
    } catch {
      toast.error(t('form.saveError'), { id: 'settings-save' });
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col w-full max-w-md gap-y-6">
      <div className="flex flex-col gap-y-2">
        <div className="flex items-center gap-x-2">
          <Label>{t('form.primaryCurrency.label')}</Label>
          <AnimatePresence>
            {primaryUnsupported && (
              <motion.div
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.8 }}
                transition={{ duration: ANIMATION_DEFAULT }}
              >
                <AlertTriangle className="size-4 text-amber-500" />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
        <Hint>{t('form.primaryCurrency.hint')}</Hint>
        <Controller
          name="primaryCurrency"
          control={control}
          render={({ field }) => (
            <CurrencyCombobox
              value={field.value ?? null}
              exclude={secondaryCurrency ? [secondaryCurrency] : []}
              placeholder={t('form.primaryCurrency.placeholder')}
              searchPlaceholder={t('form.searchPlaceholder')}
              noResults={t('form.noResults')}
              surface
              onChange={(v) => handleCurrencyChange(v ?? '', (val) => field.onChange(val ?? ''))}
            />
          )}
        />
      </div>

      <Separator />

      <div className="flex flex-col gap-y-2">
        <div className="flex items-center gap-x-2">
          <Label>{t('form.secondaryCurrency.label')}</Label>
          <AnimatePresence>
            {secondaryUnsupported && (
              <motion.div
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.8 }}
                transition={{ duration: ANIMATION_DEFAULT }}
              >
                <AlertTriangle className="size-4 text-amber-500" />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
        <Hint>{t('form.secondaryCurrency.hint')}</Hint>
        <Controller
          name="secondaryCurrency"
          control={control}
          render={({ field }) => (
            <CurrencyCombobox
              value={field.value ?? null}
              exclude={primaryCurrency ? [primaryCurrency] : []}
              placeholder={t('form.secondaryCurrency.placeholder')}
              searchPlaceholder={t('form.searchPlaceholder')}
              noResults={t('form.noResults')}
              surface
              onChange={(v) => handleCurrencyChange(v, field.onChange)}
              onClear={() => field.onChange(null)}
            />
          )}
        />
      </div>

      <WarningHint show={!!(primaryUnsupported || secondaryUnsupported)} separator parentGap={24}>
        {tCommon.rich('currency.unsupportedHint', {
          bold: (chunks) => <strong>{chunks}</strong>,
        })}
      </WarningHint>

      <Separator />

      <div className="flex flex-col gap-y-3">
        <div className="flex flex-col gap-y-2">
          <Label>{t('form.periodPresets.label')}</Label>
          <Hint>{t('form.periodPresets.hint')}</Hint>
        </div>
        <div className="grid grid-cols-4 gap-x-2">
          {(['periodPreset1', 'periodPreset2', 'periodPreset3', 'periodPreset4'] as const).map(
            (name, i) => (
              <Controller
                key={name}
                name={name}
                control={control}
                render={({ field, fieldState }) => (
                  <Input
                    {...field}
                    placeholder={localizePreset(PERIOD_PRESETS[i]?.code, yearSuffix)}
                    aria-invalid={!!fieldState.error}
                    containerClassName="text-center"
                    className="uppercase"
                    onChange={(e) => field.onChange(e.target.value.toUpperCase())}
                  />
                )}
              />
            ),
          )}
        </div>
        {(errors.periodPreset1 ||
          errors.periodPreset2 ||
          errors.periodPreset3 ||
          errors.periodPreset4) && (
          <p className="text-paragraph-xs text-destructive">
            {t('form.periodPresets.invalidFormat')}
          </p>
        )}
        <InfoHint>{t('form.periodPresets.format')}</InfoHint>
        <InfoHint>{t('form.periodPresets.emptyDefault')}</InfoHint>
        <InfoHint>{t('form.periodPresets.partialWarning')}</InfoHint>
      </div>

      <Button blue type="submit" disabled={isSubmitting || !primaryCurrency}>
        {isSubmitting ? t('form.cta.loading') : t('form.cta.label')}
      </Button>
    </form>
  );
}
