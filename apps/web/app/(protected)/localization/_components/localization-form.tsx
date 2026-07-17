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
import { FormCombobox } from '@/components/form-combobox';
import { PillToggleGroup } from '@/components/pill-toggle-group';
import { DEFAULT_LOCALE } from '@/config/constants';
import type { SettingsData } from '@/lib/api/settings';
import {
  detectBrowserLanguage,
  LANGUAGE_MODE_AUTO,
  LANGUAGE_MODE_MANUAL,
  LANGUAGE_OPTIONS,
} from '@/lib/constants/languages';
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

  const initialTimezoneMode =
    initialSettings.timezoneMode === TIMEZONE_MODE_MANUAL
      ? TIMEZONE_MODE_MANUAL
      : TIMEZONE_MODE_AUTO;
  const initialLanguageMode =
    initialSettings.languageMode === LANGUAGE_MODE_MANUAL
      ? LANGUAGE_MODE_MANUAL
      : LANGUAGE_MODE_AUTO;

  // defaultValues use stored values OR static fallbacks — never call detectBrowser*() here.
  // Those helpers reference `navigator` / `Intl.DateTimeFormat()` which return different values
  // on SSR vs client, causing hydration mismatches. The layout-level auto-sync effects populate
  // stored values in the background; the form only ever sees what's already persisted.
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
      timezone: initialSettings.timezone ?? TIMEZONE_DEFAULT,
      timezoneMode: initialTimezoneMode,
      language: (initialSettings.language ?? DEFAULT_LOCALE) as LocalizationFormValues['language'],
      languageMode: initialLanguageMode,
    },
  });

  const currentTimezoneMode = watch('timezoneMode');
  const currentLanguageMode = watch('languageMode');

  // Picking a timezone manually flips its mode to manual (the act of choosing IS a manual override).
  function handleTimezoneChange(tz: string) {
    setValue('timezone', tz, { shouldDirty: true });
    if (watch('timezoneMode') === TIMEZONE_MODE_AUTO) {
      setValue('timezoneMode', TIMEZONE_MODE_MANUAL, { shouldDirty: true });
    }
  }

  // Switching the timezone pill back to Automatic immediately re-syncs to the browser tz.
  function handleTimezoneModeChange(value: string) {
    setValue('timezoneMode', value as LocalizationFormValues['timezoneMode'], {
      shouldDirty: true,
    });
    if (value === TIMEZONE_MODE_AUTO) {
      const browserTz = detectBrowserTimezone();
      if (browserTz) setValue('timezone', browserTz, { shouldDirty: true });
    }
  }

  // Picking a language manually flips its mode to manual (same UX as timezone).
  function handleLanguageChange(value: string) {
    setValue('language', value as LocalizationFormValues['language'], { shouldDirty: true });
    if (watch('languageMode') === LANGUAGE_MODE_AUTO) {
      setValue('languageMode', LANGUAGE_MODE_MANUAL, { shouldDirty: true });
    }
  }

  // Switching the language pill back to Automatic immediately re-syncs to the browser language.
  function handleLanguageModeChange(value: string) {
    setValue('languageMode', value as LocalizationFormValues['languageMode'], {
      shouldDirty: true,
    });
    if (value === LANGUAGE_MODE_AUTO) {
      const browserLang = detectBrowserLanguage();
      if (browserLang)
        setValue('language', browserLang as LocalizationFormValues['language'], {
          shouldDirty: true,
        });
    }
  }

  async function onSubmit(values: LocalizationFormValues) {
    try {
      await saveLocalization({
        timezone: values.timezone,
        timezoneMode: values.timezoneMode,
        language: values.language,
        languageMode: values.languageMode,
      });
      reset(values);
      router.refresh();
      toast.success(t('form.saveSuccess'), { id: 'localization-save' });
    } catch {
      toast.error(t('form.saveError'), { id: 'localization-save' });
    }
  }

  const timezoneModeItems = [
    { value: TIMEZONE_MODE_AUTO, label: t('form.mode.automatic') },
    { value: TIMEZONE_MODE_MANUAL, label: t('form.mode.manual') },
  ];
  const languageModeItems = [
    { value: LANGUAGE_MODE_AUTO, label: t('form.mode.automatic') },
    { value: LANGUAGE_MODE_MANUAL, label: t('form.mode.manual') },
  ];

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col w-full gap-y-6 lg:gap-y-10">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-12 gap-y-8">
        {/* Left column — Language */}
        <div className="flex flex-col max-w-md gap-y-3">
          <h3 className="text-paragraph-sm-semibold text-muted-foreground">
            {t('form.sectionLanguage')}
          </h3>

          <div className="flex flex-col gap-y-2">
            <Label>{t('form.languageMode.label')}</Label>
            <Hint>{t('form.languageMode.hint')}</Hint>
            <Controller
              name="languageMode"
              control={control}
              render={({ field }) => (
                <PillToggleGroup
                  items={languageModeItems}
                  value={field.value}
                  onValueChange={handleLanguageModeChange}
                />
              )}
            />
          </div>

          <Separator />

          <div className="flex flex-col gap-y-2">
            <Label>{t('form.language.label')}</Label>
            <Hint>
              {currentLanguageMode === LANGUAGE_MODE_AUTO
                ? t('form.language.hintAuto')
                : t('form.language.hintManual')}
            </Hint>
            <Controller
              name="language"
              control={control}
              render={({ field }) => (
                <FormCombobox
                  surface
                  value={field.value}
                  onValueChange={handleLanguageChange}
                  options={LANGUAGE_OPTIONS.map((opt) => ({
                    value: opt.value,
                    label: t(`form.language.options.${opt.labelKey}`),
                  }))}
                />
              )}
            />
          </div>
        </div>

        {/* Right column — Timezone */}
        <div className="flex flex-col max-w-md gap-y-3">
          <h3 className="text-paragraph-sm-semibold text-muted-foreground">
            {t('form.sectionTimezone')}
          </h3>

          <div className="flex flex-col gap-y-2">
            <Label>{t('form.timezoneMode.label')}</Label>
            <Hint>{t('form.timezoneMode.hint')}</Hint>
            <Controller
              name="timezoneMode"
              control={control}
              render={({ field }) => (
                <PillToggleGroup
                  items={timezoneModeItems}
                  value={field.value}
                  onValueChange={handleTimezoneModeChange}
                />
              )}
            />
          </div>

          <Separator />

          <div className="flex flex-col gap-y-2">
            <Label>{t('form.timezone.label')}</Label>
            <Hint>
              {currentTimezoneMode === TIMEZONE_MODE_AUTO
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
      </div>

      <Button blue type="submit" className="w-full max-w-md lg:max-w-full" disabled={isSubmitting}>
        {isSubmitting ? t('form.cta.loading') : t('form.cta.label')}
      </Button>
    </form>
  );
}
