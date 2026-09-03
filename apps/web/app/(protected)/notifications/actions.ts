'use server';

import {
  toDataResult,
  toResult,
  type SharedDataResult,
  type SharedMutationResult,
} from '@/app/(protected)/shared/mutation-result';
import { mapPreferences, type NotificationPreferences } from '@/lib/api/notifications';
import { authenticatedFetch } from '@/lib/authenticated-fetch';
import type { NotificationChannel, NotificationEvent } from '@/lib/constants/notifications';

/*
 * Mutations on the notification layer. They reuse the shared-money result helpers rather than a set of
 * their own: the classification ("a refusal the user could not have known, surfaced as data" against
 * "a genuine failure, thrown") is identical, and a second copy would drift.
 *
 * The one refusal worth surfacing here is `409 push_not_configured` — a deployment with no VAPID key,
 * where the page's own `pushAvailable` flag already hides the control, so reaching it means a stale
 * page rather than a mistake.
 *
 * Both preference writes and both push writes return the WHOLE grid, so the client re-renders from one
 * source instead of patching its own copy of it. That is what stops the switches and the "on this
 * browser" line disagreeing after a save.
 */

// Records one switch: one event on one channel. One cell per request rather than the whole matrix,
// because two people (or two tabs) editing different rows must not overwrite each other's answers.
export async function saveNotificationPreference(
  event: NotificationEvent,
  channel: NotificationChannel,
  enabled: boolean,
): Promise<SharedDataResult<NotificationPreferences>> {
  const res = await authenticatedFetch('/notifications/preferences', {
    method: 'PUT',
    body: { event, channel, enabled },
  });
  return toDataResult(res, mapPreferences, 'Failed to save notification preference');
}

// Registers this browser for web push. The three values come verbatim from the browser's own
// PushSubscription; `p256dh` and `auth` are the keys the payload is encrypted with and are write-only
// — no endpoint ever reads them back.
export async function subscribeToPush(
  endpoint: string,
  p256dh: string,
  auth: string,
  userAgent: string | null,
): Promise<SharedDataResult<NotificationPreferences>> {
  const res = await authenticatedFetch('/notifications/push/subscriptions', {
    method: 'POST',
    body: { endpoint, p256dh, auth, user_agent: userAgent },
  });
  return toDataResult(res, mapPreferences, 'Failed to enable push notifications');
}

// Stops sending push to this browser, named by its own endpoint. Idempotent server-side, so a browser
// whose subscription the push service already discarded is not an error here.
export async function unsubscribeFromPush(
  endpoint: string,
): Promise<SharedDataResult<NotificationPreferences>> {
  const res = await authenticatedFetch('/notifications/push/subscriptions', {
    method: 'DELETE',
    body: { endpoint },
  });
  return toDataResult(res, mapPreferences, 'Failed to disable push notifications');
}

// Marks one notification read.
export async function markNotificationRead(id: number): Promise<SharedMutationResult> {
  const res = await authenticatedFetch(`/notifications/${id}/read`, { method: 'POST' });
  return toResult(res, 'Failed to mark the notification as read');
}

// Marks every notification the caller can see read.
export async function markAllNotificationsRead(): Promise<SharedMutationResult> {
  const res = await authenticatedFetch('/notifications/read-all', { method: 'POST' });
  return toResult(res, 'Failed to mark notifications as read');
}
