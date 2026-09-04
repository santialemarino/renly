/*
 * Server-only types + mapper for a group's audit trail. Read-only: nothing on the web writes an entry,
 * because an entry is written by whatever act it records, inside that act's own transaction.
 *
 * `payload` stays loose (`Record<string, unknown>`) and its keys stay snake_case, alone in this layer
 * and for the reason `lib/api/notifications.ts` states about its own: those keys are the placeholder
 * names the translation strings interpolate, so renaming them here would mean two vocabularies for one
 * sentence. Narrowing the type per action would put the copy's shape in two places.
 */

import 'server-only';

import { authenticatedFetch } from '@/lib/authenticated-fetch';
import type { ActivityEntityType } from '@/lib/constants/shared-activity';

// --- Raw types (API JSON shape, snake_case) ---

interface ActivityEntryRaw {
  id: number;
  entity_type: ActivityEntityType;
  entity_id: number | null;
  action: string;
  pot_id: number | null;
  actor_name: string | null;
  payload: Record<string, unknown>;
  created_at: string;
}

// --- Frontend types (camelCase) ---

export interface ActivityEntry {
  id: number;
  entityType: ActivityEntityType;
  entityId: number | null;
  action: string;
  potId: number | null;
  /** Who did it, as the group names them. Null once the seat no longer names an account. */
  actorName: string | null;
  payload: Record<string, unknown>;
  createdAt: string;
}

// --- Mappers ---

function mapEntry(raw: ActivityEntryRaw): ActivityEntry {
  return {
    id: raw.id,
    entityType: raw.entity_type,
    entityId: raw.entity_id,
    action: raw.action,
    potId: raw.pot_id,
    actorName: raw.actor_name,
    payload: raw.payload,
    createdAt: raw.created_at,
  };
}

// --- API functions ---

/*
 * A group's recent activity, newest first.
 *
 * Entries about a pot the caller cannot see are absent, and that is the row-level policy's answer
 * rather than a filter here — so this list can never state more than the pot pages themselves would.
 */
export async function getGroupActivity(groupId: number, limit: number): Promise<ActivityEntry[]> {
  const res = await authenticatedFetch(`/groups/${groupId}/activity?limit=${limit}`, {
    method: 'GET',
  });
  if (!res.ok) throw new Error('Failed to fetch group activity');
  const raw: ActivityEntryRaw[] = await res.json();
  return raw.map(mapEntry);
}
