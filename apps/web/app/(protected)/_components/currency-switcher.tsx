'use client';

import { useLayoutEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { ToggleGroup, ToggleGroupItem } from '@repo/ui/components';
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
            className="flex-1 border-0 data-[state=on]:bg-blue-800 data-[state=on]:text-white transition-all duration-200 text-paragraph-mini font-mono focus-visible:outline-none focus-visible:bg-accent focus-visible:animate-[pulse-scale_0.3s_ease-in-out]"
          >
            {code === ORIGINAL_CURRENCY ? t('currency.original') : code}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
      <span className="text-paragraph-mini text-blue-400">* {t('currency.note')}</span>
    </div>
  );
}
