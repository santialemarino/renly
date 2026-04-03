// Group limit constants from env (used when no user settings exist).

// Maximum groups per user. Numeric default: 50.
export const ENV_MAX_GROUPS = Number(process.env.NEXT_PUBLIC_MAX_GROUPS ?? 50);

// Warning threshold as a percentage of max groups. Null means no warning.
export const ENV_GROUP_WARNING_PCT = process.env.NEXT_PUBLIC_GROUP_LIMIT_WARNING_PCT
  ? Number(process.env.NEXT_PUBLIC_GROUP_LIMIT_WARNING_PCT)
  : null;
