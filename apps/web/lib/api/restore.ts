import 'server-only';

import { getTranslations } from 'next-intl/server';

import { authenticatedFetch } from '@/lib/authenticated-fetch';
import { parseApiError, resolveApiError } from '@/lib/i18n/api-errors';

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

// Builds an Error from a failed restore response: the localized message for a mapped API `code`,
// else the raw `detail`, else a generic fallback.
async function restoreError(res: Response): Promise<Error> {
  const t = await getTranslations('apiErrors');
  return new Error(resolveApiError(t, await parseApiError(res), 'restore_failed'));
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
