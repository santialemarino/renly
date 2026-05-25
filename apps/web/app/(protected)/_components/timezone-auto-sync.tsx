'use client';

import { useEffect, useRef } from 'react';

import { syncBrowserTimezone } from '@/app/(protected)/_components/timezone-auto-sync-actions';
import { detectBrowserTimezone, TIMEZONE_MODE_AUTO } from '@/lib/constants/timezones';

interface TimezoneAutoSyncProps {
  storedTimezone: string | null;
  storedMode: string | null;
}

/*
 * Silently keeps the user's timezone setting in sync with the browser-detected IANA zone
 * while mode is 'auto'. Runs once per mount: reads Intl.DateTimeFormat, compares to
 * stored value, and PUTs the diff via a server action. Skipped when mode = 'manual'.
 * No UI surface — purely a side-effect mount on the protected layout.
 */
export function TimezoneAutoSync({ storedTimezone, storedMode }: TimezoneAutoSyncProps) {
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return;
    ran.current = true;

    // Mode 'manual' locks the stored value — never auto-update.
    // Treat a null mode as 'auto' (first-fill for existing users).
    const mode = storedMode ?? TIMEZONE_MODE_AUTO;
    if (mode !== TIMEZONE_MODE_AUTO) return;

    const browserTz = detectBrowserTimezone();
    if (!browserTz) return;
    if (browserTz === storedTimezone) return;

    // Fire-and-forget; errors are silently swallowed (the next page load will retry).
    syncBrowserTimezone(browserTz).catch(() => {
      // Intentional no-op — non-blocking sync.
    });
  }, [storedTimezone, storedMode]);

  return null;
}
