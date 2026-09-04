import {
  ArrowDownUp,
  BarChart3,
  Bell,
  CalendarClock,
  CircleDollarSign,
  CreditCard,
  FileText,
  FolderOpen,
  Gauge,
  Globe,
  Inbox,
  Landmark,
  ListChecks,
  Puzzle,
  Receipt,
  RefreshCw,
  Rows3,
  SlidersHorizontal,
  Table2,
  UserCog,
  UserPlus,
  Users,
} from 'lucide-react';

import { ROUTES } from '@/config/routes';

/*
 * What the sidebar lists, as data.
 *
 * It sits in `config/` beside `routes.ts` because that is what it is — the app's navigation
 * configuration, not presentation — and because of one concrete consequence: the sidebar component is
 * a `'use client'` module whose import graph reaches a server action and therefore `server-only`, so
 * nothing that lives inside it can be imported by a plain node test. The parity guard below (see
 * SIDEBAR_NAV_KEYS) needs exactly that, and the guard exists because a nav item shipped once with no
 * translation and rendered its own key path in the sidebar — invisible to tsc, ESLint, the build and
 * every other test.
 *
 * Each item is `{ key, href, icon }`: `key` names its `sidebar.nav.*` label, `href` comes from ROUTES
 * so no path is written twice, and `icon` is the Lucide glyph beside it.
 */

export const FINANCES_GROUP = [
  { key: 'financeDashboard', href: ROUTES.financeDashboard, icon: BarChart3 },
  { key: 'income', href: ROUTES.income, icon: CircleDollarSign },
  { key: 'expenses', href: ROUTES.expenses, icon: Receipt },
  { key: 'creditCards', href: ROUTES.creditCards, icon: CreditCard },
  { key: 'accounts', href: ROUTES.accounts, icon: Landmark },
] as const;

export const COMMITMENTS_GROUP = [
  { key: 'subscriptions', href: ROUTES.subscriptions, icon: RefreshCw },
  { key: 'installments', href: ROUTES.installments, icon: ListChecks },
  { key: 'paymentObligations', href: ROUTES.paymentObligations, icon: FileText },
  { key: 'paymentsCalendar', href: ROUTES.paymentsCalendar, icon: CalendarClock },
] as const;

export const PORTFOLIO_GROUP = [
  { key: 'investorDashboard', href: ROUTES.investorDashboard, icon: BarChart3 },
  { key: 'investments', href: ROUTES.investments, icon: Rows3 },
  { key: 'collections', href: ROUTES.collections, icon: FolderOpen },
  { key: 'snapshots', href: ROUTES.snapshots, icon: Table2 },
] as const;

/** The Shared module. One item today; the group hub is reached from it. */
export const SHARED_GROUP = [{ key: 'groups', href: ROUTES.shared, icon: Users }] as const;

/*
 * Bell belongs to Notifications, and Alerts & Limits takes Gauge — it configures dashboard health
 * INDICATORS and account caps, so a bell there was promising something it never did.
 */
export const SETTINGS_GROUP = [
  { key: 'account', href: ROUTES.account, icon: UserCog },
  { key: 'preferences', href: ROUTES.preferences, icon: SlidersHorizontal },
  { key: 'alerts', href: ROUTES.alerts, icon: Gauge },
  { key: 'notifications', href: ROUTES.notifications, icon: Bell },
  { key: 'localization', href: ROUTES.localization, icon: Globe },
  { key: 'data', href: ROUTES.data, icon: ArrowDownUp },
  { key: 'integrations', href: ROUTES.integrations, icon: Puzzle },
] as const;

/*
 * Admin-only group (rendered only when the user is an admin). Items can be gated further:
 * invitePeople is only relevant in invite mode (in open mode anyone signs up, so there's no one to
 * invite).
 */
export const ADMIN_GROUP = [
  { key: 'invitePeople', href: ROUTES.admin, icon: UserPlus, inviteOnly: true },
  { key: 'feedback', href: ROUTES.adminFeedback, icon: Inbox, inviteOnly: false },
] as const;

/*
 * Every nav key the sidebar renders, in one list, for the parity test that asserts each one resolves
 * to a `sidebar.nav.*` label in both locales.
 *
 * The four literals are the items that are not part of a group: the global quick-add above the nav,
 * the top-level Dashboard, and the two in the footer's Support group (one link and one dialog action).
 * They are listed by hand because they are rendered by hand — and listing them here is what keeps them
 * inside the guard.
 */
export const SIDEBAR_NAV_KEYS: string[] = [
  'quickAdd',
  'dashboard',
  'help',
  'sendFeedback',
  ...FINANCES_GROUP.map((item) => item.key),
  ...COMMITMENTS_GROUP.map((item) => item.key),
  ...PORTFOLIO_GROUP.map((item) => item.key),
  ...SHARED_GROUP.map((item) => item.key),
  ...SETTINGS_GROUP.map((item) => item.key),
  ...ADMIN_GROUP.map((item) => item.key),
];
