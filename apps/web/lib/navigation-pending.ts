/*
 * The navigation in flight, as plain data: which URL it left, where it is going, and whether it changes
 * page or only the query. `NavigationPendingProvider` holds one and these functions move it along; they
 * are pure so the rules can be tested without a browser.
 *
 * A navigation is over when the URL the app has COMMITTED moves off the one it left — whether it landed
 * where it was going, was redirected elsewhere, or ended on the error boundary. One the app abandons
 * without moving (a newer navigation back to the current URL, a programmatic one whose transition ended
 * in place) is settled explicitly.
 */

export interface PendingNavigation {
  id: number;
  // The committed URL (path + query) when it started.
  from: string;
  // Where it is going (path + query).
  to: string;
  // The destination is another page, not the same one with another query.
  page: boolean;
}

// The modifier and button state a click carries, as `MouseEvent` has it.
export interface ClickLike {
  button: number;
  metaKey: boolean;
  ctrlKey: boolean;
  shiftKey: boolean;
  altKey: boolean;
}

// The bits of an anchor a click is judged by, as `HTMLAnchorElement` has them.
export interface AnchorLike {
  href: string;
  target: string;
  hasAttribute(name: string): boolean;
}

/*
 * A URL's path + query, the form every pending navigation is compared in. The query is re-serialised
 * the way the router's own `useSearchParams().toString()` writes it, so a link written `?q=a,b` or
 * `?q=a%20b` compares equal to the committed `?q=a%2Cb` / `?q=a+b` it lands on.
 */
export function pathAndQuery(url: URL): string {
  const query = new URLSearchParams(url.search).toString();
  return query ? `${url.pathname}?${query}` : url.pathname;
}

// The path part of a path + query.
export function pathOf(pathAndQueryValue: string): string {
  const query = pathAndQueryValue.indexOf('?');
  return query === -1 ? pathAndQueryValue : pathAndQueryValue.slice(0, query);
}

/*
 * Where a click on `anchor` takes the app, as a path + query, or null when it is not an in-app
 * navigation: another button, a modifier (new tab or window, download), a target other than this tab, a
 * `download` link, another origin, or a link that only changes the hash (an in-page jump, which never
 * leaves the page). `current` is the page's own location.
 */
export function linkDestination(click: ClickLike, anchor: AnchorLike, current: URL): string | null {
  if (click.button !== 0 || click.metaKey || click.ctrlKey || click.shiftKey || click.altKey) {
    return null;
  }
  if ((anchor.target && anchor.target !== '_self') || anchor.hasAttribute('download')) return null;
  let url: URL;
  try {
    url = new URL(anchor.href, current);
  } catch {
    return null;
  }
  if (url.origin !== current.origin) return null;
  if (url.hash && pathAndQuery(url) === pathAndQuery(current)) return null;
  return pathAndQuery(url);
}

/*
 * A navigation from the committed URL `from` to `to` begins. One to the URL already committed is no
 * navigation to wait for, but it is the newest one, so it ends whatever was pending (null).
 */
export function beginNavigation(id: number, from: string, to: string): PendingNavigation | null {
  if (to === from) return null;
  return { id, from, to, page: pathOf(to) !== pathOf(from) };
}

// The navigation `id` was abandoned where it started: it ends, unless a newer one has replaced it.
export function settleNavigation(
  pending: PendingNavigation | null,
  id: number,
): PendingNavigation | null {
  return pending?.id === id ? null : pending;
}

// The pending navigation, if it is still running at the committed URL `current`.
export function activeNavigation(
  pending: PendingNavigation | null,
  current: string,
): PendingNavigation | null {
  return pending && pending.from === current ? pending : null;
}
