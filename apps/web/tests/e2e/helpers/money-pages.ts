/*
 * Which pages the money overflow sweep visits, keyed by the route PATTERN of their `page.tsx` (the
 * folder path under `app/(protected)`, dynamic segments included).
 *
 * Pure data, no Playwright import, because a unit test reads it too:
 * `tests/unit/money-sweep-coverage.test.ts` derives the money-bearing pages from the source — every
 * page whose own components render a figure through `MoneyFigure` or a component that does — and fails
 * unless each one is either swept here or skipped here with its reason. So a new page that shows money
 * cannot quietly sit outside the sweep.
 */

// Swept pages. Each must show at least one figure once the sweep's seed exists, and the sweep fails if
// one does not — a page with nothing marked is a page the sweep is not actually checking.
export const MONEY_SWEEP_ROUTES = [
  '/accounts',
  '/accounts/[id]',
  '/credit-cards',
  '/dashboard',
  '/expenses',
  '/finance-dashboard',
  '/income',
  '/installments',
  '/investor-dashboard',
  '/payment-obligations',
  '/payments-calendar',
  '/snapshots',
  '/subscriptions',
] as const;

export type MoneySweepRoute = (typeof MONEY_SWEEP_ROUTES)[number];

// Money-bearing pages the sweep does not visit, each with the reason — never silently.
export const MONEY_SWEEP_SKIPS: Record<string, string> = {
  '/investments':
    'its section rows render TableSectionRow, whose totals are empty for holdings (a holding has no money column on the list), so the page shows no figure to check',
  '/shared/[groupId]':
    'needs a group with shared money in it; seeding one means a second member and a settlement flow, which is its own fixture',
  '/shared/pots/[id]': 'needs a pot, which needs a group — same fixture as /shared/[groupId]',
};

// The pages that draw a donut, whose legend names must not be cut off either. A subset of the swept
// pages, so the legend check rides the same visit.
export const LEGEND_ROUTES: readonly MoneySweepRoute[] = [
  '/dashboard',
  '/finance-dashboard',
  '/investor-dashboard',
];

// 320 is the narrowest phone still in use, 360 and 390 common ones, 768 the tablet edge where the
// sidebar appears, 1024 the width the defect was measured at, 1280/1440 laptops and 1920 a desktop.
export const SWEEP_WIDTHS = [320, 360, 390, 768, 1024, 1280, 1440, 1920] as const;
