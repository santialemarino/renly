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

/*
 * "Dólar tarjeta" ≈ oficial × this. As of 2026 the only surcharge on Argentine foreign-currency card
 * consumption is the 30% Ganancias perception (Impuesto PAIS expired 2024-12-23 and its residual
 * provisions were removed 2026-01-02), so the default is 1.30.
 *
 * Env-overridable because the figure is regulatory and volatile with no clean API — a hardcode would go
 * stale silently, and sources disagree while it moves. It feeds ONLY the estimate shown beside a
 * cross-currency settlement's implied rate: nothing stored depends on it, and the user's typed amount is
 * always what gets recorded, so a wrong multiplier misleads a comparison and corrupts no data.
 */
export const CARD_PERCEPTION_MULTIPLIER =
  Number(process.env.NEXT_PUBLIC_CARD_PERCEPTION_MULTIPLIER) || 1.3;
