import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useReportBoundaryError } from '@/lib/hooks/use-report-boundary-error';

/*
 * Which caught errors reach Sentry. A boundary swallows the error before the browser SDK's global
 * handler can see it, so a client-side error is reported ONLY if this hook sends it — and a server-side
 * one, which arrives carrying a `digest`, was already reported by `onRequestError` and must not be sent
 * twice. Both directions are asserted, because each failure is silent.
 */

const sentry = vi.hoisted(() => ({ captureException: vi.fn() }));
vi.mock('@sentry/nextjs', () => sentry);

beforeEach(() => {
  sentry.captureException.mockClear();
});

describe('useReportBoundaryError', () => {
  it('reports a client-side error once', () => {
    const error = new Error('client render failed');
    renderHook(() => useReportBoundaryError(error));

    expect(sentry.captureException).toHaveBeenCalledTimes(1);
    expect(sentry.captureException).toHaveBeenCalledWith(error);
  });

  it('does not report a server-side error again', () => {
    const error = Object.assign(new Error('server render failed'), { digest: '1234567890' });
    renderHook(() => useReportBoundaryError(error));

    expect(sentry.captureException).not.toHaveBeenCalled();
  });
});
