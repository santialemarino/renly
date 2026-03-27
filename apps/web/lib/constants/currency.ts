// Fallback currencies from env (used when no user settings exist).
export const FALLBACK_PRIMARY_CURRENCY = process.env.NEXT_PUBLIC_FALLBACK_PRIMARY_CURRENCY ?? 'ARS';
export const FALLBACK_SECONDARY_CURRENCY =
  process.env.NEXT_PUBLIC_FALLBACK_SECONDARY_CURRENCY ?? 'USD';

// Preferred currencies from env. Comma-separated, e.g. "BRL,EUR,GBP".
export const ENV_PREFERRED_CURRENCIES = (process.env.NEXT_PUBLIC_PREFERRED_CURRENCIES ?? '')
  .split(',')
  .filter(Boolean);

// Dollar rate preference options for the settings form.
export const DOLLAR_RATE_OPTIONS = [
  { value: 'oficial', labelKey: 'oficial' },
  { value: 'mep', labelKey: 'mep' },
  { value: 'blue', labelKey: 'blue' },
] as const;

export const DOLLAR_RATE_DEFAULT = process.env.NEXT_PUBLIC_FALLBACK_DOLLAR_RATE ?? 'mep';
