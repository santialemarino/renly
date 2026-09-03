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
    /*
     * The group-invite landing page. Unauthenticated on purpose, and grouped here for exactly that
     * reason: most recipients open the link with no session, and a protected route would bounce them
     * to /login and drop the token from the URL. Unlike its siblings it does NOT redirect a
     * logged-in visitor away — accepting an invite is what a logged-in visitor came here to do.
     */
    joinGroup: '/join',
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
  collections: '/collections',
  snapshots: '/snapshots',
  shared: '/shared',
  preferences: '/preferences',
  alerts: '/alerts',
  notifications: '/notifications',
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

/** A group's hub. A helper for the same reason as accountLedgerPath — `/shared` already protects it. */
export const sharedGroupPath = (groupId: number) => `${ROUTES.shared}/${groupId}`;

/*
 * A pot's page. Same reasoning again, plus one thing worth knowing: `/shared/pots/[id]` and
 * `/shared/[groupId]` are siblings, and Next resolves the STATIC segment first — so `/shared/pots/5`
 * is the pot page while `/shared/12` stays the group hub. `/shared/pots` with no id falls through to
 * the hub with groupId="pots", which is not a number and already renders notFound() there.
 */
export const sharedPotPath = (potId: number) => `${ROUTES.shared}/pots/${potId}`;

/*
 * The three guided flows (U6). Routes rather than dialogs, which is what makes them resumable: each
 * derives the step it opens on from what the server already has, so re-entering the URL after a
 * failure — or after closing the tab — continues rather than restarting.
 *
 * "Share something you own" hangs off the GROUP, not a pot, because it may have no pot yet: it creates
 * one. `?pot=` targets an existing one instead, which is both how the pot page hands the flow off and
 * how an interrupted run resumes. The other two hang off the pot whose ownership they change.
 */
export const sharedSharePath = (groupId: number, potId?: number) =>
  `${sharedGroupPath(groupId)}/share${potId === undefined ? '' : `?pot=${potId}`}`;

export const sharedTakeOutPath = (potId: number) => `${sharedPotPath(potId)}/take-out`;

export const sharedBuyOutPath = (potId: number) => `${sharedPotPath(potId)}/buy-out`;

/*
 * Anchors on the public help page that the app deep-links to. A help section's id is part of a public
 * URL, so it belongs here with the routes rather than as a string literal at each call site: a typo
 * becomes a type error, and `translations-parity.test.ts` asserts every value still names a real
 * section (renaming one otherwise breaks the link silently — the browser just does not scroll).
 */
export const HELP_ANCHORS = {
  accuracy: 'accuracy',
  snapshots: 'snapshots',
  returns: 'returns',
  currency: 'currency',
} as const;

export type HelpAnchor = (typeof HELP_ANCHORS)[keyof typeof HELP_ANCHORS];

/** Deep link to one help section. */
export const helpAnchorPath = (anchor: HelpAnchor) => `${ROUTES.help}#${anchor}`;

/** All auth routes — accessible without a session */
export const AUTH_ROUTES = [
  ROUTES.auth.login,
  ROUTES.auth.signup,
  ROUTES.auth.forgotPassword,
  ROUTES.auth.resetPassword,
  ROUTES.auth.verifyEmail,
  ROUTES.auth.joinGroup,
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
