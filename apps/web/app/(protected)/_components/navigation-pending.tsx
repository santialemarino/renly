'use client';

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { usePathname, useSearchParams } from 'next/navigation';

import { cn } from '@repo/ui/lib';
import { MAIN_CONTENT_ID } from '@/config/constants';
import {
  NAVIGATION_PENDING_DELAY_MS,
  NAVIGATION_PROGRESS_SWEEP_MS,
} from '@/lib/constants/animations';
import {
  NavigationPendingContext,
  useNavigationPending,
  type NavigationPendingState,
} from '@/lib/hooks/use-navigation-pending';
import {
  activeNavigation,
  beginNavigation,
  linkDestination,
  pathAndQuery,
  pathOf,
  settleNavigation,
  type PendingNavigation,
} from '@/lib/navigation-pending';

interface NavigationPendingProviderProps {
  children: React.ReactNode;
}

/*
 * The signed-in app's navigation feedback. There is no route loading state: a navigation keeps the old
 * page on screen until the new one is complete, then swaps it in at once. What answers the click is
 * this:
 *
 * - at once, the destination's nav item turns active (`pendingPathname`, read by the sidebar);
 * - past `NAVIGATION_PENDING_DELAY_MS`, a progress bar across the top of the main column and, for a
 *   change of page, the old page dimmed, busy and inert inside `<main>` only — the sidebar and its bell
 *   stay usable, so another click can take over. Both go on the swap. A faster navigation shows neither.
 *
 * It sees every in-app link click (captured on the document, so a `<Link>` anywhere counts with no
 * wiring), back and forward (`popstate`), and programmatic pushes reported through `usePendingRouter`.
 * Next has `useLinkStatus` for one link's own pending state, but nothing app-wide, so the click is read
 * here; a link whose click handler cancels the navigation must therefore be an in-page `#` link, which
 * this ignores (the pager and the skip link are). A navigation ends when the committed URL moves off the
 * one it left — on the new page, a redirect or the error boundary alike.
 */
export function NavigationPendingProvider({ children }: NavigationPendingProviderProps) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const query = searchParams.toString();
  const current = query ? `${pathname}?${query}` : pathname;

  const [pending, setPending] = useState<PendingNavigation | null>(null);
  const [shownId, setShownId] = useState<number | null>(null);
  const currentRef = useRef(current);
  const lastId = useRef(0);

  // Over the moment the URL commits, in the same render — the new page never paints dimmed.
  const active = activeNavigation(pending, current);
  const showProgress = active !== null && shownId === active.id;

  useLayoutEffect(() => {
    currentRef.current = current;
  }, [current]);

  const begin = useCallback((href: string) => {
    const id = ++lastId.current;
    const to = pathAndQuery(new URL(href, window.location.href));
    setPending(beginNavigation(id, currentRef.current, to));
    return id;
  }, []);

  const settle = useCallback((id: number) => {
    setPending((previous) => settleNavigation(previous, id));
  }, []);

  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      const anchor = (event.target as Element | null)?.closest?.('a[href]');
      if (!(anchor instanceof HTMLAnchorElement)) return;
      const to = linkDestination(event, anchor, new URL(window.location.href));
      if (to !== null) begin(to);
    };
    // By the time it fires the browser shows the destination's URL; the app has not committed it yet.
    const onPopState = () => begin(window.location.href);
    document.addEventListener('click', onClick, true);
    window.addEventListener('popstate', onPopState);
    return () => {
      document.removeEventListener('click', onClick, true);
      window.removeEventListener('popstate', onPopState);
    };
  }, [begin]);

  // A finished navigation is dropped, so the next one at this URL starts clean.
  useEffect(() => {
    if (pending && !active) setPending(null);
  }, [pending, active]);

  useEffect(() => {
    if (!active) return;
    const timer = setTimeout(() => setShownId(active.id), NAVIGATION_PENDING_DELAY_MS);
    return () => clearTimeout(timer);
  }, [active]);

  const value = useMemo<NavigationPendingState>(
    () => ({
      pendingPathname: active?.page ? pathOf(active.to) : null,
      showProgress,
      busy: active !== null && showProgress && active.page,
      begin,
      settle,
    }),
    [active, showProgress, begin, settle],
  );

  return (
    <NavigationPendingContext.Provider value={value}>{children}</NavigationPendingContext.Provider>
  );
}

/*
 * The thin bar across the top of the main column while a navigation runs past the delay. Brand blue,
 * the focus ring's. It sweeps across; under reduced motion it is a still, full-width line
 * (`.navigation-progress-fill` in `globals.css`). Zero height and sticky, so it rides the top of the viewport
 * over the column without taking room from it.
 */
export function NavigationProgressBar() {
  const { showProgress } = useNavigationPending();

  return (
    <div aria-hidden="true" className="sticky top-0 z-50 h-0">
      {showProgress && (
        <div className="relative h-0.5 overflow-hidden" data-testid="navigation-pending-bar">
          <div
            className="navigation-progress-fill absolute inset-y-0 left-0 w-1/3 bg-blue-800"
            style={{ animationDuration: `${NAVIGATION_PROGRESS_SWEEP_MS}ms` }}
          />
        </div>
      )}
    </div>
  );
}

interface PendingMainProps {
  children: React.ReactNode;
}

/*
 * The page's `<main>`. While a navigation to another page runs past the delay it is busy for assistive
 * tech, dimmed and takes no pointer input — the page is about to go, and a click on it would act on a
 * page the reader has already left. It dims with a short fade (none under reduced motion) and comes back
 * at once with the new page: the transition only exists while dimmed, so removing it is instant.
 */
export function PendingMain({ children }: PendingMainProps) {
  const { busy } = useNavigationPending();

  return (
    <main
      id={MAIN_CONTENT_ID}
      tabIndex={-1}
      aria-busy={busy || undefined}
      data-navigation-pending={busy || undefined}
      className={cn(
        'flex-1 flex flex-col min-w-0 overflow-x-hidden outline-none',
        busy &&
          'pointer-events-none opacity-60 transition-opacity duration-150 motion-reduce:transition-none',
      )}
    >
      {children}
    </main>
  );
}
