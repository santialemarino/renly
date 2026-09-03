'use client';

import { useState, useTransition } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Bell } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { Popover, PopoverContent, PopoverTrigger, Separator } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import {
  markAllNotificationsRead,
  markNotificationRead,
} from '@/app/(protected)/notifications/actions';
import { NotificationRow } from '@/components/notification-row';
import { ROUTES } from '@/config/routes';
import type { AppNotification } from '@/lib/api/notifications';

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
 * Its data comes from the protected LAYOUT, which is a server component: the count is correct on every
 * navigation and there is no polling. `router.refresh()` after a read is what re-asks for it.
 *
 * The unread marker is a DOT, not a number. A count implies a queue you are meant to empty, which is
 * the wrong relationship with a feed of things that already happened; the dot says "something is
 * there" and the popover says what.
 */
export function NotificationBell({ notifications, unread }: NotificationBellProps) {
  const t = useTranslations('notifications');

  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState(notifications);
  const [count, setCount] = useState(unread);
  const [isRefreshing, startTransition] = useTransition();

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
   * promise nobody sees — the exact silent-failure shape this repo has shipped before. The popover has
   * no room for an error message, so the honest recovery is to show the truth again; the page's own
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

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        aria-label={count > 0 ? t('bell.unread', { count }) : t('bell.none')}
        className="group/bell relative grid size-8 shrink-0 place-items-center rounded-lg outline-none hover:bg-gray-100 focus-visible:bg-gray-100 focus-visible:ring-3 focus-visible:ring-ring/50 transition-colors"
      >
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
      </PopoverTrigger>

      <PopoverContent align="start" className="w-88 p-2">
        <div className="flex items-center justify-between px-1 pb-1">
          <span className="text-paragraph-sm-semibold">{t('bell.heading')}</span>
          {count > 0 && (
            <button
              type="button"
              onClick={handleMarkAll}
              disabled={isRefreshing}
              className={cn(
                'rounded-md px-1 outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-50 transition-colors',
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
          <ul className="flex flex-col max-h-96 -mx-1 gap-y-0.5 overflow-y-auto">
            {rows.map((notification) => (
              <li key={notification.id}>
                <NotificationRow notification={notification} onOpen={handleOpen} />
              </li>
            ))}
          </ul>
        )}

        <Separator />
        <Link
          href={ROUTES.notifications}
          onClick={() => setOpen(false)}
          className="px-1 py-1 rounded-md outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 text-center text-paragraph-xs text-muted-foreground transition-colors"
        >
          {t('bell.seeAll')}
        </Link>
      </PopoverContent>
    </Popover>
  );
}
