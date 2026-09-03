export { auth as proxy } from '@/auth';

export const config = {
  /*
   * Run on all routes except Next.js internals, static files, and NextAuth API routes.
   *
   * `sw.js` is excluded by name rather than by extension: it is the service worker, served from
   * `public/` at the origin root, and it must be fetchable in every auth state — a worker that got a
   * redirect to the login page would register as an HTML document and silently receive nothing.
   * It already falls through today (the gate only redirects on known protected routes), so this keeps
   * the auth middleware off a static file rather than fixing a break.
   */
  matcher: [
    '/((?!_next/static|_next/image|favicon.ico|sw.js|api/auth|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)',
  ],
};
