'use client';

import { useEffect } from 'react';
import * as Sentry from '@sentry/nextjs';

/*
 * Reports an error an error boundary caught, and only the ones nothing else has reported.
 *
 * A boundary that catches an error also stops it reaching the window's error handler, which is where
 * the browser SDK would otherwise have seen it — so without this, adding a boundary silently takes
 * every client-side render error out of Sentry. An error thrown on the SERVER arrives here carrying a
 * `digest`, and `onRequestError` in `instrumentation.ts` has already reported it there; capturing it
 * again would count every server failure twice.
 */
export function useReportBoundaryError(error: Error & { digest?: string }) {
  useEffect(() => {
    if (error.digest) return;
    Sentry.captureException(error);
  }, [error]);
}
