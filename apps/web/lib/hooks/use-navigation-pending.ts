'use client';

import { createContext, useContext } from 'react';

/*
 * What the protected shell knows about the navigation in flight (`NavigationPendingProvider` holds it):
 * the page it is going to, whether it has run long enough to show, and how to report one that a click
 * does not reveal — a programmatic push (`usePendingRouter`).
 */
export interface NavigationPendingState {
  // The destination's path while a navigation to another page runs, so the nav can show it as current
  // on the click itself; null otherwise.
  pendingPathname: string | null;
  // Past `NAVIGATION_PENDING_DELAY_MS` and still running: the progress bar shows.
  showProgress: boolean;
  // As `showProgress`, for a navigation to another page: the old page dims and is busy.
  busy: boolean;
  // Reports a navigation to `href` about to start, returning its id for `settle`.
  begin: (href: string) => number;
  // The navigation `id` ended without moving the URL (its transition finished in place).
  settle: (id: number) => void;
}

// Outside the protected shell (the sign-in pages) there is no shell to show anything in: a no-op.
const OUTSIDE_SHELL: NavigationPendingState = {
  pendingPathname: null,
  showProgress: false,
  busy: false,
  begin: () => -1,
  settle: () => undefined,
};

export const NavigationPendingContext = createContext<NavigationPendingState>(OUTSIDE_SHELL);

export function useNavigationPending(): NavigationPendingState {
  return useContext(NavigationPendingContext);
}
