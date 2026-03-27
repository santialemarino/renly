// Period preset constants for the dashboard date range picker.
// Configurable via env vars: NEXT_PUBLIC_PERIOD_PRESET_1 through _4.
// Format: "3M" = 3 months, "6M" = 6 months, "1Y" = 1 year, "YTD" = year to date.
// An "all" preset is always appended as the last option.

// Regex for validating preset codes. Accepts NM, NY, NA (year alias), or YTD.
export const PRESET_PATTERN = /^(\d+[MYA]|YTD)$/i;

export interface PeriodPreset {
  code: string;
}

const ENV_KEYS = [
  process.env.NEXT_PUBLIC_PERIOD_PRESET_1,
  process.env.NEXT_PUBLIC_PERIOD_PRESET_2,
  process.env.NEXT_PUBLIC_PERIOD_PRESET_3,
  process.env.NEXT_PUBLIC_PERIOD_PRESET_4,
] as const;

// Comma-separated display string of env preset values (e.g. "1M, 3M, 6M, YTD").
export const ENV_PERIOD_PRESETS = ENV_KEYS.filter(Boolean).join(', ');

// Env-only preset codes (without "all"). Used for placeholders in the settings form.
export const ENV_PRESET_CODES: PeriodPreset[] = ENV_KEYS.filter(
  (v): v is string => !!v && PRESET_PATTERN.test(v),
).map((c) => ({ code: c.replace(/a$/i, 'Y').toLowerCase() }));

// Default presets derived from env vars at build time. "all" is always appended.
export const PERIOD_PRESETS: PeriodPreset[] = [...ENV_PRESET_CODES, { code: 'all' }];
