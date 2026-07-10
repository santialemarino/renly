import type { OnboardingStatus } from '@/lib/api/onboarding';
import type { SettingsData } from '@/lib/api/settings';

/*
 * Whether to show a first-run teaching empty state: the section is empty, no filter/search is
 * hiding existing rows, and the user hasn't completed onboarding. Fails closed on a settings-load
 * error (null) so a transient failure doesn't flash the newbie state at an established user — the
 * same bias the dashboard welcome uses.
 */
export function isFirstRunEmptyState(
  isEmpty: boolean,
  hasActiveFilters: boolean,
  settings: Pick<SettingsData, 'onboardingCompleted'> | null,
): boolean {
  return isEmpty && !hasActiveFilters && !!settings && settings.onboardingCompleted !== true;
}

/*
 * The "first-run newcomer with no core data yet" signal shared by the UX-7 reduced sidebar and the
 * UX-8 welcome-tour auto-start — a single definition so the two features can't drift on what "core
 * data" means. Fails closed: a null status (fetch failed) is NOT treated as a newcomer, so a
 * transient outage never reduces an established user's sidebar or re-triggers the tour.
 */
export function hasNoCoreData(status: OnboardingStatus | null): boolean {
  return !!status && !status.hasInvestments && !status.hasFinances;
}
