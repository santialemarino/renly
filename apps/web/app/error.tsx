'use client';

import { ErrorState } from '@/components/error-state';
import { useReportBoundaryError } from '@/lib/hooks/use-report-boundary-error';

interface RootErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

/*
 * The boundary for what the root layout wraps that no nearer boundary can catch: the three route-group
 * LAYOUTS themselves. A segment's own error.tsx sits inside its layout, so a failure in, say, the
 * protected layout lands here rather than in `(protected)/error.tsx`. The root layout still renders
 * around it, so the copy is translated and `<html lang>` is set; there is no nav, hence the home link.
 */
export default function RootError({ error, reset }: RootErrorProps) {
  useReportBoundaryError(error);

  // The group layouts are what render `<main>`, and a failure above them takes theirs with it.
  return (
    <main className="flex flex-col min-h-screen">
      <ErrorState reset={reset} showHomeLink />
    </main>
  );
}
