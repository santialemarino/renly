'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import type { Page } from '@/lib/api/types';
import { API_DEFAULT_PAGE_SIZE } from '@/lib/constants/api-constants';

// Minimum time (ms) from fetch start before the first result shows, so an instant resolve doesn't flash.
const DISPLAY_DELAY_MS = 500;

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
 * The display floor applies to the FIRST load only. It stops a sub-perceptual flash when the panel opens
 * with nothing on screen; on a page change the rows are already there, so padding the swap would replace
 * a real table with one line of text for half a second. `hasLoadedRef` answers "has anything landed",
 * not the cache key, because the effect records the key BEFORE it calls `load()`.
 *
 * A failed load forgets its cache key, so closing and reopening the panel asks again instead of serving
 * the empty result of the failure for good.
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
  const [localToken, setLocalToken] = useState(0);
  // The `reloadToken:localToken:page` whose data is loaded (or loading); null until the first fetch.
  const loadedKeyRef = useRef<string | null>(null);
  // Monotonic ticket per fetch; only the newest one may commit its result.
  const requestRef = useRef(0);
  const hasLoadedRef = useRef(false);
  const fetchPageRef = useRef(fetchPage);

  useEffect(() => {
    fetchPageRef.current = fetchPage;
  }, [fetchPage]);

  const load = useCallback(async (requestedPage: number) => {
    const ticket = ++requestRef.current;
    const isFirstLoad = !hasLoadedRef.current;
    setLoading(true);
    const start = Date.now();
    try {
      const result = await fetchPageRef.current(requestedPage);
      const elapsed = Date.now() - start;
      if (isFirstLoad && elapsed < DISPLAY_DELAY_MS) {
        await new Promise((r) => setTimeout(r, DISPLAY_DELAY_MS - elapsed));
      }
      if (ticket !== requestRef.current) return;
      setData(result);
    } catch {
      if (ticket !== requestRef.current) return;
      loadedKeyRef.current = null;
      setData(null);
    } finally {
      if (ticket === requestRef.current) {
        hasLoadedRef.current = true;
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    if (!expanded) return;
    const key = `${reloadToken}:${localToken}:${page}`;
    if (loadedKeyRef.current === key) return;
    loadedKeyRef.current = key;
    load(page);
  }, [expanded, reloadToken, localToken, page, load]);

  // Drops the cache so the open panel re-reads the current page — for a write made inside the panel.
  const invalidate = useCallback(() => setLocalToken((token) => token + 1), []);

  return {
    data,
    items: (data?.items ?? []) as R['items'],
    total: data?.total ?? 0,
    pageSize: data?.pageSize ?? API_DEFAULT_PAGE_SIZE,
    page,
    setPage,
    loading,
    invalidate,
  };
}
