'use client';

import { useMemo } from 'react';
import { useLocale } from 'next-intl';

import { createFormatters } from '@/lib/i18n/create-formatters';

// Client hook returning locale-bound formatters (see `createFormatters`). Reads the active locale from next-intl so call sites never thread it. Memoised per locale.
export function useFormatters() {
  const locale = useLocale();
  return useMemo(() => createFormatters(locale), [locale]);
}
