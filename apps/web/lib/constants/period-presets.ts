// Period presets for the dashboard date range picker.
// Configurable via env vars: NEXT_PUBLIC_PERIOD_PRESET_1 through _4.
// Format: "3M" = 3 months, "6M" = 6 months, "1Y" = 1 year, "YTD" = year to date.
// An "all" preset is always appended as the last option.

type PresetCode = string;

const UNIT_MONTH = 'M';
const UNIT_YEAR = 'Y';
const YEAR_ALIASES = ['Y', 'A'];
const PRESET_YTD = 'YTD';
const PRESET_ALL = 'all';
const PRESET_ALL_UPPER = 'ALL';

// Regex for validating preset codes. Accepts NM, NY, NA (year alias), or YTD.
export const PRESET_PATTERN = /^(\d+[MYA]|YTD)$/i;

// Regex for extracting amount + unit from a preset code (excludes YTD/ALL).
const UNIT_PATTERN = /^(\d+)([MYA])$/;

export interface PeriodPreset {
  code: PresetCode;
}

const ENV_KEYS = [
  process.env.NEXT_PUBLIC_PERIOD_PRESET_1,
  process.env.NEXT_PUBLIC_PERIOD_PRESET_2,
  process.env.NEXT_PUBLIC_PERIOD_PRESET_3,
  process.env.NEXT_PUBLIC_PERIOD_PRESET_4,
] as const;

// Normalizes year aliases (A → Y) so codes are stored canonically.
function normalizeCode(code: string): string {
  return code.replace(/a$/i, UNIT_YEAR).toLowerCase();
}

function parseCodes(raw: (string | undefined)[]): PeriodPreset[] {
  const codes = raw.filter((v): v is string => !!v && PRESET_PATTERN.test(v)).map(normalizeCode);
  return [...codes.map((code) => ({ code })), { code: PRESET_ALL }];
}

function parsePresets(): PeriodPreset[] {
  const envCodes = ENV_KEYS.filter((v): v is string => !!v && PRESET_PATTERN.test(v));
  return parseCodes(envCodes);
}

export const PERIOD_PRESETS = parsePresets();

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
