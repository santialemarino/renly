'use client';

import { useSearchParams } from 'next/navigation';

import type { SortOrder } from '@/lib/api/types';
import {
  useSearchParamsNavigation,
  type NavigateOverrides,
  type UseSearchParamsNavigationOptions,
} from '@/lib/hooks/use-search-params-navigation';

/*
 * Sort state + the shared three-state header toggle (asc → desc → clear) for a table
 * backed by `sort_by` / `sort_order` search params. `resetPage` additionally clears
 * pagination on every sort change (the paginated tables).
 */
export function useTableSort<T extends string>(
  route: string,
  options: UseSearchParamsNavigationOptions = {},
) {
  const searchParams = useSearchParams();
  const { navigate, isPending } = useSearchParamsNavigation(route);

  const sortBy = (searchParams.get('sort_by') as T | null) ?? null;
  const sortOrder = (searchParams.get('sort_order') as SortOrder | null) ?? 'asc';

  function handleSortChange(column: T) {
    const pageReset: NavigateOverrides = options.resetPage ? { page: null } : {};
    if (sortBy === column) {
      if (sortOrder === 'asc') {
        navigate({ sort_by: column, sort_order: 'desc', ...pageReset });
      } else {
        navigate({ sort_by: null, sort_order: null, ...pageReset });
      }
    } else {
      navigate({ sort_by: column, sort_order: 'asc', ...pageReset });
    }
  }

  return { sortBy, sortOrder, handleSortChange, navigate, isPending };
}
