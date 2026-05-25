// Timezone constants and IANA zone list. The list comes from `Intl.supportedValuesOf('timeZone')`
// at module load (Node >= 18, all modern browsers). Sorted alphabetically.

export const TIMEZONE_DEFAULT = 'UTC';

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
