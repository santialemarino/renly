// Liquidity-alert constants. Phase 3 Step 6.

// Default threshold percentage. Frontend fallback used by the alerts form placeholder
// and by `dashboard-footer` when the user hasn't saved a preference yet. Backend mirrors
// this default via `DEFAULT_LIQUIDITY_THRESHOLD_PCT` in `app/utils/liquidity.py` — keep
// the two in sync. Same pattern as `DOLLAR_RATE_DEFAULT` / `dollar_rate_preference`.
export const ENV_LIQUIDITY_THRESHOLD_PCT = Number(
  process.env.NEXT_PUBLIC_LIQUIDITY_THRESHOLD_PCT ?? 40,
);

// Percentage-points above the user's threshold where state flips from caution to at_risk.
// Hardcoded opinion, not user-tunable. Mirrors `LIQUIDITY_CAUTION_BAND_PCT` on the backend.
export const LIQUIDITY_CAUTION_BAND_PCT = 10;
