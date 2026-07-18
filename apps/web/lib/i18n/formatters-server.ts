import 'server-only';

import { getLocale } from 'next-intl/server';

import { createFormatters } from '@/lib/i18n/create-formatters';

// Server counterpart of `useFormatters` for async Server Components. Resolves the active locale via next-intl, then returns the same locale-bound formatter set.
export async function getFormatters() {
  const locale = await getLocale();
  return createFormatters(locale);
}
