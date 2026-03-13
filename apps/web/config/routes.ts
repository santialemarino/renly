export const ROUTES = {
  home: '/dashboard',
  auth: {
    login: '/login',
    signup: '/signup',
  },
  dashboard: '/dashboard',
  investments: '/investments',
  snapshots: '/snapshots',
  dataEntry: '/data-entry',
  settings: '/settings',
} as const;

/** All auth routes — accessible without a session */
export const AUTH_ROUTES = [ROUTES.auth.login, ROUTES.auth.signup] as const;

export const LOGIN_ROUTE = ROUTES.auth.login;
