import { describe, expect, it } from 'vitest';

import type { OnboardingStatus } from '@/lib/api/onboarding';
import { hasCompletedCoreSteps, hasNoCoreData } from '@/lib/onboarding';

/*
 * The two predicates that decide what "this user has data" means: `hasNoCoreData` gates the reduced
 * first-run sidebar and the welcome-tour auto-start, `hasCompletedCoreSteps` gates the checklist's
 * positive finish. They are complements over the same two fields, and this file is what keeps them
 * that way — the checklist's non-gating steps are a product decision, so it needs a real guard rather
 * than a service-layer test (the API has no concept of gating at all).
 */
function status(overrides: Partial<OnboardingStatus> = {}): OnboardingStatus {
  return {
    hasInvestments: false,
    hasFinances: false,
    hasAccounts: false,
    primaryCurrencySet: false,
    sampleInvestments: false,
    sampleExpenses: false,
    sampleIncome: false,
    tourCompleted: false,
    ...overrides,
  };
}

describe('hasCompletedCoreSteps', () => {
  it('is false for a user who has done nothing', () => {
    expect(hasCompletedCoreSteps(status())).toBe(false);
  });

  it('needs both core steps, not either one', () => {
    expect(hasCompletedCoreSteps(status({ hasInvestments: true }))).toBe(false);
    expect(hasCompletedCoreSteps(status({ hasFinances: true }))).toBe(false);
    expect(hasCompletedCoreSteps(status({ hasInvestments: true, hasFinances: true }))).toBe(true);
  });

  /*
   * The load-bearing one. The account step is deliberately optional, so the finish must not wait on
   * it — requiring an account to complete onboarding would turn the net-worth headline's cash input
   * into a completeness demand, which the product holds. Adding `&& hasAccounts` to the predicate
   * fails here.
   */
  it('does not wait on the optional account step', () => {
    const done = status({ hasInvestments: true, hasFinances: true, hasAccounts: false });
    expect(hasCompletedCoreSteps(done)).toBe(true);
  });

  it('does not wait on the optional display-currency step', () => {
    const done = status({ hasInvestments: true, hasFinances: true, primaryCurrencySet: false });
    expect(hasCompletedCoreSteps(done)).toBe(true);
  });

  it('is not satisfied by an optional step alone', () => {
    expect(hasCompletedCoreSteps(status({ hasAccounts: true }))).toBe(false);
    expect(hasCompletedCoreSteps(status({ primaryCurrencySet: true }))).toBe(false);
  });

  // A failed status fetch must never claim the user is finished.
  it('fails closed on a null status', () => {
    expect(hasCompletedCoreSteps(null)).toBe(false);
  });
});

describe('hasNoCoreData', () => {
  // Deliberately excludes accounts, which is what keeps the checklist step optional: if an account
  // counted as core data here, the two predicates would disagree about the same user.
  it('reads the same two fields as the checklist finish, so the two cannot disagree', () => {
    const accountOnly = status({ hasAccounts: true });
    expect(hasNoCoreData(accountOnly)).toBe(true);
    expect(hasCompletedCoreSteps(accountOnly)).toBe(false);

    const coreDone = status({ hasInvestments: true, hasFinances: true });
    expect(hasNoCoreData(coreDone)).toBe(false);
    expect(hasCompletedCoreSteps(coreDone)).toBe(true);
  });

  // Fails closed the other way: a transient outage must not reduce an established user's sidebar.
  it('fails closed on a null status', () => {
    expect(hasNoCoreData(null)).toBe(false);
  });
});
