export const ROUTES = {
  home: '/dashboard',
  auth: {
    login: '/login',
  },
  dashboard: '/dashboard',
  investments: '/investments',
  dataEntry: '/data-entry',
  settings: '/settings',
} as const;

/** All auth routes — accessible without a session */
export const AUTH_ROUTES = [ROUTES.auth.login] as const;

export const LOGIN_ROUTE = ROUTES.auth.login;
