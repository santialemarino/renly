import 'server-only';

import { authenticatedFetch } from '@/lib/authenticated-fetch';

// --- Raw types (API JSON shape, snake_case) ---

interface RestoreEntityStatRaw {
  entity: string;
  restore: number;
  skipped_unresolved: number;
}

interface RestorePreviewRaw {
  recognized: boolean;
  exported_at: string | null;
  entities: RestoreEntityStatRaw[];
  skipped_entities: string[];
}

interface RestoreResultRaw {
  restored: number;
  skipped_unresolved: number;
  entities: RestoreEntityStatRaw[];
}

// --- Frontend types (camelCase) ---

export interface RestoreEntityStat {
  entity: string;
  restore: number;
  skippedUnresolved: number;
}

export interface RestorePreview {
  recognized: boolean;
  exportedAt: string | null;
  entities: RestoreEntityStat[];
  skippedEntities: string[];
}

export interface RestoreResult {
  restored: number;
  skippedUnresolved: number;
  entities: RestoreEntityStat[];
}

// --- Mappers ---

function mapStat(raw: RestoreEntityStatRaw): RestoreEntityStat {
  return {
    entity: raw.entity,
    restore: raw.restore,
    skippedUnresolved: raw.skipped_unresolved,
  };
}

function mapPreview(raw: RestorePreviewRaw): RestorePreview {
  return {
    recognized: raw.recognized,
    exportedAt: raw.exported_at,
    entities: raw.entities.map(mapStat),
    skippedEntities: raw.skipped_entities,
  };
}

function mapResult(raw: RestoreResultRaw): RestoreResult {
  return {
    restored: raw.restored,
    skippedUnresolved: raw.skipped_unresolved,
    entities: raw.entities.map(mapStat),
  };
}

// --- API functions ---

// Reads the `{detail}` message from a failed restore response, falling back to a generic message.
async function restoreError(res: Response): Promise<Error> {
  try {
    const body = await res.json();
    if (body && typeof body.detail === 'string') return new Error(body.detail);
  } catch {
    // The error body wasn't JSON; fall through to the generic message.
  }
  return new Error('restore_failed');
}

export async function fetchRestorePreview(formData: FormData): Promise<RestorePreview> {
  const res = await authenticatedFetch('/restore/preview', { method: 'POST', body: formData });
  if (!res.ok) throw await restoreError(res);
  return mapPreview(await res.json());
}

export async function fetchRestoreConfirm(formData: FormData): Promise<RestoreResult> {
  const res = await authenticatedFetch('/restore', { method: 'POST', body: formData });
  if (!res.ok) throw await restoreError(res);
  return mapResult(await res.json());
}
