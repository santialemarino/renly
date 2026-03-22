'use client';

import { useRouter } from 'next/navigation';
import { zodResolver } from '@hookform/resolvers/zod';
import { AlertTriangle } from 'lucide-react';
import { AnimatePresence, motion } from 'motion/react';
import { useTranslations } from 'next-intl';
import { Controller, useForm } from 'react-hook-form';
import { toast } from 'sonner';

import { Button, Hint, Label, Separator } from '@repo/ui/components';
import { CurrencyCombobox } from '@/app/(protected)/_components/currency-combobox';
import { saveSettings } from '@/app/(protected)/settings/settings-actions';
import {
  settingsFormSchema,
  type SettingsFormValues,
} from '@/app/(protected)/settings/settings-form-schema';
import { WarningHint } from '@/components/warning-hint';
import type { SettingsData } from '@/lib/api/settings';
import { isCurrencySupported } from '@/lib/utils/currency';

interface SettingsFormProps {
  initialSettings: SettingsData;
}

const fallbackPrimary = process.env.NEXT_PUBLIC_FALLBACK_PRIMARY_CURRENCY ?? 'ARS';
const fallbackSecondary = process.env.NEXT_PUBLIC_FALLBACK_SECONDARY_CURRENCY ?? 'USD';

export function SettingsForm({ initialSettings }: SettingsFormProps) {
  const t = useTranslations('settings');
  const tCommon = useTranslations('common');
  const router = useRouter();

  const {
    control,
    handleSubmit,
    watch,
    formState: { isSubmitting },
  } = useForm<SettingsFormValues>({
    resolver: zodResolver(settingsFormSchema),
    defaultValues: {
      primaryCurrency: initialSettings.primaryCurrency ?? fallbackPrimary,
      secondaryCurrency: initialSettings.secondaryCurrency ?? fallbackSecondary,
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
      await saveSettings(values.primaryCurrency, values.secondaryCurrency ?? null);
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
                transition={{ duration: 0.25 }}
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
                transition={{ duration: 0.25 }}
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

      {(primaryUnsupported || secondaryUnsupported) && <Separator />}
      <WarningHint show={!!(primaryUnsupported || secondaryUnsupported)}>
        {tCommon.rich('currency.unsupportedHint', {
          bold: (chunks) => <strong>{chunks}</strong>,
        })}
      </WarningHint>

      <Button blue type="submit" disabled={isSubmitting || !primaryCurrency}>
        {isSubmitting ? t('form.cta.loading') : t('form.cta.label')}
      </Button>
    </form>
  );
}
