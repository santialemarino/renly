'use client';

import { useEffect, useRef } from 'react';

import {
  seedLocaleCookie,
  syncBrowserLanguage,
} from '@/app/(protected)/_components/language-auto-sync-actions';
import { detectBrowserLanguage, LANGUAGE_MODE_AUTO, pinnedLocale } from '@/lib/i18n/locales';

interface LanguageAutoSyncProps {
  storedLanguage: string | null;
  storedMode: string | null;
  localeCookie: string | null;
}

/*
 * Keeps the user's language setting and this browser's locale cookie in step, once per mount. In
 * 'auto' it follows the browser: reads navigator.language (mapped to a supported locale), compares it
 * to the stored value, and PUTs the diff via a server action. In 'manual' the stored value is pinned and
 * never updated; instead, when the cookie is absent or names another locale, it seeds the cookie from
 * the pin. No UI surface — purely a side-effect mount on the protected layout.
 */
export function LanguageAutoSync({
  storedLanguage,
  storedMode,
  localeCookie,
}: LanguageAutoSyncProps) {
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return;
    ran.current = true;

    // Treat a null mode as 'auto' (first-fill for existing users).
    const mode = storedMode ?? LANGUAGE_MODE_AUTO;
    if (mode !== LANGUAGE_MODE_AUTO) {
      const pinned = pinnedLocale(storedLanguage, mode);
      if (pinned && pinned !== localeCookie) {
        seedLocaleCookie(pinned).catch(() => {
          // Intentional no-op — the next page load retries.
        });
      }
      return;
    }

    const browserLang = detectBrowserLanguage();
    if (!browserLang) return;
    if (browserLang === storedLanguage) return;

    // Fire-and-forget; errors are silently swallowed (the next page load will retry).
    syncBrowserLanguage(browserLang).catch(() => {
      // Intentional no-op — non-blocking sync.
    });
  }, [storedLanguage, storedMode, localeCookie]);

  return null;
}
