import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  NavigationPendingProvider,
  NavigationProgressBar,
  PendingMain,
} from '@/app/(protected)/_components/navigation-pending';
import { NAVIGATION_PENDING_DELAY_MS } from '@/lib/constants/animations';
import { useNavigationPending } from '@/lib/hooks/use-navigation-pending';
import { usePendingRouter } from '@/lib/hooks/use-pending-router';

/*
 * The navigation feedback as the shell wires it: a link click (or back/forward, or a programmatic push)
 * turns the destination active at once, the progress bar and the busy, dimmed `<main>` come only after
 * `NAVIGATION_PENDING_DELAY_MS`, and all of it ends in the render where the URL commits. The router is a
 * stand-in whose committed URL the test moves by hand, the way Next commits a navigation.
 */

const router = vi.hoisted(() => ({
  url: { pathname: '/expenses', search: '' },
  push: vi.fn(),
  replace: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  usePathname: () => router.url.pathname,
  useSearchParams: () => new URLSearchParams(router.url.search),
  useRouter: () => ({ push: router.push, replace: router.replace }),
}));

// Every destination the nav was told about, render by render.
const shownDestinations: (string | null)[] = [];

function Probe() {
  const { pendingPathname, showProgress, busy } = useNavigationPending();
  const { push } = usePendingRouter();
  shownDestinations.push(pendingPathname);
  return (
    <>
      <output data-testid="probe">{JSON.stringify({ pendingPathname, showProgress, busy })}</output>
      <button type="button" onClick={() => push('/shared/1')}>
        push
      </button>
    </>
  );
}

function Shell() {
  return (
    <NavigationPendingProvider>
      <NavigationProgressBar />
      <nav>
        <a href="/dashboard">dashboard</a>
        <a href="/income">income</a>
        <a href="/expenses">expenses</a>
        <a href="/expenses?page=2">page 2</a>
        <a href="/data.csv" download>
          download
        </a>
        <a href="#main-content">skip</a>
      </nav>
      <PendingMain>
        <Probe />
      </PendingMain>
    </NavigationPendingProvider>
  );
}

function state() {
  return JSON.parse(screen.getByTestId('probe').textContent ?? '{}') as {
    pendingPathname: string | null;
    showProgress: boolean;
    busy: boolean;
  };
}

// A link click as the browser dispatches it; the default action (a page load) is cancelled, as
// Next's `<Link>` does, so jsdom does not try to navigate.
function click(name: string, init: MouseEventInit = {}) {
  const link = screen.getByText(name);
  link.addEventListener('click', (event) => event.preventDefault(), { once: true });
  fireEvent.click(link, init);
}

// Commits a URL the way the router does when a navigation lands.
function commit(rerender: (ui: React.ReactElement) => void, pathname: string, search = '') {
  router.url = { pathname, search };
  rerender(<Shell />);
}

