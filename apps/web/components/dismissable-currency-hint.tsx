'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';

import { InfoHint } from '@/components/styled-hint';

const STORAGE_KEY = 'currency-hint-dismissed';

interface DismissableCurrencyHintProps {
  show: boolean;
}

// Shows an info hint explaining that currency conversions use today's exchange rate.
// The user can dismiss it permanently via localStorage.
export function DismissableCurrencyHint({ show }: DismissableCurrencyHintProps) {
  const t = useTranslations('common.currencyHint');
  const [dismissed, setDismissed] = useState(true);

  useEffect(() => {
    setDismissed(localStorage.getItem(STORAGE_KEY) === 'true');
  }, []);

  const handleDismiss = () => {
    localStorage.setItem(STORAGE_KEY, 'true');
    setDismissed(true);
  };

  return (
    <InfoHint show={show && !dismissed} surface parentGap={16} onDismiss={handleDismiss}>
      {t('message')}
    </InfoHint>
  );
}
