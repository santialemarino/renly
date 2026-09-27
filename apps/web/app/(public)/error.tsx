'use client';

import { ErrorState } from '@/components/error-state';
import { useReportBoundaryError } from '@/lib/hooks/use-report-boundary-error';

interface PublicErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

/*
 * The boundary for the public pages. It renders inside the public layout, between the site header
 * and footer, so the way home and to every other page stays exactly where it was.
 */
export default function PublicError({ error, reset }: PublicErrorProps) {
  useReportBoundaryError(error);

  return <ErrorState reset={reset} />;
}
