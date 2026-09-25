// Collection limit constants from env (used when no user settings exist).

// Maximum collections per user. Numeric default: 50.
export const ENV_MAX_COLLECTIONS = Number(process.env.NEXT_PUBLIC_MAX_COLLECTIONS ?? 50);

// The inclusive ranges the API accepts for the two settings (`MAX_COLLECTIONS_RANGE` and
// `COLLECTION_WARNING_PCT_RANGE` in apps/api/app/schemas/settings.py); the Alerts form enforces the same.
export const MAX_COLLECTIONS_RANGE = [1, 1000] as const;
export const COLLECTION_WARNING_PCT_RANGE = [1, 100] as const;

// Warning threshold as a percentage of max collections. Null means no warning.
export const ENV_COLLECTION_WARNING_PCT = process.env.NEXT_PUBLIC_COLLECTION_LIMIT_WARNING_PCT
  ? Number(process.env.NEXT_PUBLIC_COLLECTION_LIMIT_WARNING_PCT)
  : null;
