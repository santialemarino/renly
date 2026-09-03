import { render, screen, waitFor } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { PushSection } from '@/app/(protected)/notifications/_components/push-section';
import type { NotificationPreferences } from '@/lib/api/notifications';
import messages from '../../translations/en.json';

/*
 * What "on for this browser" is allowed to mean.
 *
 * The section answers a question no single source can: the BROWSER knows whether it holds a push
 * subscription, and the ACCOUNT knows how many it owns — and the two can disagree, because a browser
 * holds exactly one subscription, so a second account signing in on a shared computer and turning push
 * on takes it over and the first account's row is released. Reading the browser alone would then leave
 * this page telling somebody push is on while every send goes to the other account.
 *
 * The real English copy is used rather than a stub, so a claim being asserted here is the sentence a
 * person actually reads.
 */

vi.mock('@/app/(protected)/notifications/actions', () => ({
  subscribeToPush: vi.fn(),
  unsubscribeFromPush: vi.fn(),
}));

const pushMock = vi.hoisted(() => ({
  supported: true,
  permission: 'granted' as NotificationPermission,
  endpoint: null as string | null,
}));

vi.mock('@/lib/push', () => ({
  isPushSupported: () => pushMock.supported,
  currentPushEndpoint: () => Promise.resolve(pushMock.endpoint),
  enablePush: vi.fn(),
  disablePush: vi.fn(),
  PushPermissionDeniedError: class PushPermissionDeniedError extends Error {},
}));

function preferences(subscriptions: number): NotificationPreferences {
  return {
    preferences: [],
    pushAvailable: true,
    pushPublicKey: 'key',
    pushSubscriptions: subscriptions,
  };
}

function renderSection(subscriptions: number) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages} timeZone="UTC">
      <PushSection initialPreferences={preferences(subscriptions)} />
    </NextIntlClientProvider>,
  );
}

describe('the push section', () => {
  beforeEach(() => {
    pushMock.supported = true;
    pushMock.permission = 'granted';
    pushMock.endpoint = null;
    vi.stubGlobal('Notification', { permission: pushMock.permission });
  });

  it('says push is on only when the browser holds one AND the account owns one', async () => {
    pushMock.endpoint = 'https://push.test/this-browser';
    renderSection(1);
    await waitFor(() => expect(screen.getByText('On for this browser.')).toBeVisible());
    expect(screen.getByRole('button', { name: 'Turn off for this browser' })).toBeVisible();
  });

  it('says push is off when the browser holds a subscription this account does not own', async () => {
    // The shared computer: this browser is subscribed, but the row belongs to whoever enabled it last.
    // Zero rows is the case the count settles exactly — none of them can be this browser's.
    pushMock.endpoint = 'https://push.test/claimed-by-someone-else';
    renderSection(0);
    await waitFor(() => expect(screen.getByText('Off for this browser.')).toBeVisible());
    // And the way back is offered rather than hidden: turning it on re-claims this browser.
    expect(screen.getByRole('button', { name: 'Turn on for this browser' })).toBeVisible();
  });

  it('counts the account’s other browsers without counting this one twice', async () => {
    pushMock.endpoint = 'https://push.test/this-browser';
    renderSection(3);
    await waitFor(() => expect(screen.getByText('2 other browsers are subscribed.')).toBeVisible());
  });

  it('counts every subscription as another browser when this one holds none', async () => {
    renderSection(1);
    await waitFor(() => expect(screen.getByText('1 other browser is subscribed.')).toBeVisible());
  });

  it('offers nothing at all where the browser cannot do push', async () => {
    // Distinct from "off": no button can fix it, so offering one would be a lie.
    pushMock.supported = false;
    renderSection(0);
    await waitFor(() => expect(screen.getByText(/does not support web push/i)).toBeVisible());
    expect(screen.queryByRole('button')).toBeNull();
  });
});
