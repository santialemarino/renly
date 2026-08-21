// Collection limit constants from env (used when no user settings exist).

// Maximum collections per user. Numeric default: 50.
export const ENV_MAX_COLLECTIONS = Number(process.env.NEXT_PUBLIC_MAX_COLLECTIONS ?? 50);

// Warning threshold as a percentage of max collections. Null means no warning.
export const ENV_COLLECTION_WARNING_PCT = process.env.NEXT_PUBLIC_COLLECTION_LIMIT_WARNING_PCT
  ? Number(process.env.NEXT_PUBLIC_COLLECTION_LIMIT_WARNING_PCT)
  : null;
