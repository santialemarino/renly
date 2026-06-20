import * as Sentry from '@sentry/nextjs';

// Loads the runtime-specific Sentry config (server vs edge). Next.js calls this once per runtime.
export async function register() {
  if (process.env.NEXT_RUNTIME === 'nodejs') {
    await import('./sentry.server.config');
  }
  if (process.env.NEXT_RUNTIME === 'edge') {
    await import('./sentry.edge.config');
  }
}

// Reports errors thrown while rendering on the server (including nested RSCs) to Sentry.
export const onRequestError = Sentry.captureRequestError;
