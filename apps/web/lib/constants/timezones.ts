// Timezone constants and IANA zone list. The list comes from `Intl.supportedValuesOf('timeZone')`
// at module load (Node >= 18, all modern browsers). Sorted alphabetically.

import { COOKIE_MAX_AGE_1_YEAR } from '@/config/constants';

export const TIMEZONE_DEFAULT = 'UTC';

// Cookie carrying the active IANA timezone across requests — mirrors LOCALE_COOKIE. Written by the
// localization save + timezone auto-sync actions, read by i18n/request.ts to drive next-intl's timeZone.
export const TIMEZONE_COOKIE = 'NEXT_TIMEZONE';
export const TIMEZONE_COOKIE_MAX_AGE = COOKIE_MAX_AGE_1_YEAR;

export const TIMEZONE_MODE_AUTO = 'auto';
export const TIMEZONE_MODE_MANUAL = 'manual';
export const TIMEZONE_MODES = [TIMEZONE_MODE_AUTO, TIMEZONE_MODE_MANUAL] as const;
export type TimezoneMode = (typeof TIMEZONE_MODES)[number];

// All IANA timezone names supported by the runtime. Falls back to a small list when
// Intl.supportedValuesOf isn't available (older runtimes); validation still happens server-side.
function listIanaTimezones(): string[] {
  const intl = Intl as unknown as { supportedValuesOf?: (key: string) => string[] };
  if (typeof intl.supportedValuesOf === 'function') {
    return [...intl.supportedValuesOf('timeZone')].sort();
  }
  return ['UTC', 'America/Argentina/Buenos_Aires', 'America/New_York', 'Europe/Madrid'];
}

export const IANA_TIMEZONES: string[] = listIanaTimezones();

// Returns the browser's detected IANA timezone. Safe to call on both server and client;
// returns TIMEZONE_DEFAULT when the runtime can't resolve a zone.
export function detectBrowserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || TIMEZONE_DEFAULT;
  } catch {
    return TIMEZONE_DEFAULT;
  }
}

// True when the runtime recognises the IANA timezone name. Used to validate the timezone cookie
// before handing it to next-intl (an unknown zone would otherwise throw in Intl formatters).
export function isValidTimezone(tz: string): boolean {
  try {
    Intl.DateTimeFormat('en-US', { timeZone: tz });
    return true;
  } catch {
    return false;
  }
}

// Formats an IANA timezone for display: underscores -> spaces, slashes -> " / ".
// Storage and validation always operate on the raw IANA value; this is presentation-only.
// "America/Argentina/Buenos_Aires" -> "America / Argentina / Buenos Aires".
export function formatIanaTimezone(tz: string): string {
  return tz.replace(/_/g, ' ').replace(/\//g, ' / ');
}
