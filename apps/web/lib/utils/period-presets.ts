// Runtime functions for period preset formatting, building, and date computation.

import { PERIOD_PRESETS, PRESET_PATTERN, type PeriodPreset } from '@/lib/constants/period-presets';

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

// Computes a start date from a preset code relative to now, snapped to start of month.
export function presetToStartDate(code: string): string | undefined {
  if (code === PRESET_ALL) return undefined;

  const now = new Date();
  const upper = code.toUpperCase();

  if (upper === PRESET_YTD) {
    return `${now.getFullYear()}-01-01`;
  }

  const match = upper.match(UNIT_PATTERN);
  if (!match || !match[1] || !match[2]) return undefined;

  const amount = parseInt(match[1], 10);
  const unit = match[2];

  if (unit === UNIT_MONTH) {
    const d = new Date(now.getFullYear(), now.getMonth() - amount, 1);
    return d.toISOString().slice(0, 10);
  }

  if (YEAR_ALIASES.includes(unit)) {
    const d = new Date(now.getFullYear() - amount, now.getMonth(), 1);
    return d.toISOString().slice(0, 10);
  }

  return undefined;
}

// Localizes a canonical preset code (e.g. "1Y") for display using the year suffix.
export function localizePreset(code: string | undefined, yearSuffix: string): string {
  if (!code) return '';
  return code.replace(/Y$/i, yearSuffix);
}
