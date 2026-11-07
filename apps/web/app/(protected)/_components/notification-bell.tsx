'use client';

import { useRef, useState, useTransition } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Bell } from 'lucide-react';
import { useTranslations } from 'next-intl';

import {
  Popover,
  PopoverContent,
  PopoverTrigger,
  Separator,
  Sheet,
  SheetContent,
  SheetTitle,
  SheetTrigger,
} from '@repo/ui/components';
import { useIsMobile } from '@repo/ui/hooks';
import { cn } from '@repo/ui/lib';
import {
  markAllNotificationsRead,
  markNotificationRead,
} from '@/app/(protected)/notifications/actions';
import { NotificationRow } from '@/components/notification-row';
import { ROUTES } from '@/config/routes';
import type { AppNotification } from '@/lib/api/notifications';

// The space between the sidebar's edge and the popover beside it, and the least it keeps from the
// viewport's edges when it has to shift to fit.
const POPOVER_GAP_PX = 8;
const POPOVER_COLLISION_PADDING_PX = 16;

const TRIGGER_CLASS =
  'group/bell relative grid size-8 shrink-0 place-items-center rounded-lg outline-none hover:bg-gray-100 focus-visible:bg-gray-100 focus-visible:ring-3 focus-visible:ring-ring transition-colors';

/*
 * How far right of the bell the popover must open for its left edge to clear the sidebar: the distance
 * from the bell to the sidebar's edge, plus the gap. Measured rather than assumed, because the bell's
 * inset inside the header is the header's padding, which a restyle can change without anyone thinking
 * of this popover.
 */
function offsetPastSidebar(trigger: HTMLElement): number {
  const sidebar = trigger.closest('[data-slot="sidebar-container"]');
  if (!sidebar) return POPOVER_GAP_PX;
  return (
    sidebar.getBoundingClientRect().right - trigger.getBoundingClientRect().right + POPOVER_GAP_PX
  );
}

interface NotificationBellProps {
  notifications: AppNotification[];
  unread: number;
}

/*
 * The always-visible way in: a bell beside the wordmark in the sidebar header, with a dot while
 * anything is unread, opening the most recent few.
 *
 * It lives in the sidebar HEADER rather than in a top bar because the app has no top bar — every
 * protected page owns its full vertical space and renders its own PageHeader, so a second persistent
 * band would stack two headers on twenty pages. The sidebar header is already the persistent shell.
 *
 * Where it opens follows the sidebar. On a desktop the sidebar is a column, and the popover opens to
 * its RIGHT, top-aligned with the bell and clear of the sidebar's edge — over the page the reader is
 * looking at, never straddling the column it came from. Below `md` the sidebar is itself a Sheet, so
 * the bell opens a full-width panel over it instead: a popover there would have the width of the menu
 * to work in.
 *
 * Its data comes from the protected LAYOUT, which is a server component: the count is correct on every
 * navigation and there is no polling. `router.refresh()` after a read is what re-asks for it.
 *
 * The unread marker is a DOT, not a number. A count implies a queue you are meant to empty, which is
 * the wrong relationship with a feed of things that already happened; the dot says "something is
 * there" and the panel says what.
 */
