'use client';

import { useTranslations } from 'next-intl';

import { DismissableHint } from '@/components/dismissable-hint';

const STORAGE_KEY = 'currency-hint-dismissed';

interface DismissableCurrencyHintProps {
  show: boolean;
}

// Shows an info hint explaining that currency conversions use today's exchange rate.
// The user can dismiss it permanently via localStorage.
export function DismissableCurrencyHint({ show }: DismissableCurrencyHintProps) {
  const t = useTranslations('common.currencyHint');

  return (
    <DismissableHint storageKey={STORAGE_KEY} show={show}>
      {t('message')}
    </DismissableHint>
  );
}
