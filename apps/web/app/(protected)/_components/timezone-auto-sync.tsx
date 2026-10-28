'use client';

import { useEffect, useRef } from 'react';

import {
  seedTimezoneCookie,
  syncBrowserTimezone,
} from '@/app/(protected)/_components/timezone-auto-sync-actions';
import {
  detectBrowserTimezone,
  pinnedTimezone,
  TIMEZONE_MODE_AUTO,
} from '@/lib/constants/timezones';

interface TimezoneAutoSyncProps {
  storedTimezone: string | null;
  storedMode: string | null;
  timezoneCookie: string | null;
}

/*
 * Keeps the user's timezone setting and this browser's timezone cookie in step, once per mount. In
 * 'auto' it follows the browser: reads Intl.DateTimeFormat, compares it to the stored value, and PUTs
 * the diff via a server action (which also sets the cookie); when the stored value already matches, it
 * seeds a cookie that is absent or names another zone. In 'manual' the stored zone is pinned and never updated; instead, when
 * the cookie is absent or names another zone, it seeds the cookie from the pin. No UI surface —
 * purely a side-effect mount on the protected layout.
 */
export function TimezoneAutoSync({
  storedTimezone,
  storedMode,
  timezoneCookie,
}: TimezoneAutoSyncProps) {
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return;
    ran.current = true;

    // Treat a null mode as 'auto' (first-fill for existing users).
    const mode = storedMode ?? TIMEZONE_MODE_AUTO;
    if (mode !== TIMEZONE_MODE_AUTO) {
      const pinned = pinnedTimezone(storedTimezone, mode);
      if (pinned && pinned !== timezoneCookie) {
        seedTimezoneCookie(pinned).catch(() => {
          // Intentional no-op — the next page load retries.
        });
      }
      return;
    }

    const browserTz = detectBrowserTimezone();
    if (!browserTz) return;
    if (browserTz === storedTimezone) {
      // The account already follows this zone, but a new browser has no cookie yet (login seeds only a
      // manual zone), and without it the server renders timestamps in its own zone.
      if (timezoneCookie !== browserTz) {
        seedTimezoneCookie(browserTz).catch(() => {
          // Intentional no-op — the next page load retries.
        });
      }
      return;
    }

    // Fire-and-forget; errors are silently swallowed (the next page load will retry).
    syncBrowserTimezone(browserTz).catch(() => {
      // Intentional no-op — non-blocking sync.
    });
  }, [storedTimezone, storedMode, timezoneCookie]);

  return null;
}
