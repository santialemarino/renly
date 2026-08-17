export const ROUTES = {
  home: '/dashboard',
  landing: '/',
  help: '/help',
  privacy: '/privacy',
  terms: '/terms',
  disclaimer: '/disclaimer',
  auth: {
    login: '/login',
    signup: '/signup',
    forgotPassword: '/forgot-password',
    resetPassword: '/reset-password',
    verifyEmail: '/verify-email',
  },
  dashboard: '/dashboard',
  financeDashboard: '/finance-dashboard',
  income: '/income',
  expenses: '/expenses',
  creditCards: '/credit-cards',
  accounts: '/accounts',
  subscriptions: '/subscriptions',
  installments: '/installments',
  paymentObligations: '/payment-obligations',
  paymentsCalendar: '/payments-calendar',
  investorDashboard: '/investor-dashboard',
  investments: '/investments',
  groups: '/groups',
  snapshots: '/snapshots',
  preferences: '/preferences',
  alerts: '/alerts',
  localization: '/localization',
  integrations: '/integrations',
  account: '/account',
  data: '/data',
  admin: '/admin',
  adminFeedback: '/admin/feedback',
} as const;

/*
 * The per-account ledger — the app's only dynamic route. Deliberately a helper rather than a member
 * of ROUTES: ALL_ROUTE_PATHS flattens ROUTES' values as strings or objects of strings, so a function
 * there would contribute nothing and silently drop out of PROTECTED_ROUTES. It needs no entry of its
 * own anyway — the route gate matches by prefix, so `/accounts` already protects `/accounts/{id}`.
 */
export const accountLedgerPath = (accountId: number) => `${ROUTES.accounts}/${accountId}`;

/** All auth routes — accessible without a session */
export const AUTH_ROUTES = [
  ROUTES.auth.login,
  ROUTES.auth.signup,
  ROUTES.auth.forgotPassword,
  ROUTES.auth.resetPassword,
  ROUTES.auth.verifyEmail,
] as const;

/** Public, unauthenticated routes — the marketing landing, help, and legal pages. */
export const PUBLIC_ROUTES = [
  ROUTES.landing,
  ROUTES.help,
  ROUTES.privacy,
  ROUTES.terms,
  ROUTES.disclaimer,
] as const;

// Every leaf path in ROUTES, including the nested `auth` group, deduped.
export const ALL_ROUTE_PATHS = Array.from(
  new Set(
    Object.values(ROUTES).flatMap((value) =>
      typeof value === 'string' ? [value] : Object.values(value),
    ),
  ),
);

/**
 * Protected routes — the complement ROUTES − AUTH_ROUTES − PUBLIC_ROUTES, computed (not a static
 * literal) so ROUTES stays the single source of truth: any new route is protected by default
 * (safe-by-default). Drives the proxy gate's optimistic login redirect; the (protected) layout's
 * getSession() is the authoritative guard.
 */
export const PROTECTED_ROUTES = ALL_ROUTE_PATHS.filter(
  (path) =>
    !(AUTH_ROUTES as readonly string[]).includes(path) &&
    !(PUBLIC_ROUTES as readonly string[]).includes(path),
);

export const LOGIN_ROUTE = ROUTES.auth.login;
