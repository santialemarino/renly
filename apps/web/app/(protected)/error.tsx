'use client';

import { ErrorState } from '@/components/error-state';
import { useReportBoundaryError } from '@/lib/hooks/use-report-boundary-error';

interface ProtectedErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

/*
 * The boundary for every protected page. It sits INSIDE the protected layout, so a page whose read
 * failed keeps the sidebar, the mobile bar and the rest of the shell — the user can retry, or simply
 * go somewhere else. An error in the layout itself is caught one level up, by `app/error.tsx`.
 */
export default function ProtectedError({ error, reset }: ProtectedErrorProps) {
  useReportBoundaryError(error);

  return <ErrorState reset={reset} />;
}
