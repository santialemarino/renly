'use client';

import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ChevronRight } from 'lucide-react';
import { AnimatePresence, LayoutGroup, motion } from 'motion/react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { cn } from '@repo/ui/lib';
import { PillToggleGroup } from '@/components/pill-toggle-group';
import { COOKIE_MAX_AGE_1_YEAR } from '@/config/constants';
import { ANIMATION_DEFAULT } from '@/lib/constants/animations';
import {
  CURRENCY_COLLAPSED_COOKIE,
  ORIGINAL_CURRENCY,
  useCurrencyStore,
} from '@/lib/stores/currency-store';
import { isCurrencySupported } from '@/lib/utils/currency';

interface CurrencySwitcherProps {
  displayCurrencies: string[];
  activeCurrency: string;
  initialCollapsed: boolean;
}

export function CurrencySwitcher({
  displayCurrencies,
  activeCurrency: initialActive,
  initialCollapsed,
}: CurrencySwitcherProps) {
  const t = useTranslations('sidebar');
  const tCommon = useTranslations('common');
  const router = useRouter();
  const setActiveCurrency = useCurrencyStore((s) => s.setActiveCurrency);
  const [activeCurrency, setActive] = useState(initialActive);
  const [collapsed, setCollapsed] = useState(initialCollapsed);

  // Measure content height for smooth container resize.
  const contentRef = useRef<HTMLDivElement>(null);
  const [contentHeight, setContentHeight] = useState<number | undefined>(undefined);

  useLayoutEffect(() => {
    useCurrencyStore.setState({ activeCurrency: initialActive });
  }, [initialActive]);

  useEffect(() => {
    const el = contentRef.current;
    if (!el) return;
    setContentHeight(el.scrollHeight);
    const observer = new ResizeObserver(() => setContentHeight(el.scrollHeight));
    observer.observe(el);
    return () => observer.disconnect();
  }, [collapsed]);

  function handleChange(v: string) {
    setActive(v);
    setActiveCurrency(v);

    if (v !== ORIGINAL_CURRENCY && !isCurrencySupported(v)) {
      toast.warning(tCommon('currency.unsupportedSwitch', { currency: v }));
    }

    router.refresh();
  }

  function handleToggleCollapse() {
    setCollapsed((prev) => {
      const next = !prev;
      document.cookie = `${CURRENCY_COLLAPSED_COOKIE}=${next}; path=/; max-age=${COOKIE_MAX_AGE_1_YEAR}`;
      return next;
    });
  }

  const activeLabel =
    activeCurrency === ORIGINAL_CURRENCY ? t('currency.original') : activeCurrency;

  const pillToggle = (
    <PillToggleGroup
      items={displayCurrencies.map((code) => ({
        value: code,
        label: code === ORIGINAL_CURRENCY ? t('currency.original') : code,
      }))}
      value={activeCurrency}
      onValueChange={handleChange}
      itemClassName="flex-1 text-paragraph-xs font-mono"
      className="w-full border-blue-100 shadow-none"
    />
  );

  const chevron = (
    <button
      onClick={handleToggleCollapse}
      className="group/currency-collapse shrink-0 cursor-pointer focus-visible:outline-none"
    >
      <ChevronRight
        className={cn(
          'size-4 text-blue-400 transition-transform duration-200',
          'group-focus-visible/currency-collapse:animate-focus-bump',
          !collapsed && 'rotate-90',
        )}
      />
    </button>
  );

  return (
    <div
      className="overflow-hidden bg-blue-50 rounded-lg transition-[height] duration-200 ease-in-out"
      style={{ height: contentHeight }}
    >
      <div ref={contentRef} className="p-3">
        <AnimatePresence mode="wait" initial={false}>
          {collapsed ? (
            <motion.div
              key="collapsed"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: ANIMATION_DEFAULT }}
            >
              <LayoutGroup>
                <div className="flex items-center gap-x-2">
                  <motion.span
                    layout
                    transition={{ duration: ANIMATION_DEFAULT }}
                    className="shrink-0 font-mono text-paragraph-sm-semibold text-blue-800"
                  >
                    {activeLabel}
                  </motion.span>
                  <motion.div
                    layout
                    transition={{ duration: ANIMATION_DEFAULT }}
                    className="min-w-0 flex-1"
                  >
                    {pillToggle}
                  </motion.div>
                  {chevron}
                </div>
              </LayoutGroup>
            </motion.div>
          ) : (
            <motion.div
              key="expanded"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: ANIMATION_DEFAULT }}
              className="flex flex-col gap-y-2"
            >
              <div className="flex items-center">
                <span className="text-paragraph-sm-medium text-blue-800">
                  {t('currency.label')}
                </span>
                <div className="ml-auto">{chevron}</div>
              </div>
              {pillToggle}
              <span className="text-paragraph-xs text-blue-400">* {t('currency.note')}</span>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
