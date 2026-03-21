'use client';

import { useLayoutEffect, useState } from 'react';
import { useTranslations } from 'next-intl';

import { ToggleGroup, ToggleGroupItem } from '@repo/ui/components';
import { ORIGINAL_CURRENCY, useCurrencyStore } from '@/lib/stores/currency-store';

interface CurrencySwitcherProps {
  displayCurrencies: string[];
  activeCurrency: string;
}

export function CurrencySwitcher({
  displayCurrencies,
  activeCurrency: initialActive,
}: CurrencySwitcherProps) {
  const t = useTranslations('sidebar');
  const setActiveCurrency = useCurrencyStore((s) => s.setActiveCurrency);
  const [activeCurrency, setActive] = useState(initialActive);

  useLayoutEffect(() => {
    useCurrencyStore.setState({ activeCurrency: initialActive });
  }, [initialActive]);

  // TODO: §11.4.1 — When switching to a currency without exchange rate support,
  // show a warning toast: "Conversion to {CURRENCY} is not available yet.
  // Showing values in original currency. Support coming soon."
  function handleChange(v: string) {
    setActive(v);
    setActiveCurrency(v);
  }

  return (
    <div className="flex flex-col p-3 gap-y-2 bg-blue-50 rounded-lg">
      <span className="text-paragraph-sm-medium text-blue-800">{t('currency.label')}</span>
      <ToggleGroup
        type="single"
        value={activeCurrency}
        onValueChange={(v) => v && handleChange(v)}
        variant="outline"
        size="sm"
        className="w-full border border-blue-100 bg-white rounded-full overflow-hidden"
      >
        {displayCurrencies.map((code) => (
          <ToggleGroupItem
            key={code}
            value={code}
            className="flex-1 border-0 data-[state=on]:bg-blue-800 data-[state=on]:text-white transition-all duration-200 text-paragraph-mini font-mono"
          >
            {code === ORIGINAL_CURRENCY ? t('currency.original') : code}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
      <span className="text-paragraph-mini text-blue-400">* {t('currency.note')}</span>
    </div>
  );
}
