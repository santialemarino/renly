'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { Button, Hint, Label, Separator } from '@repo/ui/components';
import { CurrencyCombobox } from '@/app/(protected)/settings/_components/currency-combobox';
import { saveSettings } from '@/app/(protected)/settings/actions';
import type { SettingsData } from '@/lib/api/settings';

interface SettingsFormProps {
  initialSettings: SettingsData;
}

export function SettingsForm({ initialSettings }: SettingsFormProps) {
  const t = useTranslations('settings');
  const router = useRouter();

  const fallbackPrimary = process.env.NEXT_PUBLIC_FALLBACK_PRIMARY_CURRENCY ?? 'ARS';
  const fallbackSecondary = process.env.NEXT_PUBLIC_FALLBACK_SECONDARY_CURRENCY ?? 'USD';

  const [primary, setPrimary] = useState<string | null>(
    initialSettings.primary_currency ?? fallbackPrimary,
  );
  const [secondary, setSecondary] = useState<string | null>(
    initialSettings.secondary_currency ?? fallbackSecondary,
  );
  const [saving, setSaving] = useState(false);

  async function handleSave() {
    if (!primary) return;
    setSaving(true);
    try {
      await saveSettings(primary, secondary);
      router.refresh();
      toast.success(t('form.saveSuccess'), { id: 'settings-save' });
    } catch {
      toast.error(t('form.saveError'), { id: 'settings-save' });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-col w-full max-w-md gap-y-6">
      <div className="flex flex-col gap-y-2">
        <Label>{t('form.primaryCurrency.label')}</Label>
        <Hint>{t('form.primaryCurrency.hint')}</Hint>
        <CurrencyCombobox
          value={primary}
          exclude={secondary ? [secondary] : []}
          placeholder={t('form.primaryCurrency.placeholder')}
          searchPlaceholder={t('form.searchPlaceholder')}
          noResults={t('form.noResults')}
          onChange={setPrimary}
        />
      </div>

      <Separator />

      <div className="flex flex-col gap-y-2">
        <Label>{t('form.secondaryCurrency.label')}</Label>
        <Hint>{t('form.secondaryCurrency.hint')}</Hint>
        <CurrencyCombobox
          value={secondary}
          exclude={primary ? [primary] : []}
          placeholder={t('form.secondaryCurrency.placeholder')}
          searchPlaceholder={t('form.searchPlaceholder')}
          noResults={t('form.noResults')}
          onChange={setSecondary}
          onClear={() => setSecondary(null)}
        />
      </div>

      <Button blue onClick={handleSave} disabled={saving || !primary}>
        {saving ? t('form.cta.loading') : t('form.cta.label')}
      </Button>
    </div>
  );
}
