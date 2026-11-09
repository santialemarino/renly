import { forwardRef, type ComponentProps, type ReactNode } from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { NotificationBell } from '@/app/(protected)/_components/notification-bell';
import type { AppNotification } from '@/lib/api/notifications';
import messages from '../../translations/en.json';

/*
 * The bell's rows and unread count come from the protected layout, and `router.refresh()` is how they
 * are re-read after a read anywhere — here, in the inbox, or through "Mark all read". The bell once
 * copied its props into state on mount, so every refresh after that was ignored and the count stayed
 * stale until a full reload. These tests hand it fresh props the way a refresh does and check that it
 * shows them, and that its own optimistic reads give way to them.
 */

const router = vi.hoisted(() => ({ refresh: vi.fn() }));
vi.mock('next/navigation', () => ({ useRouter: () => router }));

const actions = vi.hoisted(() => ({
  markNotificationRead: vi.fn(),
  markAllNotificationsRead: vi.fn(),
}));
vi.mock('@/app/(protected)/notifications/actions', () => actions);

// Desktop: the popover. The Sheet variant shares every line this file is about.
vi.mock('@repo/ui/hooks', () => ({ useIsMobile: () => false }));

/*
 * Radix cannot mount in this suite (it resolves a second React copy), so the popover is a plain
 * trigger with its panel always rendered: what is asserted is the bell's own state, not Radix's.
 */
vi.mock('@repo/ui/components', () => {
  const PopoverTrigger = forwardRef<HTMLButtonElement, ComponentProps<'button'>>(
    function PopoverTrigger(props, ref) {
      return <button type="button" ref={ref} {...props} />;
    },
  );
  return {
    Popover: ({ children }: { children: ReactNode }) => children,
    PopoverTrigger,
    PopoverContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    Separator: () => <hr />,
    Sheet: ({ children }: { children: ReactNode }) => children,
    SheetContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    SheetTitle: ({ children }: { children: ReactNode }) => <h2>{children}</h2>,
    SheetTrigger: PopoverTrigger,
  };
});

function notification(id: number, read = false): AppNotification {
  return {
    id,
    event: 'member_joined',
    payload: { group_id: 1, group: `Group ${id}`, member: 'Ana' },
    readAt: read ? '2026-11-01T00:00:00Z' : null,
    createdAt: '2026-11-01T00:00:00Z',
  };
}

function bell(notifications: AppNotification[], unread: number) {
  return (
    <NextIntlClientProvider locale="en" messages={messages} timeZone="UTC">
      <NotificationBell notifications={notifications} unread={unread} />
    </NextIntlClientProvider>
  );
}

function trigger() {
  return screen.getByTestId('notification-bell');
}

beforeEach(() => {
  router.refresh.mockReset();
  actions.markNotificationRead.mockReset().mockResolvedValue({ ok: true });
  actions.markAllNotificationsRead.mockReset().mockResolvedValue({ ok: true });
});

describe('the notification bell', () => {
  it('follows fresh props from a refresh', () => {
    const { rerender } = render(bell([notification(1), notification(2)], 2));
    expect(trigger()).toHaveAccessibleName('2 unread notifications');

    // A read in the inbox, then the refresh: the layout hands the bell its new rows and count.
    rerender(bell([notification(1, true), notification(2)], 1));
    expect(trigger()).toHaveAccessibleName('1 unread notification');

    rerender(bell([notification(1, true), notification(2, true)], 0));
    expect(trigger()).toHaveAccessibleName('No notifications');
  });

  it('marks one read at once, then re-reads the server once the write lands', async () => {
    render(bell([notification(1), notification(2)], 2));
    const rows = await screen.findAllByRole('link', { name: /Group 1/ });
    await act(async () => {
      fireEvent.click(rows[0]!);
    });

    expect(trigger()).toHaveAccessibleName('1 unread notification');
    expect(actions.markNotificationRead).toHaveBeenCalledWith(1);
    expect(router.refresh).toHaveBeenCalledTimes(1);
  });

  it('lets the server answer replace its own optimistic "mark all read"', async () => {
    const { rerender } = render(bell([notification(1), notification(2)], 2));
    await act(async () => {
      fireEvent.click(await screen.findByRole('button', { name: 'Mark all read' }));
    });
    expect(trigger()).toHaveAccessibleName('No notifications');
    expect(router.refresh).toHaveBeenCalledTimes(1);

    // The refresh arrives with a notification that came in meanwhile: it shows, not a stale zero.
    rerender(bell([notification(3), notification(1, true), notification(2, true)], 1));
    expect(trigger()).toHaveAccessibleName('1 unread notification');
  });
});
