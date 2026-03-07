export { auth as proxy } from './auth';

export const config = {
  // Run on all routes except Next.js internals, static files, and NextAuth API routes
  matcher: [
    '/((?!_next/static|_next/image|favicon.ico|api/auth|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)',
  ],
};
