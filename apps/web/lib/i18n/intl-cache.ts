/*
 * Bounded cache of `Intl.*` instances, keyed by (localeTag, options). Constructing an
 * `Intl.NumberFormat` / `Intl.DateTimeFormat` / `Intl.ListFormat` resolves locale data and is
 * far more expensive than calling `.format()` on an existing one — and dense surfaces (the
 * snapshots grid, tables, charts) format hundreds of cells per render, each otherwise building
 * a fresh instance. Every formatter in this module routes construction through here so the same
 * (locale, options) pair reuses one instance. Output is byte-identical to a fresh instance, so
 * this is purely a perf optimization.
 *
 * The keyspace is naturally bounded — a handful of supported locales × a fixed set of option
 * shapes used across the formatters. The number/list caches stay tiny (~a dozen entries); the
 * date cache also keys on `timeZone` (only for `formatTimestampDate`), whose values are validated
 * IANA zone names, so it is bounded by the finite IANA set — never user-unbounded. A plain `Map`
 * therefore never grows without bound, and the instances are stateless, so no eviction is needed.
 */

const numberFormats = new Map<string, Intl.NumberFormat>();
const dateTimeFormats = new Map<string, Intl.DateTimeFormat>();
const listFormats = new Map<string, Intl.ListFormat>();

// Cache key for a (locale, options) pair. `JSON.stringify` drops `undefined`-valued options
// (e.g. an unset `timeZone`), so an ambient-zone formatter caches under the same key as one built
// with the option omitted — which is correct, they behave identically.
function cacheKey(locale: string, options: object): string {
  return `${locale}|${JSON.stringify(options)}`;
}

// Returns a cached `Intl.NumberFormat` for the (locale, options) pair, constructing on first use.
export function numberFormat(
  locale: string,
  options: Intl.NumberFormatOptions = {},
): Intl.NumberFormat {
  const key = cacheKey(locale, options);
  let formatter = numberFormats.get(key);
  if (!formatter) {
    formatter = new Intl.NumberFormat(locale, options);
    numberFormats.set(key, formatter);
  }
  return formatter;
}

// Returns a cached `Intl.DateTimeFormat` for the (locale, options) pair, constructing on first use.
export function dateTimeFormat(
  locale: string,
  options: Intl.DateTimeFormatOptions = {},
): Intl.DateTimeFormat {
  const key = cacheKey(locale, options);
  let formatter = dateTimeFormats.get(key);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat(locale, options);
    dateTimeFormats.set(key, formatter);
  }
  return formatter;
}

// Returns a cached `Intl.ListFormat` for the (locale, options) pair, constructing on first use.
export function listFormat(locale: string, options: Intl.ListFormatOptions = {}): Intl.ListFormat {
  const key = cacheKey(locale, options);
  let formatter = listFormats.get(key);
  if (!formatter) {
    formatter = new Intl.ListFormat(locale, options);
    listFormats.set(key, formatter);
  }
  return formatter;
}