beforeEach(() => {
  vi.useFakeTimers();
  router.url = { pathname: '/expenses', search: '' };
  window.history.replaceState(null, '', '/expenses');
  router.push.mockClear();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('NavigationPendingProvider', () => {
  it('activates the destination on the click and shows progress only past the delay', () => {
    const { rerender } = render(<Shell />);
    click('dashboard');
    expect(state()).toEqual({ pendingPathname: '/dashboard', showProgress: false, busy: false });
    expect(screen.queryByTestId('navigation-pending-bar')).toBeNull();

    act(() => vi.advanceTimersByTime(NAVIGATION_PENDING_DELAY_MS - 1));
    expect(state().showProgress).toBe(false);
    act(() => vi.advanceTimersByTime(1));
    expect(state()).toEqual({ pendingPathname: '/dashboard', showProgress: true, busy: true });
    expect(screen.getByTestId('navigation-pending-bar')).toBeInTheDocument();
    const main = screen.getByRole('main');
    expect(main).toHaveAttribute('aria-busy', 'true');
    expect(main.className).toContain('opacity-60');
    expect(main.className).toContain('pointer-events-none');

    // The URL commits: everything goes in that same render, with no fade back.
    commit(rerender, '/dashboard');
    expect(state()).toEqual({ pendingPathname: null, showProgress: false, busy: false });
    expect(screen.queryByTestId('navigation-pending-bar')).toBeNull();
    expect(main).not.toHaveAttribute('aria-busy');
    expect(main.className).not.toContain('transition-opacity');
    expect(main.className).not.toContain('opacity-60');
  });

  it('shows nothing for a navigation that lands within the delay', () => {
    const { rerender } = render(<Shell />);
    click('dashboard');
    act(() => vi.advanceTimersByTime(NAVIGATION_PENDING_DELAY_MS / 2));
    commit(rerender, '/dashboard');
    act(() => vi.advanceTimersByTime(NAVIGATION_PENDING_DELAY_MS * 2));
    expect(state()).toEqual({ pendingPathname: null, showProgress: false, busy: false });
  });

  it('ends with the error boundary or a redirect as well: any move off the URL it left', () => {
    const { rerender } = render(<Shell />);
    click('dashboard');
    commit(rerender, '/login');
    expect(state().pendingPathname).toBeNull();
  });

  it('forgets a finished navigation, so returning to the URL it left does not revive it', () => {
    const { rerender } = render(<Shell />);
    click('dashboard');
    commit(rerender, '/dashboard');
    // Back where it started without a click the shell saw (a redirect, a bare router call).
    commit(rerender, '/expenses');
    act(() => vi.advanceTimersByTime(NAVIGATION_PENDING_DELAY_MS * 2));
    expect(state()).toEqual({ pendingPathname: null, showProgress: false, busy: false });
  });

  it('lets a newer click take over, and a click back to the current page end it', () => {
    render(<Shell />);
    click('dashboard');
    click('income');
    expect(state().pendingPathname).toBe('/income');
    click('expenses');
    act(() => vi.advanceTimersByTime(NAVIGATION_PENDING_DELAY_MS * 2));
    expect(state()).toEqual({ pendingPathname: null, showProgress: false, busy: false });
  });

  it('ignores clicks that do not navigate this tab', () => {
    render(<Shell />);
    click('dashboard', { metaKey: true });
    click('dashboard', { ctrlKey: true });
    click('dashboard', { shiftKey: true });
    click('download');
    click('skip');
    act(() => vi.advanceTimersByTime(NAVIGATION_PENDING_DELAY_MS * 2));
    expect(state()).toEqual({ pendingPathname: null, showProgress: false, busy: false });
  });

  it('gives a query-only navigation the bar but leaves the page and the nav alone', () => {
    const { rerender } = render(<Shell />);
    click('page 2');
    act(() => vi.advanceTimersByTime(NAVIGATION_PENDING_DELAY_MS));
    expect(state()).toEqual({ pendingPathname: null, showProgress: true, busy: false });
    commit(rerender, '/expenses', 'page=2');
    expect(state().showProgress).toBe(false);
  });

  it('follows back and forward', () => {
    const { rerender } = render(<Shell />);
    act(() => {
      window.history.pushState(null, '', '/income');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });
    expect(state().pendingPathname).toBe('/income');
    commit(rerender, '/income');
    expect(state().pendingPathname).toBeNull();
  });

  it('reports a programmatic push, and settles one whose transition ends without moving', () => {
    render(<Shell />);
    shownDestinations.length = 0;
    act(() => screen.getByText('push').click());
    expect(router.push).toHaveBeenCalledWith('/shared/1', undefined);
    // It was shown as the destination while it ran.
    expect(shownDestinations).toContain('/shared/1');
    // The stand-in router never commits, so the push's transition ends in place: settled, not stuck.
    act(() => vi.advanceTimersByTime(NAVIGATION_PENDING_DELAY_MS * 2));
    expect(state()).toEqual({ pendingPathname: null, showProgress: false, busy: false });
  });
});
