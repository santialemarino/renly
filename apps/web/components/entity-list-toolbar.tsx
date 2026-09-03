'use client';

import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { Archive, Plus } from 'lucide-react';
import { LayoutGroup, motion } from 'motion/react';

import { Button, Pill, SearchInput } from '@repo/ui/components';
import { ANIMATION_DEFAULT, DEBOUNCE_MS } from '@/lib/constants/animations';
import { useSearchParamsNavigation } from '@/lib/hooks/use-search-params-navigation';

interface EntityListToolbarProps {
  route: string;
  // Search/filter changes reset pagination on the paginated list pages (expenses/income/investments).
  resetPage?: boolean;
  searchAriaLabel: string;
  searchPlaceholder: string;
  // Renders the archived-toggle pill when provided.
  showArchivedLabel?: string;
  addLabel: string;
  onAdd: () => void;
  // Extra filter controls rendered in their own layout group between search and the trailing actions.
  filters?: React.ReactNode;
  // Extra trailing content rendered between the archived pill and the add button (e.g. the investments import link).
  trailing?: React.ReactNode;
  // Dialogs owned by the page toolbar, kept inside the LayoutGroup to match the current markup.
  children?: React.ReactNode;
}

// Shared list-page toolbar: debounced search, optional filter slot, optional archived
// pill, and the add button — each in its own animated layout group.
export function EntityListToolbar({
  route,
  resetPage = false,
  searchAriaLabel,
  searchPlaceholder,
  showArchivedLabel,
  addLabel,
  onAdd,
  filters,
  trailing,
  children,
}: EntityListToolbarProps) {
  const searchParams = useSearchParams();
  const { navigate } = useSearchParamsNavigation(route, { resetPage });
  const [search, setSearch] = useState(searchParams.get('search') ?? '');
  // Whether the debounce effect below is on its first, URL-matching run — see the note on it.
  const isMountRun = useRef(true);

  const showArchived = searchParams.get('show_archived') === 'true';

  /*
   * The debounced search, and the first run is SKIPPED deliberately.
   *
   * On mount `search` already equals what the URL says, so navigating would be a no-op — except for
   * `resetPage`, which deletes the `page` param. That made every full load of a URL beyond page one —
   * a bookmark, a shared link, a browser refresh — bounce back to page one 300ms after it rendered,
   * on all three paginated lists. Only a full load is affected: a client-side pager click leaves this
   * component mounted, so the effect never re-runs.
   */
  useEffect(() => {
    if (isMountRun.current) {
      isMountRun.current = false;
      return;
    }
    const timer = setTimeout(() => navigate({ search }), DEBOUNCE_MS);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  return (
    <LayoutGroup>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        {/*
         * `min-w-48` and not `min-w-0`, matching `SearchInput`'s own container minimum.
         *
         * The two have to agree or the flex item lies about how far it can shrink: the item would go
         * to 166px while the 192px input inside it kept its width and OVERFLOWED to the right, over
         * whatever filter control came next. Measured at 1440px once this toolbar carried a third
         * filter — a 14px overlap, with the input's background painting over the control's border.
         * With the minimum stated, the row wraps instead, which `flex-wrap` was already there for.
         */}
        <motion.div layout transition={{ duration: ANIMATION_DEFAULT }} className="min-w-48 flex-1">
          <SearchInput
            aria-label={searchAriaLabel}
            placeholder={searchPlaceholder}
            value={search}
            surface
            onChange={(e) => setSearch(e.target.value)}
            onClear={() => setSearch('')}
          />
        </motion.div>

        {filters && (
          <motion.div
            layout
            transition={{ duration: ANIMATION_DEFAULT }}
            className="flex flex-wrap items-center gap-x-3 gap-y-2 basis-full lg:basis-auto"
          >
            {filters}
          </motion.div>
        )}

        <motion.div
          layout
          transition={{ duration: ANIMATION_DEFAULT }}
          className="flex flex-wrap basis-full md:basis-auto items-center gap-x-3 gap-y-2"
        >
          {showArchivedLabel && (
            <Pill
              active={showArchived}
              aria-pressed={showArchived}
              onClick={() => navigate({ show_archived: showArchived ? null : 'true' })}
              className="min-w-fit flex-1"
            >
              <Archive className="size-4" />
              {showArchivedLabel}
            </Pill>
          )}
          {trailing}
          <Button blue onClick={onAdd} className="min-w-fit flex-1">
            <Plus className="size-4" />
            {addLabel}
          </Button>
        </motion.div>

        {children}
      </div>
    </LayoutGroup>
  );
}
