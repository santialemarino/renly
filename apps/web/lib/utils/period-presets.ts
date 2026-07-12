// Runtime functions for period preset formatting, building, and date computation.

import { PERIOD_PRESETS, PRESET_PATTERN, type PeriodPreset } from '@/lib/constants/period-presets';
import { currentYearMonth } from '@/lib/utils/dates';

const UNIT_MONTH = 'M';
const UNIT_YEAR = 'Y';
const YEAR_ALIASES = ['Y', 'A'];
const PRESET_YTD = 'YTD';
const PRESET_ALL = 'all';
const PRESET_ALL_UPPER = 'ALL';
const UNIT_PATTERN = /^(\d+)([MYA])$/;

function normalizeCode(code: string): string {
  return code.replace(/a$/i, UNIT_YEAR).toLowerCase();
}

function parseCodes(raw: (string | undefined)[]): PeriodPreset[] {
  const codes = raw.filter((v): v is string => !!v && PRESET_PATTERN.test(v)).map(normalizeCode);
  return [...codes.map((code) => ({ code })), { code: PRESET_ALL }];
}

// Builds presets from user settings. Falls back to env defaults if no user presets.
export function buildPresets(userPresets: string[] | null | undefined): PeriodPreset[] {
  if (!userPresets || userPresets.length === 0) return PERIOD_PRESETS;
  const valid = userPresets.filter((v) => PRESET_PATTERN.test(v));
  return valid.length > 0 ? parseCodes(valid) : PERIOD_PRESETS;
}

// Formats a preset code into a display label using localized suffixes.
export function formatPresetLabel(
  code: string,
  translations: { ytd: string; all: string; monthSuffix: string; yearSuffix: string },
): string {
  const upper = code.toUpperCase();
  if (upper === PRESET_YTD) return translations.ytd;
  if (upper === PRESET_ALL_UPPER) return translations.all;
  const match = upper.match(UNIT_PATTERN);
  if (!match) return upper;
  const [, amount, unit] = match;
  if (unit && YEAR_ALIASES.includes(unit)) return `${amount}${translations.yearSuffix}`;
  return `${amount}${translations.monthSuffix}`;
}

// First day of the month `shiftMonths` months away from (year, month), as YYYY-MM-DD.
function startOfMonthShifted(year: number, month: number, shiftMonths: number): string {
  const total = year * 12 + (month - 1) + shiftMonths;
  const shiftedYear = Math.floor(total / 12);
  const shiftedMonth = (total % 12) + 1;
  return `${shiftedYear}-${String(shiftedMonth).padStart(2, '0')}-01`;
}

// Computes a start date from a preset code relative to the user's "today" in the given IANA
// timezone (undefined = environment default zone), snapped to start of month. Pure string
// arithmetic — no Date object, so no local/UTC or DST skew.
export function presetToStartDate(code: string, timeZone?: string): string | undefined {
  if (code === PRESET_ALL) return undefined;

  const { year, month } = currentYearMonth(timeZone);
  const upper = code.toUpperCase();

  if (upper === PRESET_YTD) {
    return `${year}-01-01`;
  }

  const match = upper.match(UNIT_PATTERN);
  if (!match || !match[1] || !match[2]) return undefined;

  const amount = parseInt(match[1], 10);
  const unit = match[2];

  if (unit === UNIT_MONTH) {
    return startOfMonthShifted(year, month, -amount);
  }

  if (YEAR_ALIASES.includes(unit)) {
    return startOfMonthShifted(year, month, -amount * 12);
  }

  return undefined;
}

// Localizes a canonical preset code (e.g. "1Y") for display using the year suffix.
export function localizePreset(code: string | undefined, yearSuffix: string): string {
  if (!code) return '';
  return code.replace(/Y$/i, yearSuffix);
}
