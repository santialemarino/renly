import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { Page } from '@/lib/api/types';
import { useExpandablePagedList } from '@/lib/hooks/use-expandable-paged-list';

/*
 * The paged list behind every expandable table row (a card's settlements, an account's transfers and
 * reconciliations). Three hand-written copies of it drifted, and one of the drifts stranded a panel:
 * a failed first load was recorded as loaded, so the panel showed its empty state for good and
 * closing and reopening it never asked again. What is pinned is the retry, plus the cache it must not
 * break: a re-expand after a SUCCESSFUL load serves what is already there. Now that the hook is the only
 * place they live, its two timing promises are pinned too: the last requested page wins, and the
 * display floor pads the first load only.
 */

const ROWS: Page<string> = { items: ['a', 'b'], total: 2, pageSize: 25 };

// Lets the fetch settle, then moves the clock past the first-load display floor.
async function settle() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(600);
  });
}

function renderPanel(fetchPage: (page: number) => Promise<Page<string>>) {
  return renderHook(({ expanded }) => useExpandablePagedList({ expanded, fetchPage }), {
    initialProps: { expanded: false },
  });
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('useExpandablePagedList', () => {
  it('asks again on the next expand after a failed first load', async () => {
    const fetchPage = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue(ROWS);
    const panel = renderPanel(fetchPage);

    panel.rerender({ expanded: true });
    await settle();
    expect(fetchPage).toHaveBeenCalledTimes(1);
    expect(panel.result.current.loading).toBe(false);
    expect(panel.result.current.total).toBe(0);

    panel.rerender({ expanded: false });
    panel.rerender({ expanded: true });
    await settle();
    expect(fetchPage).toHaveBeenCalledTimes(2);
    expect(panel.result.current.items).toEqual(ROWS.items);
    expect(panel.result.current.total).toBe(2);
  });

  it('serves a loaded list on re-expand without fetching it again', async () => {
    const fetchPage = vi.fn().mockResolvedValue(ROWS);
    const panel = renderPanel(fetchPage);

    panel.rerender({ expanded: true });
    await settle();
    panel.rerender({ expanded: false });
    panel.rerender({ expanded: true });
    await settle();
    expect(fetchPage).toHaveBeenCalledTimes(1);
    expect(panel.result.current.items).toEqual(ROWS.items);
  });

  it('re-reads the current page after invalidate()', async () => {
    const fetchPage = vi.fn().mockResolvedValue(ROWS);
    const panel = renderPanel(fetchPage);

    panel.rerender({ expanded: true });
    await settle();
    act(() => panel.result.current.invalidate());
    await settle();
    expect(fetchPage).toHaveBeenCalledTimes(2);
    expect(fetchPage).toHaveBeenLastCalledWith(1);
  });

  it('shows the last REQUESTED page when two page fetches resolve out of order', async () => {
    let resolvePage2: (page: Page<string>) => void = () => {};
    const fetchPage = vi.fn((page: number) =>
      page === 2
        ? new Promise<Page<string>>((resolve) => (resolvePage2 = resolve))
        : Promise.resolve({ ...ROWS, items: [`p${page}`] }),
    );
    const panel = renderPanel(fetchPage);

    panel.rerender({ expanded: true });
    await settle();
    act(() => panel.result.current.setPage(2));
    act(() => panel.result.current.setPage(3));
    await settle();
    await act(async () => resolvePage2({ ...ROWS, items: ['p2'] }));
    await settle();
    expect(panel.result.current.page).toBe(3);
    expect(panel.result.current.items).toEqual(['p3']);
  });

  it('applies the display floor to the first load only, not to a page change', async () => {
    const fetchPage = vi.fn((page: number) => Promise.resolve({ ...ROWS, items: [`p${page}`] }));
    const panel = renderPanel(fetchPage);

    panel.rerender({ expanded: true });
    await settle();
    act(() => panel.result.current.setPage(2));
    // Well under the 500 ms floor: a padded swap would still be loading here.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(panel.result.current.loading).toBe(false);
    expect(panel.result.current.items).toEqual(['p2']);
  });
});
