'use client';

import { useLayoutEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { getCurrencyPillLabel } from '@/app/(protected)/_components/currency-combobox';
import { PillToggleGroup } from '@/components/pill-toggle-group';
import { ORIGINAL_CURRENCY, useCurrencyStore } from '@/lib/stores/currency-store';
import { isCurrencySupported } from '@/lib/utils/currency';

interface CurrencySwitcherProps {
  displayCurrencies: string[];
  activeCurrency: string;
}

export function CurrencySwitcher({
  displayCurrencies,
  activeCurrency: initialActive,
}: CurrencySwitcherProps) {
  const t = useTranslations('sidebar');
  const tCommon = useTranslations('common');
  const router = useRouter();
  const setActiveCurrency = useCurrencyStore((s) => s.setActiveCurrency);
  const [activeCurrency, setActive] = useState(initialActive);

  useLayoutEffect(() => {
    useCurrencyStore.setState({ activeCurrency: initialActive });
  }, [initialActive]);

  function handleChange(v: string) {
    setActive(v);
    setActiveCurrency(v);

    if (v !== ORIGINAL_CURRENCY && !isCurrencySupported(v)) {
      toast.warning(tCommon('currency.unsupportedSwitch', { currency: v }));
    }

    // Re-fetch server components so pages that read the currency cookie get the new value.
    router.refresh();
  }

  return (
    <div className="flex flex-col p-3 gap-y-2 bg-blue-50 rounded-lg">
      <span className="text-paragraph-sm-medium text-blue-800">{t('currency.label')}</span>
      <PillToggleGroup
        items={displayCurrencies.map((code) => ({
          value: code,
          label: code === ORIGINAL_CURRENCY ? t('currency.original') : getCurrencyPillLabel(code),
        }))}
        value={activeCurrency}
        onValueChange={handleChange}
        itemClassName="flex-1 text-paragraph-xs font-mono"
        className="w-full border-blue-100 shadow-none"
      />
      <span className="text-paragraph-xs text-blue-400">* {t('currency.note')}</span>
    </div>
  );
}
