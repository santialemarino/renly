'use client';

import './globals.css';

import { useEffect, useState } from 'react';
import { Plus_Jakarta_Sans } from 'next/font/google';
import { NextIntlClientProvider } from 'next-intl';

import { ErrorState } from '@/components/error-state';
import { useReportBoundaryError } from '@/lib/hooks/use-report-boundary-error';
import { DEFAULT_LOCALE, LOCALE_COOKIE, resolveLocale, type Locale } from '@/lib/i18n/locales';

const plusJakartaSans = Plus_Jakarta_Sans({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
});

// The copy this page renders — the one namespace `ErrorState` reads — in the visitor's locale.
interface GlobalErrorCopy {
  locale: Locale;
  documentTitle: string;
  messages: { common: { errorBoundary: Record<string, string> } };
}

// Reads the locale cookie from `document.cookie`.
function readLocaleCookie(): string | undefined {
  return document.cookie
    .split('; ')
    .find((entry) => entry.startsWith(`${LOCALE_COOKIE}=`))
    ?.slice(LOCALE_COOKIE.length + 1);
}

/*
 * Resolves the visitor's locale by the same rule every server render uses, then loads that locale's
 * translations. Loaded on demand rather than imported: this component sits at the root of the tree, so
 * a static import put every locale's full message set into a chunk the browser fetched on EVERY page —
 * measured at ~87 KB gzipped for two locales, to serve a page almost nobody sees. The dynamic import is
 * split per locale and fetched only when this page renders.
 */
async function loadCopy(): Promise<GlobalErrorCopy> {
  const locale = resolveLocale(readLocaleCookie(), navigator.languages);
  const { default: messages } = await import(`../translations/${locale}.json`);
  const errorBoundary = messages.common.errorBoundary;
  return {
    locale,
    documentTitle: errorBoundary.documentTitle,
    messages: { common: { errorBoundary } },
  };
}

interface GlobalErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

/*
 * The last boundary: it replaces the ROOT layout when that layout itself throws, so none of what the
 * root layout provides exists here — no next-intl provider, no messages, no `<html lang>`, no styles.
 * This page supplies each of them itself. A client component has no request to read the locale from
 * on the server, so the copy renders once the browser has resolved it and loaded its messages; the
 * first paint is the empty page shell for the moment that takes.
 */
export default function GlobalError({ error, reset }: GlobalErrorProps) {
  const [copy, setCopy] = useState<GlobalErrorCopy | null>(null);
  useReportBoundaryError(error);

  useEffect(() => {
    let live = true;
    void loadCopy().then((loaded) => {
      if (live) setCopy(loaded);
    });
    return () => {
      live = false;
    };
  }, []);

  return (
    <html className={plusJakartaSans.className} lang={copy?.locale ?? DEFAULT_LOCALE}>
      <body className="min-h-screen w-full bg-muted/30 antialiased">
        {copy && (
          <>
            <title>{copy.documentTitle}</title>
            <NextIntlClientProvider locale={copy.locale} messages={copy.messages}>
              <main className="flex flex-col min-h-screen">
                <ErrorState reset={reset} showHomeLink />
              </main>
            </NextIntlClientProvider>
          </>
        )}
      </body>
    </html>
  );
}
