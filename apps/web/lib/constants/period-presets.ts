// Period presets for the dashboard date range picker.
// Configurable via env vars: NEXT_PUBLIC_PERIOD_PRESET_1 through _4.
// Format: "3M" = 3 months, "6M" = 6 months, "1Y" = 1 year, "YTD" = year to date.
// An "all" preset is always appended as the last option.

type PresetCode = string;

interface PeriodPreset {
  code: PresetCode;
  translationKey: string;
}

const ENV_KEYS = [
  process.env.NEXT_PUBLIC_PERIOD_PRESET_1,
  process.env.NEXT_PUBLIC_PERIOD_PRESET_2,
  process.env.NEXT_PUBLIC_PERIOD_PRESET_3,
  process.env.NEXT_PUBLIC_PERIOD_PRESET_4,
] as const;

const DEFAULTS: PresetCode[] = ['1M', '3M', '6M', 'YTD'];

const VALID_PATTERN = /^(\d+[MY]|YTD)$/i;

function parsePresets(): PeriodPreset[] {
  const raw = ENV_KEYS.filter((v): v is string => !!v && VALID_PATTERN.test(v));
  const codes = raw.length > 0 ? raw.map((v) => v.toUpperCase()) : DEFAULTS;

  return [
    ...codes.map((code) => ({
      code: code.toLowerCase(),
      translationKey: `period.${code.toLowerCase()}`,
    })),
    { code: 'all', translationKey: 'period.all' },
  ];
}

export const PERIOD_PRESETS = parsePresets();

// Computes a start date from a preset code relative to now, snapped to start of month.
export function presetToStartDate(code: string): string | undefined {
  if (code === 'all') return undefined;

  const now = new Date();
  const upper = code.toUpperCase();

  if (upper === 'YTD') {
    return `${now.getFullYear()}-01-01`;
  }

  const match = upper.match(/^(\d+)([MY])$/);
  if (!match || !match[1] || !match[2]) return undefined;

  const amount = parseInt(match[1], 10);
  const unit = match[2];

  if (unit === 'M') {
    const d = new Date(now.getFullYear(), now.getMonth() - amount, 1);
    return d.toISOString().slice(0, 10);
  }

  if (unit === 'Y') {
    const d = new Date(now.getFullYear() - amount, now.getMonth(), 1);
    return d.toISOString().slice(0, 10);
  }

  return undefined;
}
