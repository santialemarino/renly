// Dashboard health-indicator threshold defaults. Phase 3 Step 6 follow-up — Savings Rate
// and Income/Expense Ratio thresholds promoted from module-local constants in
// `dashboard-footer.tsx` to user-configurable settings (matches the pattern set by
// `liquidity_threshold_pct`). Env vars provide the deploy-time fallback for the form
// placeholders; the backend stores user-set values in `user_settings.settings`.

export const ENV_SAVINGS_RATE_HEALTHY_PCT = Number(
  process.env.NEXT_PUBLIC_SAVINGS_RATE_HEALTHY_PCT ?? 20,
);

export const ENV_SAVINGS_RATE_MODERATE_PCT = Number(
  process.env.NEXT_PUBLIC_SAVINGS_RATE_MODERATE_PCT ?? 10,
);

export const ENV_INCOME_EXPENSE_RATIO_HEALTHY = Number(
  process.env.NEXT_PUBLIC_INCOME_EXPENSE_RATIO_HEALTHY ?? 1.5,
);

// Income/expense ratio break-even point. Hardcoded mathematical constant, not user-tunable —
// ratio == 1 means income exactly covers expenses; below = deficit, above = surplus.
export const INCOME_EXPENSE_RATIO_BREAKEVEN = 1;
