import { createElement, type ReactNode } from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { NotificationChannelsSection } from '@/app/(protected)/notifications/_components/notification-channels-section';
import type { NotificationPreferences } from '@/lib/api/notifications';
import { AUTOSAVE_COALESCE_MS } from '@/lib/constants/autosave';
import type { NotificationChannel, NotificationEvent } from '@/lib/constants/notifications';
import messages from '../../translations/en.json';

/*
 * The grid keeps only the clicked cell's part of each save's answer. Every save answers with the WHOLE
 * grid as the server saw it then, so when two cells' writes answer in reverse order, the later answer
 * is older about the other cell — taking it whole would switch that cell back off.
 *
 * Radix's Switch cannot render here (two React copies; see the testing skill), so the base components
 * are stood in for by plain elements that keep the props the section relies on.
 */

vi.mock('@repo/ui/components', () => ({
  Label: ({ children, ...props }: { children?: ReactNode }) =>
    createElement('label', props, children),
  Switch: ({
    checked,
    onCheckedChange,
    'aria-label': label,
    id,
  }: {
    checked: boolean;
    onCheckedChange: (next: boolean) => void;
    'aria-label'?: string;
    id?: string;
  }) =>
    createElement('button', {
      type: 'button',
      role: 'switch',
      id,
      'aria-label': label,
      'aria-checked': checked,
      onClick: () => onCheckedChange(!checked),
    }),
}));

vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

const pending = vi.hoisted(
  () =>
    [] as {
      event: string;
      channel: string;
      resolve: (answer: NotificationPreferences) => void;
    }[],
);

vi.mock('@/app/(protected)/notifications/actions', () => ({
  saveNotificationEmailCadence: vi.fn(),
  saveNotificationPreference: (event: string, channel: string) =>
    new Promise((resolve) =>
      pending.push({
        event,
        channel,
        resolve: (answer: NotificationPreferences) => resolve({ ok: true, data: answer }),
      }),
    ),
}));

const A = { event: 'group_invited', channel: 'email' } as const;
const B = { event: 'member_joined', channel: 'email' } as const;

// The grid as the server would answer it, with the two cells under test set as given.
function grid(a: boolean, b: boolean): NotificationPreferences {
  const row = (
    { event, channel }: { event: NotificationEvent; channel: NotificationChannel },
    enabled: boolean,
  ) => ({ event, channel, enabled, isDefault: false });
  return {
    preferences: [row(A, a), row(B, b)],
    emailCadence: 'immediate',
    pushAvailable: true,
    pushPublicKey: 'key',
    pushSubscriptions: 0,
  };
}

function cell({ event, channel }: { event: string; channel: string }) {
  const en = messages.notifications;
  const label = `${en.events[event as keyof typeof en.events].label} — ${en.channels[channel as 'email']}`;
  return screen.getByRole('switch', { name: label });
}

describe('the notification channels grid', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    pending.length = 0;
  });
  afterEach(() => vi.useRealTimers());

  it('keeps both cells on when their saves answer in reverse order', async () => {
    render(
      <NextIntlClientProvider locale="en" messages={messages} timeZone="UTC">
        <NotificationChannelsSection initialPreferences={grid(false, false)} />
      </NextIntlClientProvider>,
    );

    fireEvent.click(cell(A));
    fireEvent.click(cell(B));
    await act(async () => {
      vi.advanceTimersByTime(AUTOSAVE_COALESCE_MS);
    });
    expect(pending.map(({ event }) => event)).toEqual([A.event, B.event]);

    // B's answer comes first and already includes A's change; A's comes last and predates B's.
    await act(async () => pending[1]!.resolve(grid(true, true)));
    await act(async () => pending[0]!.resolve(grid(true, false)));

    expect(cell(A)).toHaveAttribute('aria-checked', 'true');
    expect(cell(B)).toHaveAttribute('aria-checked', 'true');
  });
});
