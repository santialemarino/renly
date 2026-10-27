import * as Sentry from '@sentry/nextjs';

import { internalApiSecretWarning } from '@/lib/internal-api-secret';

// Loads the runtime-specific Sentry config (server vs edge) and checks the server's own env once at
// startup. Next.js calls this once per runtime.
export async function register() {
  if (process.env.NEXT_RUNTIME === 'nodejs') {
    await import('./sentry.server.config');
    const secretWarning = internalApiSecretWarning(process.env.INTERNAL_API_SECRET);
    if (secretWarning) console.warn(secretWarning);
  }
  if (process.env.NEXT_RUNTIME === 'edge') {
    await import('./sentry.edge.config');
  }
}

// Reports errors thrown while rendering on the server (including nested RSCs) to Sentry.
export const onRequestError = Sentry.captureRequestError;
