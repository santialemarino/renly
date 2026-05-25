'use client';

import { useRouter } from 'next/navigation';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslations } from 'next-intl';
import { Controller, useForm } from 'react-hook-form';
import { toast } from 'sonner';

import { Button, Hint, Label, Separator } from '@repo/ui/components';
import { TimezoneCombobox } from '@/app/(protected)/_components/timezone-combobox';
import { saveLocalization } from '@/app/(protected)/localization/localization-actions';
import {
  localizationFormSchema,
  type LocalizationFormValues,
} from '@/app/(protected)/localization/localization-form-schema';
import { PillToggleGroup } from '@/components/pill-toggle-group';
import type { SettingsData } from '@/lib/api/settings';
import {
  detectBrowserTimezone,
  TIMEZONE_DEFAULT,
  TIMEZONE_MODE_AUTO,
  TIMEZONE_MODE_MANUAL,
} from '@/lib/constants/timezones';

interface LocalizationFormProps {
  initialSettings: SettingsData;
}

export function LocalizationForm({ initialSettings }: LocalizationFormProps) {
  const t = useTranslations('localization');
  const router = useRouter();

  const initialMode =
    initialSettings.timezoneMode === TIMEZONE_MODE_MANUAL
      ? TIMEZONE_MODE_MANUAL
      : TIMEZONE_MODE_AUTO;

  const {
    control,
    handleSubmit,
    setValue,
    watch,
    reset,
    formState: { isSubmitting },
  } = useForm<LocalizationFormValues>({
    resolver: zodResolver(localizationFormSchema),
    defaultValues: {
      timezone: initialSettings.timezone ?? detectBrowserTimezone() ?? TIMEZONE_DEFAULT,
      timezoneMode: initialMode,
    },
  });

  const currentMode = watch('timezoneMode');

  // Picking a timezone manually flips mode to manual (the act of choosing IS a manual override).
  function handleTimezoneChange(tz: string) {
    setValue('timezone', tz, { shouldDirty: true });
    if (watch('timezoneMode') === TIMEZONE_MODE_AUTO) {
      setValue('timezoneMode', TIMEZONE_MODE_MANUAL, { shouldDirty: true });
    }
  }

  // Switching back to Automatic immediately re-syncs to the browser tz so the next
  // navigation reflects the detected value.
  function handleModeChange(value: string) {
    setValue('timezoneMode', value as LocalizationFormValues['timezoneMode'], {
      shouldDirty: true,
    });
    if (value === TIMEZONE_MODE_AUTO) {
      const browserTz = detectBrowserTimezone();
      if (browserTz) setValue('timezone', browserTz, { shouldDirty: true });
    }
  }

  async function onSubmit(values: LocalizationFormValues) {
    try {
      await saveLocalization({
        timezone: values.timezone,
        timezoneMode: values.timezoneMode,
      });
      reset(values);
      router.refresh();
      toast.success(t('form.saveSuccess'), { id: 'localization-save' });
    } catch {
      toast.error(t('form.saveError'), { id: 'localization-save' });
    }
  }

  const modeItems = [
    { value: TIMEZONE_MODE_AUTO, label: t('form.mode.automatic') },
    { value: TIMEZONE_MODE_MANUAL, label: t('form.mode.manual') },
  ];

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col w-full max-w-md gap-y-6">
      <div className="flex flex-col gap-y-3">
        <div className="flex flex-col gap-y-2">
          <Label>{t('form.mode.label')}</Label>
          <Hint>{t('form.mode.hint')}</Hint>
          <Controller
            name="timezoneMode"
            control={control}
            render={({ field }) => (
              <PillToggleGroup
                items={modeItems}
                value={field.value}
                onValueChange={handleModeChange}
              />
            )}
          />
        </div>

        <Separator />

        <div className="flex flex-col gap-y-2">
          <Label>{t('form.timezone.label')}</Label>
          <Hint>
            {currentMode === TIMEZONE_MODE_AUTO
              ? t('form.timezone.hintAuto')
              : t('form.timezone.hintManual')}
          </Hint>
          <Controller
            name="timezone"
            control={control}
            render={({ field }) => (
              <TimezoneCombobox
                value={field.value || null}
                placeholder={t('form.timezone.placeholder')}
                searchPlaceholder={t('form.timezone.searchPlaceholder')}
                noResults={t('form.timezone.noResults')}
                surface
                onChange={handleTimezoneChange}
              />
            )}
          />
        </div>
      </div>

      <Button blue type="submit" disabled={isSubmitting}>
        {isSubmitting ? t('form.cta.loading') : t('form.cta.label')}
      </Button>
    </form>
  );
}
