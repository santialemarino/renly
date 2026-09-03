/*
 * Server-only types + mappers for the notification layer. Reads go through the two functions here;
 * mutations are server actions in `app/(protected)/notifications/actions.ts`.
 *
 * One property of the API's design survives into these types and shapes the whole surface: a
 * notification stores its EVENT and a PAYLOAD, never a rendered sentence. The prose is built on the
 * web from `notifications.events.*` translation keys, so the feed reads in whatever language the
 * reader is using now and a copy fix reaches rows written months ago. `payload` is therefore
 * deliberately loose (`Record<string, unknown>`) rather than a union per event: it is interpolation
 * data, and narrowing it here would put the copy's shape in two places.
 *
 * The payload's keys stay snake_case, alone in this layer and on purpose. Every other field is mapped
 * to camelCase at this boundary, but the payload's keys are the placeholder names the translation
 * strings interpolate (`from_member`, `valued_as_of`), and the API's own email catalog interpolates
 * the same ones — renaming them on one side would mean two vocabularies for one message.
 */

import 'server-only';

import { authenticatedFetch } from '@/lib/authenticated-fetch';
import type { NotificationChannel, NotificationEvent } from '@/lib/constants/notifications';

// --- Raw types (API JSON shape, snake_case) ---

interface NotificationRaw {
  id: number;
  event: NotificationEvent;
  payload: Record<string, unknown>;
  read_at: string | null;
  created_at: string;
}

interface NotificationFeedRaw {
  items: NotificationRaw[];
  total: number;
  unread: number;
}

interface NotificationPreferenceRaw {
  event: NotificationEvent;
  channel: NotificationChannel;
  enabled: boolean;
  is_default: boolean;
}

interface NotificationPreferencesRaw {
  preferences: NotificationPreferenceRaw[];
  push_available: boolean;
  push_public_key: string | null;
  push_subscriptions: number;
}

// --- Frontend types (camelCase) ---

export interface AppNotification {
  id: number;
  event: NotificationEvent;
  payload: Record<string, unknown>;
  readAt: string | null;
  createdAt: string;
}

export interface NotificationFeed {
  items: AppNotification[];
  total: number;
  unread: number;
}

export interface NotificationPreference {
  event: NotificationEvent;
  channel: NotificationChannel;
  enabled: boolean;
  isDefault: boolean;
}

export interface NotificationPreferences {
  preferences: NotificationPreference[];
  pushAvailable: boolean;
  pushPublicKey: string | null;
  pushSubscriptions: number;
}

// --- Mappers ---

function mapNotification(raw: NotificationRaw): AppNotification {
  return {
    id: raw.id,
    event: raw.event,
    payload: raw.payload,
    readAt: raw.read_at,
    createdAt: raw.created_at,
  };
}

function mapFeed(raw: NotificationFeedRaw): NotificationFeed {
  return { items: raw.items.map(mapNotification), total: raw.total, unread: raw.unread };
}

function mapPreference(raw: NotificationPreferenceRaw): NotificationPreference {
  return {
    event: raw.event,
    channel: raw.channel,
    enabled: raw.enabled,
    isDefault: raw.is_default,
  };
}

export function mapPreferences(raw: NotificationPreferencesRaw): NotificationPreferences {
  return {
    preferences: raw.preferences.map(mapPreference),
    pushAvailable: raw.push_available,
    pushPublicKey: raw.push_public_key,
    pushSubscriptions: raw.push_subscriptions,
  };
}

// --- API functions ---

/** One page of the caller's notifications, newest first, with the total and the unread count. */
export async function getNotifications(limit: number, offset = 0): Promise<NotificationFeed> {
  const qs = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  const res = await authenticatedFetch(`/notifications?${qs.toString()}`, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch notifications');
  return mapFeed(await res.json());
}

/** The full preferences grid, plus whether this deployment can send web push at all. */
export async function getNotificationPreferences(): Promise<NotificationPreferences> {
  const res = await authenticatedFetch('/notifications/preferences', { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch notification preferences');
  return mapPreferences(await res.json());
}
