import { ALL_ROUTE_PATHS } from '@/config/routes';

// A host that can never resolve (`.invalid` is reserved), used only to make a relative path parseable.
// Its origin is never returned, and an input naming it explicitly fails the leading-slash check.
const PARSE_BASE = 'https://renly.invalid';

/*
 * Resolves a `?next=` parameter to a path that is safe to redirect to after login, or null.
 *
 * Three checks, each of which is what actually stops something — no belt-and-braces duplicates, so a
 * later reader can trust that removing any one of them opens a hole (each has a test that proves it):
 *
 *   1. It must start with `/`. This is what rejects a scheme of any kind — `https://evil.example/…`,
 *      `javascript:`, `data:` — including an absolute URL naming this app's own host.
 *   2. Resolved against a constant base, its origin must still be that base. This is what rejects the
 *      host-borrowing forms that DO start with a slash: `//evil.example`, and `/\evil.example`, which
 *      the URL parser normalises to the same thing.
 *   3. Its pathname must be a route this app declares. An allowlist, so a plausible-looking path does
 *      not qualify and widening what is accepted means adding a real route.
 *
 * What comes back is the PARSED `pathname + search`, never the input string: the path is normalised
 * (so `/a/../dashboard` cannot smuggle a non-route segment past check 3) and a fragment is dropped.
 * The query survives because the join link's token lives there.
 */
export function safeNextPath(next: string | undefined): string | null {
  if (!next || !next.startsWith('/')) return null;

  let url: URL;
  try {
    url = new URL(next, PARSE_BASE);
  } catch {
    return null;
  }
  if (url.origin !== PARSE_BASE) return null;
  // Widened to string[] because ROUTES is `as const`, so ALL_ROUTE_PATHS is a literal union and
  // `.includes` would reject any runtime string. Same cast PROTECTED_ROUTES uses in config/routes.ts.
  if (!(ALL_ROUTE_PATHS as readonly string[]).includes(url.pathname)) return null;
  return `${url.pathname}${url.search}`;
}
