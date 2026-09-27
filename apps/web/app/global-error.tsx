'use client';

import './globals.css';

import { useSyncExternalStore } from 'react';
import { Plus_Jakarta_Sans } from 'next/font/google';

import { GlobalErrorContent } from '@/components/global-error-content';
import { useReportBoundaryError } from '@/lib/hooks/use-report-boundary-error';
import { DEFAULT_LOCALE, LOCALE_COOKIE, resolveLocale, type Locale } from '@/lib/i18n/locales';

const plusJakartaSans = Plus_Jakarta_Sans({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
});

// Reads the locale cookie from `document.cookie`.
function readLocaleCookie(): string | undefined {
  return document.cookie
    .split('; ')
    .find((entry) => entry.startsWith(`${LOCALE_COOKIE}=`))
    ?.slice(LOCALE_COOKIE.length + 1);
}

// The visitor's locale, resolved by the same rule every server render uses.
function getClientLocale(): Locale {
  return resolveLocale(readLocaleCookie(), navigator.languages);
}

// Neither input announces its changes, so there is nothing to subscribe to.
function subscribe(): () => void {
  return () => {};
}

interface GlobalErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

/*
 * The last boundary: it replaces the ROOT layout when that layout itself throws, so none of what the
 * root layout provides exists here — no next-intl provider, no messages, no `<html lang>`, no styles.
 * This page supplies each of them itself, and its copy is imported statically (see
 * `lib/i18n/error-boundary-messages.ts`), so it can never render without a heading and a retry.
 *
 * A client component has no request to read the locale from, so the server render uses the default
 * and `useSyncExternalStore` swaps in the visitor's locale on hydration without a mismatch.
 */
export default function GlobalError({ error, reset }: GlobalErrorProps) {
  const locale = useSyncExternalStore(subscribe, getClientLocale, () => DEFAULT_LOCALE);
  useReportBoundaryError(error);

  return (
    <html className={plusJakartaSans.className} lang={locale}>
      <body className="min-h-screen w-full bg-muted/30 antialiased">
        <GlobalErrorContent locale={locale} reset={reset} />
      </body>
    </html>
  );
}