export function NotificationBell({ notifications, unread }: NotificationBellProps) {
  const t = useTranslations('notifications');

  const router = useRouter();
  const isMobile = useIsMobile();
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState(notifications);
  const [count, setCount] = useState(unread);
  const [sideOffset, setSideOffset] = useState(POPOVER_GAP_PX);
  const [isRefreshing, startTransition] = useTransition();
  const triggerRef = useRef<HTMLButtonElement>(null);

  // Measured on every open, so the popover follows the sidebar however it is laid out at the time.
  function handleOpenChange(next: boolean) {
    if (next && triggerRef.current) setSideOffset(offsetPastSidebar(triggerRef.current));
    setOpen(next);
  }

  // Un-awaited on purpose: it runs alongside the row's own navigation, which would cancel an awaited
  // Server Action before it settled. The catch is still required — an un-caught rejection is an error
  // nobody sees — and swallowing is the right recovery: losing one costs an unread dot, not data.
  function handleOpen(id: number) {
    setRows((current) =>
      current.map((item) =>
        item.id === id && item.readAt === null
          ? { ...item, readAt: new Date().toISOString() }
          : item,
      ),
    );
    setCount((current) => Math.max(0, current - 1));
    setOpen(false);
    void markNotificationRead(id).catch(() => undefined);
  }

  /*
   * Optimistic, and the `finally` is what makes that honest: the dots go out immediately, and the
   * refresh afterwards re-reads the count from the server whatever happened. So a failed write does
   * not leave the bell claiming a clear inbox — the true count comes straight back.
   *
   * The catch is not decoration either. `markAllNotificationsRead` THROWS on a genuine failure (only a
   * refusal comes back as data), and an unhandled throw in an async click handler is a rejected
   * promise nobody sees — the exact silent-failure shape this repo has shipped before. The panel has
   * no room for an error message, so the honest recovery is to show the truth again; the inbox's own
   * "mark all read" is the one that toasts.
   */
  async function handleMarkAll() {
    setRows((current) =>
      current.map((item) => ({ ...item, readAt: item.readAt ?? new Date().toISOString() })),
    );
    setCount(0);
    try {
      await markAllNotificationsRead();
    } catch {
      // Swallowed deliberately; the refresh below is the recovery.
    } finally {
      // Last, so it cannot cancel the write above.
      startTransition(() => router.refresh());
    }
  }

  const triggerName = count > 0 ? t('bell.unread', { count }) : t('bell.none');
  const bell = (
    <>
      <Bell className="size-5 text-muted-foreground group-hover/bell:text-foreground group-focus-visible/bell:animate-focus-bump transition-colors" />
      {/*
       * A dot rather than a badge with a number, and absolutely positioned so it never resizes the
       * trigger: the bell must not move when something arrives.
       */}
      {count > 0 && (
        <span
          aria-hidden
          className="absolute top-1.5 right-1.5 size-2 bg-blue-800 rounded-full ring-2 ring-sidebar"
        />
      )}
    </>
  );
  const panel = (
    <NotificationPanel
      rows={rows}
      count={count}
      isRefreshing={isRefreshing}
      mobile={isMobile}
      onOpen={handleOpen}
      onMarkAll={handleMarkAll}
      onSeeAll={() => setOpen(false)}
    />
  );

  if (isMobile) {
    return (
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetTrigger
          ref={triggerRef}
          aria-label={triggerName}
          data-testid="notification-bell"
          className={TRIGGER_CLASS}
        >
          {bell}
        </SheetTrigger>
        <SheetContent
          side="right"
          aria-describedby={undefined}
          data-testid="notification-panel"
          className="flex flex-col w-full sm:max-w-none p-4 gap-y-2"
        >
          {panel}
        </SheetContent>
      </Sheet>
    );
  }

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
      <PopoverTrigger
        ref={triggerRef}
        aria-label={triggerName}
        data-testid="notification-bell"
        className={TRIGGER_CLASS}
      >
        {bell}
      </PopoverTrigger>

      {/* Its height is capped by the room below the bell, and the list inside it is what scrolls. */}
      <PopoverContent
        side="right"
        align="start"
        sideOffset={sideOffset}
        collisionPadding={POPOVER_COLLISION_PADDING_PX}
        data-testid="notification-panel"
        className="w-88 max-h-(--radix-popover-content-available-height) p-2"
      >
        {panel}
      </PopoverContent>
    </Popover>
  );
}

interface NotificationPanelProps {
  rows: AppNotification[];
  count: number;
  isRefreshing: boolean;
  // The full-width sheet below `md`, where the heading is the sheet's title.
  mobile: boolean;
  onOpen: (id: number) => void;
  onMarkAll: () => void;
  onSeeAll: () => void;
}

// What the bell opens, in either container: the heading and "mark all read", the recent rows (the part
// that scrolls), and the way to the inbox.
function NotificationPanel({
  rows,
  count,
  isRefreshing,
  mobile,
  onOpen,
  onMarkAll,
  onSeeAll,
}: NotificationPanelProps) {
  const t = useTranslations('notifications');

  return (
    <>
      <div className={cn('flex items-center justify-between px-1 pb-1', mobile && 'pr-8')}>
        {mobile ? (
          <SheetTitle className="text-paragraph-sm-semibold">{t('bell.heading')}</SheetTitle>
        ) : (
          <span className="text-paragraph-sm-semibold">{t('bell.heading')}</span>
        )}
        {count > 0 && (
          <button
            type="button"
            onClick={onMarkAll}
            disabled={isRefreshing}
            className={cn(
              'rounded-md px-1 outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring disabled:opacity-50 transition-colors',
              'text-paragraph-xs text-muted-foreground',
            )}
          >
            {t('bell.markAll')}
          </button>
        )}
      </div>
      <Separator />

      {rows.length === 0 ? (
        <p className="px-1 py-6 text-center text-paragraph-xs text-muted-foreground">
          {t('bell.emptyDescription')}
        </p>
      ) : (
        // `min-h-0` lets the list, rather than the panel, give way when the rows outgrow the room.
        <ul
          className={cn(
            'flex flex-col min-h-0 -mx-1 gap-y-0.5 overflow-y-auto',
            !mobile && 'max-h-96',
          )}
        >
          {rows.map((notification) => (
            <li key={notification.id}>
              <NotificationRow notification={notification} onOpen={onOpen} />
            </li>
          ))}
        </ul>
      )}

      <Separator />
      <Link
        href={ROUTES.notifications}
        onClick={onSeeAll}
        data-testid="notification-see-all"
        className="px-1 py-1 rounded-md outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring text-center text-paragraph-xs text-muted-foreground transition-colors"
      >
        {t('bell.seeAll')}
      </Link>
    </>
  );
}
