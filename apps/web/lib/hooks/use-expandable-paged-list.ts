'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import type { Page } from '@/lib/api/types';
import { LOADING_DISPLAY_FLOOR_MS } from '@/lib/constants/animations';
import { API_DEFAULT_PAGE_SIZE } from '@/lib/constants/api-constants';

interface UseExpandablePagedListOptions<R> {
  // Whether the panel is open. Nothing is fetched while it is closed.
  expanded: boolean;
  fetchPage: (page: number) => Promise<R>;
  // Bumped by a parent after a write lands, so an already-loaded panel re-reads its list.
  reloadToken?: number;
}

/*
 * The paged list inside an expandable table row: fetched on first expand, cached across a re-expand,
 * re-fetched on a page change, a bumped `reloadToken` or `invalidate()`.
 *
 * A monotonic ticket makes the LAST REQUESTED page win rather than the last response to arrive — two
 * pager clicks put two fetches in flight, and without it the slower one repaints over the newer, leaving
 * the pager and the rows describing different pages.
 *
 * The display floor pads every load except a page change. It stops a sub-perceptual flash: on the first
 * load, and on a reload of the same page (a bumped `reloadToken`, `invalidate()`, a retry), the panel
 * would otherwise swap its table for the loading line and back again too fast to read. A page change is
 * the user's own click, answered as fast as it lands; padding it would hold one line of text over the
 * table for half a second. `lastPageRef` answers "which page was last asked for", not the cache key,
 * because a failed load forgets the key.
 *
 * A failed load sets `failed` (the panel shows a retry rather than its empty line, which would claim the
 * list is empty) and forgets its cache key, so `invalidate()` or closing and reopening the panel asks
 * again instead of serving the failure for good.
 */
export function useExpandablePagedList<R extends Page<unknown>>({
  expanded,
  fetchPage,
  reloadToken = 0,
}: UseExpandablePagedListOptions<R>) {
  const [data, setData] = useState<R | null>(null);
  const [page, setPage] = useState(1);
  // Loading until the first fetch lands, so the panel's first frame is the loading line rather than an
  // empty state the list may not be in.
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [localToken, setLocalToken] = useState(0);
  // The `reloadToken:localToken:page` whose data is loaded (or loading); null until the first fetch.
  const loadedKeyRef = useRef<string | null>(null);
  // Monotonic ticket per fetch; only the newest one may commit its result.
  const requestRef = useRef(0);
  // The page the last load asked for; null until the first fetch.
  const lastPageRef = useRef<number | null>(null);
  const fetchPageRef = useRef(fetchPage);

  useEffect(() => {
    fetchPageRef.current = fetchPage;
  }, [fetchPage]);

  const load = useCallback(async (requestedPage: number, floored: boolean) => {
    const ticket = ++requestRef.current;
    setLoading(true);
    const start = Date.now();
    let result: R | null = null;
    try {
      result = await fetchPageRef.current(requestedPage);
    } catch {
      result = null;
    }
    const elapsed = Date.now() - start;
    if (floored && elapsed < LOADING_DISPLAY_FLOOR_MS) {
      await new Promise((r) => setTimeout(r, LOADING_DISPLAY_FLOOR_MS - elapsed));
    }
    if (ticket !== requestRef.current) return;
    if (result === null) loadedKeyRef.current = null;
    setData(result);
    setFailed(result === null);
    setLoading(false);
  }, []);

  useEffect(() => {
    if (!expanded) return;
    const key = `${reloadToken}:${localToken}:${page}`;
    if (loadedKeyRef.current === key) return;
    loadedKeyRef.current = key;
    const pageChange = lastPageRef.current !== null && lastPageRef.current !== page;
    lastPageRef.current = page;
    load(page, !pageChange);
  }, [expanded, reloadToken, localToken, page, load]);

  // Drops the cache so the open panel re-reads the current page — for a write made inside the panel, or
  // the retry after a failed load.
  const invalidate = useCallback(() => setLocalToken((token) => token + 1), []);

  return {
    data,
    items: (data?.items ?? []) as R['items'],
    total: data?.total ?? 0,
    pageSize: data?.pageSize ?? API_DEFAULT_PAGE_SIZE,
    page,
    setPage,
    loading,
    failed,
    invalidate,
  };
}
