'use client';

import { NextIntlClientProvider } from 'next-intl';

import { ErrorState } from '@/components/error-state';
import { ERROR_BOUNDARY_MESSAGES } from '@/lib/i18n/error-boundary-messages';
import type { Locale } from '@/lib/i18n/locales';

interface GlobalErrorContentProps {
  locale: Locale;
  reset: () => void;
}

/*
 * Everything `app/global-error.tsx` renders inside `<body>`: the document title and the boundary, in
 * `locale`, from the statically imported error-boundary copy. Its own module so it can be rendered —
 * and tested — without the `<html>` shell around it.
 */
export function GlobalErrorContent({ locale, reset }: GlobalErrorContentProps) {
  const errorBoundary = ERROR_BOUNDARY_MESSAGES[locale];

  return (
    <>
      <title>{errorBoundary.documentTitle}</title>
      <NextIntlClientProvider locale={locale} messages={{ common: { errorBoundary } }}>
        <main className="flex flex-col min-h-screen">
          <ErrorState reset={reset} showHomeLink />
        </main>
      </NextIntlClientProvider>
    </>
  );
}
