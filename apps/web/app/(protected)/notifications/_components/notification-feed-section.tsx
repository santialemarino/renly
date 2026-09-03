'use client';

import { useState, useTransition } from 'react';
import { useRouter } from 'next/navigation';
import { BellRing } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { Button } from '@repo/ui/components';
import {
  markAllNotificationsRead,
  markNotificationRead,
} from '@/app/(protected)/notifications/actions';
import { EmptyState } from '@/components/empty-state';
import { NotificationRow } from '@/components/notification-row';
import { SectionHeader } from '@/components/section-header';
import { TablePagination } from '@/components/table-pagination';
import { ROUTES } from '@/config/routes';
import type { NotificationFeed } from '@/lib/api/notifications';
import { NOTIFICATION_PAGE_SIZE } from '@/lib/constants/notifications';
import { useSearchParamsNavigation } from '@/lib/hooks/use-search-params-navigation';

interface NotificationFeedSectionProps {
  feed: NotificationFeed;
  page: number;
}

/*
 * The full history, newest first, paged through the URL like every other list in the app —
 * `useSearchParamsNavigation` + `TablePagination`, which is a count plus page links and carries no
 * table markup of its own.
 *
 * The rows are held in state ONLY so the two local interactions can be optimistic: marking one read (a
 * dot goes out) and marking all read (every dot goes out). Both are confirmed afterwards by
 * `router.refresh()`, which is what keeps the bell's unread count — rendered by the layout, from a
 * different request — in step with what the page now shows.
 */
export function NotificationFeedSection({ feed, page }: NotificationFeedSectionProps) {
  const t = useTranslations('notifications');

  const router = useRouter();
  const { navigate, isPending: isNavigating } = useSearchParamsNavigation(ROUTES.notifications);
  const [rows, setRows] = useState(feed.items);
  const [unread, setUnread] = useState(feed.unread);
  const [saving, setSaving] = useState(false);
  const [isRefreshing, startTransition] = useTransition();

  const totalPages = Math.max(1, Math.ceil(feed.total / NOTIFICATION_PAGE_SIZE));

  /*
   * Optimistic and un-awaited, deliberately: it fires alongside the row's own navigation, which would
   * cancel an awaited Server Action before it settled. The `catch` is not optional even so — an
   * un-caught rejection here is an error nobody sees — and swallowing it is the right recovery,
   * because losing one costs an unread dot that the next visit puts back, not data.
   */
  function handleOpen(id: number) {
    setRows((current) =>
      current.map((item) =>
        item.id === id && item.readAt === null
          ? { ...item, readAt: new Date().toISOString() }
          : item,
      ),
    );
    setUnread((current) => Math.max(0, current - 1));
    void markNotificationRead(id).catch(() => undefined);
  }

  // Awaited, so the button can say it is working — and wrapped, because this action THROWS on a
  // genuine failure and only a refusal comes back as data. An unhandled throw in a click handler is a
  // button that silently does nothing, which this repo has shipped before.
  async function handleMarkAll() {
    setSaving(true);
    try {
      const result = await markAllNotificationsRead();
      if (!result.ok) {
        toast.error(result.conflictDetail, { id: 'notifications-mark-all' });
        return;
      }
      setRows((current) =>
        current.map((item) => ({ ...item, readAt: item.readAt ?? new Date().toISOString() })),
      );
      setUnread(0);
      toast.success(t('feed.markAllDone'), { id: 'notifications-mark-all' });
      // Last, so it cannot cancel the write above, and inside a transition so the button can honestly
      // stay disabled until the server props catch up.
      startTransition(() => router.refresh());
    } catch {
      toast.error(t('feed.markAllError'), { id: 'notifications-mark-all' });
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="flex flex-col gap-y-4">
      <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-2">
        <SectionHeader title={t('feed.title')} description={t('feed.description')} />
        {unread > 0 && (
          <Button
            variant="outline"
            size="sm"
            onClick={handleMarkAll}
            disabled={saving || isRefreshing}
          >
            {t('feed.markAll')}
          </Button>
        )}
      </div>

      {rows.length === 0 ? (
        <EmptyState
          icon={BellRing}
          title={t('feed.empty')}
          description={t('feed.emptyDescription')}
          className="bg-muted/30 rounded-1.5xl"
        />
      ) : (
        <div className={isNavigating ? 'opacity-60 transition-opacity' : 'transition-opacity'}>
          <ul className="flex flex-col -mx-3 gap-y-0.5">
            {rows.map((notification) => (
              <li key={notification.id}>
                <NotificationRow notification={notification} onOpen={handleOpen} />
              </li>
            ))}
          </ul>
          <div className="mt-4">
            <TablePagination
              page={page}
              totalPages={totalPages}
              totalLabel={t('feed.count', { count: feed.total })}
              onPageChange={(next) => navigate({ page: next === 1 ? null : String(next) })}
            />
          </div>
        </div>
      )}
    </section>
  );
}
