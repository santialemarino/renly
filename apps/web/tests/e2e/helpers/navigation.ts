import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { expect, type Page, type Request } from '@playwright/test';

import {
  COMMITMENTS_GROUP,
  FINANCES_GROUP,
  PORTFOLIO_GROUP,
  SETTINGS_GROUP,
  SHARED_GROUP,
} from '@/config/nav';
import { ROUTES } from '@/config/routes';
import { WEB_ROOT } from './list-pages';

/*
 * What the navigation specs share: the sidebar's destinations (derived from `config/nav.ts`, which is
 * what the sidebar renders), a way to make a navigation slow on purpose, and a frame sampler that
 * records what `<main>`, the progress bar and the nav show on every animation frame from the click on.
 */

export const NAV_TIMEOUT = 30_000;
export const PROGRESS_BAR = 'navigation-pending-bar';

// Every page the sidebar links to for a regular account (the admin group needs an admin session).
export function sidebarRoutes(): string[] {
  return [
    ROUTES.dashboard,
    ...[FINANCES_GROUP, COMMITMENTS_GROUP, PORTFOLIO_GROUP, SHARED_GROUP, SETTINGS_GROUP].flatMap(
      (group) => group.map((item) => item.href),
    ),
  ];
}

/*
 * Every dismissible hint's storage key in the app: every `'…-dismissed'` string literal, the one naming
 * convention the keys share, so a hint whose key lives in a constant is found like an inline one.
 */
function allHintKeys(): string[] {
  const keys = new Set<string>();
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      const full = join(dir, entry);
      if (entry === 'node_modules' || entry.startsWith('.')) continue;
      if (statSync(full).isDirectory()) walk(full);
      else if (entry.endsWith('.tsx')) {
        for (const match of readFileSync(full, 'utf8').matchAll(
          /['"]([a-z0-9-]+-dismissed)['"]/g,
        )) {
          keys.add(match[1]!);
        }
      }
    }
  };
  walk(join(WEB_ROOT, 'app'));
  walk(join(WEB_ROOT, 'components'));
  return [...keys];
}

// Dismisses every hint before the page loads (a hint reveals with a height animation after load).
export async function dismissAllHints(page: Page) {
  const keys = allHintKeys();
  expect(keys.length, 'found no hint keys to dismiss').toBeGreaterThan(3);
  await page.addInitScript((list) => {
    for (const key of list) localStorage.setItem(key, 'true');
  }, keys);
}

// The sidebar's link to `href` (the desktop column; below `md` the same links live in the Sheet).
export function sidebarLink(page: Page, href: string) {
  return page.locator(`[data-testid="sidebar-nav"] a[href="${href}"]`);
}

// Opens every collapsed group in the sidebar, so each destination has a link on screen to click.
export async function openNavGroups(page: Page) {
  for (let pass = 0; pass < 4; pass += 1) {
    const closed = page.locator('[data-sidebar="sidebar"] button[aria-expanded="false"]');
    const count = await closed.count();
    if (count === 0) return;
    for (let i = 0; i < count; i += 1) await closed.first().click();
  }
}

// Loads `route` and waits for its own content: a heading in `<main>`.
export async function openPage(page: Page, route: string) {
  await page.goto(route);
  await expect(page.locator('main h1').first()).toBeVisible({ timeout: NAV_TIMEOUT });
}

// The request that carries a navigation's page (the client router's fetch or a document load), not a
// prefetch.
function isNavigationTo(request: Request, path: string): boolean {
  const headers = request.headers();
  return (
    new URL(request.url()).pathname === path &&
    !headers['next-router-prefetch'] &&
    (headers['rsc'] === '1' || request.resourceType() === 'document')
  );
}

// Holds every navigation to `path` back by `ms` before it reaches the server.
export async function delayNavigationTo(page: Page, path: string, ms: number) {
  await page.route(
    (url) => url.pathname === path,
    async (route) => {
      // A plain timer, not `page.waitForTimeout`, which throws once the test has ended mid-hold.
      if (isNavigationTo(route.request(), path)) await new Promise((done) => setTimeout(done, ms));
      await route.continue().catch(() => undefined);
    },
  );
}

/*
 * Holds every navigation to `path` until the returned `release` is called, so a test can assert what
 * the page shows while it waits for as long as that takes, rather than racing a fixed hold. Call
 * `release` in a `finally`: a request still held when the test ends keeps its route open.
 */
