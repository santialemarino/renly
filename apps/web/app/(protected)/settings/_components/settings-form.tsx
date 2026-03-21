'use client';

import { useRouter } from 'next/navigation';
import { zodResolver } from '@hookform/resolvers/zod';
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
import type { SettingsData } from '@/lib/api/settings';

interface SettingsFormProps {
  initialSettings: SettingsData;
}

const fallbackPrimary = process.env.NEXT_PUBLIC_FALLBACK_PRIMARY_CURRENCY ?? 'ARS';
const fallbackSecondary = process.env.NEXT_PUBLIC_FALLBACK_SECONDARY_CURRENCY ?? 'USD';

export function SettingsForm({ initialSettings }: SettingsFormProps) {
  const t = useTranslations('settings');
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
        <Label>{t('form.primaryCurrency.label')}</Label>
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
              onChange={(v) => field.onChange(v ?? '')}
            />
          )}
        />
      </div>

      <Separator />

      <div className="flex flex-col gap-y-2">
        <Label>{t('form.secondaryCurrency.label')}</Label>
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
              onChange={field.onChange}
              onClear={() => field.onChange(null)}
            />
          )}
        />
      </div>

      {/* TODO: §11.4.1 — Add warning icon next to currencies without exchange rate support
          in each CurrencyCombobox. Below this separator, add a hint row with the warning icon
          + explanation: "Currencies marked with ⚠ don't have exchange rate support yet.
          Conversion will be available soon." Show warning toast on selection. */}

      <Button blue type="submit" disabled={isSubmitting || !primaryCurrency}>
        {isSubmitting ? t('form.cta.loading') : t('form.cta.label')}
      </Button>
    </form>
  );
}
