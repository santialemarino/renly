'use client';

import { useRef, useTransition } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

export type NavigateOverrides = Record<string, string | string[] | null>;

export interface UseSearchParamsNavigationOptions {
  // Drop the `page` param before applying overrides — for list pages whose filters reset pagination.
  resetPage?: boolean;
}

/*
 * URL-search-param navigation for list pages: merges overrides into the current query
 * string (null / '' / empty array delete the key; arrays append one entry per value)
 * and pushes the result inside a transition so tables can dim on `isPending` while
 * the server component refetches.
 */
export function useSearchParamsNavigation(
  route: string,
  options: UseSearchParamsNavigationOptions = {},
) {
  const router = useRouter();
  const searchParams = useSearchParams();
  // Ref keeps searchParams current inside debounced callbacks without adding it to effect dependency arrays.
  const searchParamsRef = useRef(searchParams);
  searchParamsRef.current = searchParams;
  const [isPending, startTransition] = useTransition();

  function navigate(overrides: NavigateOverrides) {
    const params = new URLSearchParams(searchParamsRef.current.toString());
    if (options.resetPage) params.delete('page');
    Object.entries(overrides).forEach(([key, val]) => {
      if (val === null || val === '' || (Array.isArray(val) && val.length === 0)) {
        params.delete(key);
      } else if (Array.isArray(val)) {
        params.delete(key);
        val.forEach((v) => params.append(key, v));
      } else {
        params.set(key, val);
      }
    });
    startTransition(() => router.push(`${route}?${params.toString()}`));
  }

  return { navigate, isPending };
}
