import * as Sentry from '@sentry/nextjs';

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

// Server-side (Node runtime) Sentry init (INFRA-5). Disabled unless NEXT_PUBLIC_SENTRY_DSN is
// set, so local dev and CI builds send nothing; set the DSN — even on localhost — to capture errors.
Sentry.init({
  dsn,
  enabled: Boolean(dsn),
  environment: process.env.NODE_ENV,
  tracesSampleRate: 0,
});
