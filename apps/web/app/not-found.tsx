import { NotFoundContent } from '@/app/_components/not-found-content';
import { getSession, isAuthenticatedSession } from '@/lib/auth';

// Global 404 for unmatched routes. Reads the session on the server so the CTA can adapt — logged-in
// visitors also get a direct "Go to Dashboard" — while the animated UI lives in the client child.
export default async function NotFound() {
  const session = await getSession();
  const isAuthenticated = isAuthenticatedSession(session);

  return <NotFoundContent isAuthenticated={isAuthenticated} />;
}
