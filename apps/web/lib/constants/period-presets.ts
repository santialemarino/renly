// Period preset constants for the dashboard date range picker.
// Format: "3M" = 3 months, "6M" = 6 months, "1Y" = 1 year, "YTD" = year to date.
// An "all" preset is always appended as the last option.

// Regex for validating preset codes. Accepts NM, NY, NA (year alias), or YTD.
export const PRESET_PATTERN = /^(\d+[MYA]|YTD)$/i;

export interface PeriodPreset {
  code: string;
}

// The presets offered when the deployment configures none. A built image never receives the
// NEXT_PUBLIC_PERIOD_PRESET_* values (they are inlined at build time, and the Docker build has no
// .env), so without this a deployed app would offer only "All".
const FALLBACK_PRESETS = ['1M', '3M', '6M', 'YTD'];

// NEXT_PUBLIC_PERIOD_PRESET_1 through _4 override the fallback as a set: when any is set, exactly the
// ones set are used, in slot order.
const ENV_KEYS = [
  process.env.NEXT_PUBLIC_PERIOD_PRESET_1,
  process.env.NEXT_PUBLIC_PERIOD_PRESET_2,
  process.env.NEXT_PUBLIC_PERIOD_PRESET_3,
  process.env.NEXT_PUBLIC_PERIOD_PRESET_4,
].filter((v): v is string => !!v);

const DEFAULT_VALUES = ENV_KEYS.length > 0 ? ENV_KEYS : FALLBACK_PRESETS;

// Comma-separated display string of the default preset values (e.g. "1M, 3M, 6M, YTD").
export const DEFAULT_PERIOD_PRESETS = DEFAULT_VALUES.join(', ');

// The default preset codes (without "all"). Used for placeholders in the settings form.
export const DEFAULT_PRESET_CODES: PeriodPreset[] = DEFAULT_VALUES.filter((v) =>
  PRESET_PATTERN.test(v),
).map((c) => ({ code: c.replace(/a$/i, 'Y').toLowerCase() }));

// Default presets: the env override or the fallback, with "all" always appended.
export const PERIOD_PRESETS: PeriodPreset[] = [...DEFAULT_PRESET_CODES, { code: 'all' }];
