'use client';

import { ErrorState } from '@/components/error-state';
import { useReportBoundaryError } from '@/lib/hooks/use-report-boundary-error';

interface AuthErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

/*
 * The boundary for the auth pages. It renders inside the auth layout's centred column, so a failure
 * there still looks like the page it happened on. Those pages have no nav, hence the home link.
 */
export default function AuthError({ error, reset }: AuthErrorProps) {
  useReportBoundaryError(error);

  return <ErrorState reset={reset} showHomeLink />;
}
