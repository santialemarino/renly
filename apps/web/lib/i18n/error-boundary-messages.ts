import type { Locale } from '@/lib/i18n/locales';
import en from '../../translations/error-boundary/en.json';
import es from '../../translations/error-boundary/es.json';

/*
 * The error boundaries' copy — `common.errorBoundary` — kept in its own small file per locale rather
 * than inside `translations/<code>.json`, because `app/global-error.tsx` has to import it STATICALLY: it
 * renders when the root layout (and with it the next-intl provider and every message) is gone, and a
 * page that loads its copy on demand renders nothing at all when that load fails. Importing the full
 * translation files there would ship every locale's whole message set to every page.
 *
 * This is still the one source: `i18n/request.ts` merges it into `common` for every other render.
 * Keyed by `Locale`, so adding a language without its file here is a type error.
 */
export type ErrorBoundaryMessages = typeof en;

export const ERROR_BOUNDARY_MESSAGES: Record<Locale, ErrorBoundaryMessages> = { en, es };

// A locale's full message set with the error-boundary copy merged into `common`.
export function withErrorBoundaryMessages<T extends { common: object }>(
  messages: T,
  locale: Locale,
): T & { common: { errorBoundary: ErrorBoundaryMessages } } {
  return {
    ...messages,
    common: { ...messages.common, errorBoundary: ERROR_BOUNDARY_MESSAGES[locale] },
  };
}
