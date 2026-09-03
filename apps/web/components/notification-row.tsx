'use client';

import Link from 'next/link';
import { useTranslations } from 'next-intl';

import { cn } from '@repo/ui/lib';
import type { AppNotification } from '@/lib/api/notifications';
import { useFormatters } from '@/lib/i18n/formatters';
import { notificationRow } from '@/lib/notifications';

interface NotificationRowProps {
  notification: AppNotification;
  // Marks it read. Fired on click, alongside the navigation — see the ordering note below.
  onOpen?: (id: number) => void;
  className?: string;
}

/*
 * One notification, rendered from its stored event and payload rather than from a stored sentence.
 * Shared by the bell's popover and the /notifications page so both read a row identically — the rule
 * itself lives in `lib/notifications.ts`, and this is only its presentation.
 *
 * It is a real `<Link>`, not a div with a router.push: a notification points at a page, so new-tab,
 * middle-click, copy-address and "link" in a screen reader's list all have to keep working.
 *
 * `onOpen` fires BEFORE the navigation and is deliberately not awaited. A Server Action called after a
 * navigation begins is cancelled by it, so an awaited mark-read would never settle; losing one is
 * harmless (the row stays unread and the next visit retries), blocking the navigation on it is not.
 */
export function NotificationRow({ notification, onOpen, className }: NotificationRowProps) {
  const fmt = useFormatters();
  const t = useTranslations('notifications');

  const row = notificationRow(notification, {
    formatAmount: (amount, currency) => fmt.amount(amount, currency || undefined),
    formatDate: (iso) => fmt.date(iso),
    potFallback: t('potFallback'),
  });
  const unread = notification.readAt === null;

  return (
    <Link
      href={row.href}
      onClick={() => onOpen?.(notification.id)}
      className={cn(
        'flex items-start px-3 py-2.5 gap-x-3 hover:bg-muted/60 rounded-lg outline-none focus-visible:bg-muted/60 focus-visible:ring-3 focus-visible:ring-ring/50 transition-colors',
        className,
      )}
    >
      {/*
       * The unread marker keeps its box whether or not it is filled, so reading a row does not shift
       * the lines beside it. aria-hidden because the state is announced by the label below rather than
       * by a colour.
       */}
      <span
        aria-hidden
        className={cn(
          'mt-1.5 size-2 shrink-0 rounded-full',
          unread ? 'bg-blue-800' : 'bg-transparent',
        )}
      />
      <span className="flex flex-col min-w-0 gap-y-0.5">
        <span className="text-paragraph-sm text-foreground">
          {unread && <span className="sr-only">{t('feed.unreadDot')}: </span>}
          {t(`events.${row.titleKey}`, row.params)}
        </span>
        {row.detailKey && (
          <span className="text-paragraph-xs text-muted-foreground">
            {t(`events.${row.detailKey}`, row.params)}
          </span>
        )}
        <span className="text-paragraph-xs text-muted-foreground/80">
          {fmt.timestampDate(notification.createdAt)}
        </span>
      </span>
    </Link>
  );
}
