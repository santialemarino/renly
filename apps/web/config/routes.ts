export const ROUTES = {
  home: '/dashboard',
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
} as const;

/** All auth routes — accessible without a session */
export const AUTH_ROUTES = [
  ROUTES.auth.login,
  ROUTES.auth.signup,
  ROUTES.auth.forgotPassword,
  ROUTES.auth.resetPassword,
  ROUTES.auth.verifyEmail,
] as const;

export const LOGIN_ROUTE = ROUTES.auth.login;
