import { NotFoundContent } from '@/app/_components/not-found-content';

// A `notFound()` from an app page (an id that is not the reader's, an admin page for a non-admin).
// Rendered inside the protected layout, whose `main` holds it — the root not-found brings its own
// `main`, and rendered here it would be a second one. Every visitor here is signed in.
export default function ProtectedNotFound() {
  return <NotFoundContent isAuthenticated />;
}
