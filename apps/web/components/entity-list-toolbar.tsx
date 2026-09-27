'use client';

import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { Archive, Plus } from 'lucide-react';
import { LayoutGroup, motion } from 'motion/react';

import { Button, Pill, SearchInput } from '@repo/ui/components';
import {
  TOOLBAR_ACTIONS,
  TOOLBAR_FILTERS,
  TOOLBAR_ITEM,
  TOOLBAR_ROW,
  TOOLBAR_SEARCH,
} from '@/components/entity-list-toolbar-layout';
import { ANIMATION_DEFAULT, DEBOUNCE_MS } from '@/lib/constants/animations';
import { SEARCH_MAX } from '@/lib/constants/api-constants';
import { useSearchParamsNavigation } from '@/lib/hooks/use-search-params-navigation';

/*
 * The add button, as one all-or-nothing group: a label with no handler (or the reverse) is a type error
 * rather than a button that silently fails to render. Left out entirely on a list that creates nothing
 * from its toolbar — the snapshots grid, whose rows come from the investments it lists.
 */
type EntityListToolbarAddProps =
  | {
      addLabel: string;
      onAdd: () => void;
      // Keeps the button on screen but inert — e.g. collections at their soft limit.
      addDisabled?: boolean;
    }
  | { addLabel?: never; onAdd?: never; addDisabled?: never };

type EntityListToolbarProps = EntityListToolbarAddProps & {
  route: string;
  // Search/filter changes reset pagination on the paginated list pages (expenses/income/investments).
  resetPage?: boolean;
  // Also the search field's ACCESSIBLE NAME — it has no visible label, so `SearchInput` requires a
  // placeholder and names itself from it rather than taking a second string that says the same thing.
  searchPlaceholder: string;
  // Renders the archived-toggle pill when provided.
  showArchivedLabel?: string;
  // Extra filter controls rendered in their own layout group between search and the trailing actions.
  filters?: React.ReactNode;
  // Extra trailing content rendered between the archived pill and the add button (e.g. the investments import link).
  trailing?: React.ReactNode;
  // Dialogs owned by the page toolbar, kept inside the LayoutGroup to match the current markup.
  children?: React.ReactNode;
};

/*
 * THE list-page toolbar: debounced search, optional filter slot, optional archived pill, trailing
 * actions and an optional add button — each in its own animated layout group.
 *
 * Every list page renders this rather than its own row, and `tests/unit/list-toolbar-ownership.test.ts`
 * fails otherwise. Two pages once hand-rolled a copy; each kept the pre-fix `min-w-0` search item after
 * the fix below landed here, which left the snapshots filters dead under the search input at 1024px.
 */
export function EntityListToolbar({
  route,
  resetPage = false,
  searchPlaceholder,
  showArchivedLabel,
  addLabel,
  onAdd,
  addDisabled,
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
      <div className={TOOLBAR_ROW} data-testid="entity-list-toolbar">
        {/*
         * `min-w-48` and not `min-w-0`, matching `SearchInput`'s own container minimum.
         *
         * The two have to agree or the flex item lies about how far it can shrink: the item would go
         * to 166px while the 192px input inside it kept its width and OVERFLOWED to the right, over
         * whatever filter control came next. Measured at 1440px once this toolbar carried a third
         * filter — a 14px overlap, with the input's background painting over the control's border.
         * With the minimum stated, the row wraps instead, which `flex-wrap` was already there for.
         */}
        <motion.div layout transition={{ duration: ANIMATION_DEFAULT }} className={TOOLBAR_SEARCH}>
          <SearchInput
            placeholder={searchPlaceholder}
            value={search}
            maxLength={SEARCH_MAX}
            surface
            onChange={(e) => setSearch(e.target.value)}
            onClear={() => setSearch('')}
          />
        </motion.div>

        {filters && (
          <motion.div
            layout
            transition={{ duration: ANIMATION_DEFAULT }}
            className={TOOLBAR_FILTERS}
          >
            {filters}
          </motion.div>
        )}

        <motion.div layout transition={{ duration: ANIMATION_DEFAULT }} className={TOOLBAR_ACTIONS}>
          {showArchivedLabel && (
            <Pill
              active={showArchived}
              aria-pressed={showArchived}
              onClick={() => navigate({ show_archived: showArchived ? null : 'true' })}
              className={TOOLBAR_ITEM}
            >
              <Archive className="size-4" />
              {showArchivedLabel}
            </Pill>
          )}
          {trailing}
          {/* One testid on the shared primitive, so every list page's add button is already
              reachable — the same rule ConfirmDialog's confirm button follows. */}
          {addLabel && (
            <Button
              blue
              onClick={onAdd}
              disabled={addDisabled}
              className={TOOLBAR_ITEM}
              data-testid="entity-list-add"
            >
              <Plus className="size-4" />
              {addLabel}
            </Button>
          )}
        </motion.div>

        {children}
      </div>
    </LayoutGroup>
  );
}
