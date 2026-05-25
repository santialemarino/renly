'use client';

import { useEffect, useRef } from 'react';

import { syncBrowserLanguage } from '@/app/(protected)/_components/language-auto-sync-actions';
import { detectBrowserLanguage, LANGUAGE_MODE_AUTO } from '@/lib/constants/languages';

interface LanguageAutoSyncProps {
  storedLanguage: string | null;
  storedMode: string | null;
}

/*
 * Silently keeps the user's language setting in sync with the browser-detected locale
 * while mode is 'auto'. Runs once per mount: reads navigator.language (mapped to a supported
 * locale), compares to stored value, and PUTs the diff via a server action. Skipped when
 * mode = 'manual'. No UI surface — purely a side-effect mount on the protected layout.
 */
export function LanguageAutoSync({ storedLanguage, storedMode }: LanguageAutoSyncProps) {
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return;
    ran.current = true;

    // Mode 'manual' locks the stored value — never auto-update.
    // Treat a null mode as 'auto' (first-fill for existing users).
    const mode = storedMode ?? LANGUAGE_MODE_AUTO;
    if (mode !== LANGUAGE_MODE_AUTO) return;

    const browserLang = detectBrowserLanguage();
    if (!browserLang) return;
    if (browserLang === storedLanguage) return;

    // Fire-and-forget; errors are silently swallowed (the next page load will retry).
    syncBrowserLanguage(browserLang).catch(() => {
      // Intentional no-op — non-blocking sync.
    });
  }, [storedLanguage, storedMode]);

  return null;
}
