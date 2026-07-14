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