export async function holdNavigationTo(page: Page, path: string): Promise<() => void> {
  let release = () => {};
  const released = new Promise<void>((done) => (release = done));
  await page.route(
    (url) => url.pathname === path,
    async (route) => {
      if (isNavigationTo(route.request(), path)) await released;
      await route.continue().catch(() => undefined);
    },
  );
  return release;
}

// One sampled frame, timed from the click.
export interface Frame {
  t: number;
  // Text of the page that was on screen before the click is visible.
  old: boolean;
  // Text of the next page is visible.
  fresh: boolean;
  // `<main>`'s rendered text, recorded only on the frames where it changed (null on the others).
  text: string | null;
  bar: boolean;
  busy: boolean;
  // The hrefs of the sidebar items drawn as active.
  active: string[];
}

export interface Sample {
  frames: Frame[];
  // Layout shifts after the click (excluding ones caused by input), as their scores.
  shifts: number[];
}

/*
 * Starts sampling: marks everything now in `<main>` as the old page, then records one `Frame` per
 * animation frame. Call `markClick` right before the click (the frames are timed from it) and
 * `stopSampling` to read them.
 */
export async function startSampling(page: Page) {
  await page.evaluate(() => {
    type Window = typeof window & { __navSample?: unknown };
    const main = document.querySelector('main')!;
    for (const element of main.querySelectorAll('*')) element.setAttribute('data-nav-old', '');
    // An element showing text of its own, laid out and not hidden.
    const showsText = (element: Element) =>
      [...element.childNodes].some(
        (node) => node.nodeType === Node.TEXT_NODE && node.textContent!.trim() !== '',
      ) &&
      element.getClientRects().length > 0 &&
      element.checkVisibility({ opacityProperty: true, visibilityProperty: true });
    const state = {
      t0: Number.POSITIVE_INFINITY,
      running: true,
      frames: [] as unknown[],
      shifts: [] as { t: number; value: number }[],
      lastText: '',
    };
    (window as Window).__navSample = state;
    const frame = () => {
      if (!state.running) return;
      const current = document.querySelector('main');
      let old = false;
      let fresh = false;
      for (const element of current?.querySelectorAll('*') ?? []) {
        if (old && fresh) break;
        const isOld = element.hasAttribute('data-nav-old');
        if (isOld ? old : fresh) continue;
        if (showsText(element)) {
          if (isOld) old = true;
          else fresh = true;
        }
      }
      const text = current?.innerText ?? '';
      const changed = text !== state.lastText;
      state.lastText = text;
      state.frames.push({
        t: performance.now() - state.t0,
        old,
        fresh,
        text: changed ? text : null,
        bar: document.querySelector('[data-testid="navigation-pending-bar"]') !== null,
        busy: current?.getAttribute('aria-busy') === 'true',
        active: [
          ...document.querySelectorAll('[data-testid="sidebar-nav"] a[data-active="true"]'),
        ].map((link) => link.getAttribute('href')),
      });
      requestAnimationFrame(frame);
    };
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries() as (PerformanceEntry & {
        value: number;
        hadRecentInput: boolean;
      })[]) {
        if (!entry.hadRecentInput) state.shifts.push({ t: entry.startTime, value: entry.value });
      }
    }).observe({ type: 'layout-shift' });
    requestAnimationFrame(frame);
  });
}

// Sets the moment the frames are timed from (call it right before the click).
export async function markClick(page: Page) {
  await page.evaluate(() => {
    (window as typeof window & { __navSample: { t0: number } }).__navSample.t0 = performance.now();
  });
}

export async function stopSampling(page: Page): Promise<Sample> {
  return page.evaluate(() => {
    const state = (
      window as typeof window & {
        __navSample: {
          t0: number;
          running: boolean;
          frames: Frame[];
          shifts: { t: number; value: number }[];
        };
      }
    ).__navSample;
    state.running = false;
    return {
      frames: state.frames.filter((frame) => frame.t >= 0),
      shifts: state.shifts.filter((shift) => shift.t >= state.t0).map((shift) => shift.value),
    };
  });
}

// `<main>`'s text on every frame from `from` on (the frames record it only where it changed).
export function textsFrom(frames: Frame[], from: number): string[] {
  let text = '';
  for (const frame of frames.slice(0, from + 1)) if (frame.text !== null) text = frame.text;
  const texts = [text];
  for (const frame of frames.slice(from + 1)) if (frame.text !== null) texts.push(frame.text);
  return texts;
}

// The first frame showing the next page, or -1.
export function swapIndex(frames: Frame[]): number {
  return frames.findIndex((frame) => frame.fresh);
}
