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
