export const ROUTES = {
  home: '/dashboard',
  auth: {
    login: '/login',
    signup: '/signup',
  },
  dashboard: '/dashboard',
  financeDashboard: '/finance-dashboard',
  income: '/income',
  expenses: '/expenses',
  creditCards: '/credit-cards',
  subscriptions: '/subscriptions',
  installments: '/installments',
  investorDashboard: '/investor-dashboard',
  investments: '/investments',
  groups: '/groups',
  snapshots: '/snapshots',
  preferences: '/preferences',
  integrations: '/integrations',
} as const;

/** All auth routes — accessible without a session */
export const AUTH_ROUTES = [ROUTES.auth.login, ROUTES.auth.signup] as const;

export const LOGIN_ROUTE = ROUTES.auth.login;
