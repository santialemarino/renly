import { NotFoundContent } from '@/app/_components/not-found-content';
import { getSession, isAuthenticatedSession } from '@/lib/auth';

// Global 404 for unmatched routes. Reads the session on the server so the CTA can adapt — logged-in
// visitors also get a direct "Go to Dashboard" — while the animated UI lives in the client child.
// An unmatched URL renders under the root layout alone, so this is where its `main` comes from;
// without one the whole screen sat outside every landmark. A `notFound()` inside the app renders
// `(protected)/not-found.tsx` instead, inside that layout's own `main`.
export default async function NotFound() {
  const session = await getSession();
  const isAuthenticated = isAuthenticatedSession(session);

  return (
    <main>
      <NotFoundContent isAuthenticated={isAuthenticated} />
    </main>
  );
}
