// Helpers that resolve "today" in a specific IANA timezone (the user's settings timezone).
// An undefined timeZone falls back to the environment's default zone — the browser zone in
// client components, the server zone in server components.

// Returns today's date as YYYY-MM-DD in the given IANA timezone. The 'en-CA' locale formats
// dates ISO-style. An invalid timezone name falls back to the environment default, mirroring
// the API's today_in_timezone UTC fallback.
export function todayInTimezone(timeZone?: string): string {
  try {
    return new Intl.DateTimeFormat('en-CA', { timeZone }).format(new Date());
  } catch {
    return new Intl.DateTimeFormat('en-CA').format(new Date());
  }
}

// Returns the current year and month (1-12) in the given IANA timezone.
export function currentYearMonth(timeZone?: string): { year: number; month: number } {
  const iso = todayInTimezone(timeZone);
  return { year: Number(iso.slice(0, 4)), month: Number(iso.slice(5, 7)) };
}

/*
 * Whether a string is a real YYYY-MM-DD calendar date.
 *
 * Two checks, and each catches what the other cannot. The pattern rejects anything not in that exact
 * form — and it is what makes the parse below safe, because it hands over three known numbers rather
 * than a string whose interpretation depends on the engine's date parsing. The calendar comparison
 * then rejects a date-shaped string that is not a date: `2026-02-31` passes any pattern, and Date
 * ROLLS IT FORWARD to 3 March rather than failing, so the only way to notice is to check that the
 * date you got back is the one you asked for.
 *
 * Which half does which job is worth being exact about, because a sweep made it clear that only one of
 * them REJECTS anything:
 *
 *   * the pattern's job is to hand over three known numbers, so the parse cannot be at the mercy of
 *     the engine's string-to-date rules;
 *   * the comparison, against the WHOLE original string, is what rejects. It is total on its own: a
 *     value longer than ten characters cannot equal a ten-character result whatever the pattern
 *     allowed, and a day out of range always rolls the month, so nothing gets through it.
 *
 * So the trailing `$` and the exact slice length are shape statements rather than second checks, and
 * no input can distinguish keeping them from dropping them — verified by mutating both and finding, by
 * proof rather than by a missing case, that no such input exists. An earlier version compared the
 * three fields separately instead; those clauses were MUTUALLY redundant (an out-of-range day rolls
 * the month, an out-of-range month rolls the year), so either of two could be deleted and stay green.
 *
 * Built from UTC parts rather than by parsing the string: a local-zone construction shifts the day
 * west of UTC, which would fail the last day of a month for no reason the caller could see. One
 * consequence worth knowing — Date.UTC maps years 0-99 to 1900-1999, so a date before 0100-01-01
 * fails. Nothing here dates from then (every picker is bounded above by today) and refusing is safe.
 */
export function isIsoDate(value: string): boolean {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (match === null) return false;
  const parsed = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}
