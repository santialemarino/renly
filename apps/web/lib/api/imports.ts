import 'server-only';

import { getTranslations } from 'next-intl/server';

import { authenticatedFetch } from '@/lib/authenticated-fetch';
import { parseApiError, resolveApiError } from '@/lib/i18n/api-errors';

// --- Raw types (API JSON shape, snake_case) ---

interface ImportFieldRaw {
  key: string;
  required: boolean;
}

interface ImportPreviewRowRaw {
  row_number: number;
  values: Record<string, string>;
  status: string;
  errors: string[];
  warnings: string[];
}

interface ImportSummaryRaw {
  total: number;
  valid: number;
  invalid: number;
  duplicate: number;
}

interface ImportPreviewRaw {
  columns: string[];
  fields: ImportFieldRaw[];
  mapping: Record<string, string>;
  rows: ImportPreviewRowRaw[];
  summary: ImportSummaryRaw;
}

interface ImportResultRaw {
  created: number;
  skipped_invalid: number;
  skipped_duplicate: number;
}

// --- Frontend types (camelCase) ---

export type ImportRowStatus = 'valid' | 'invalid' | 'duplicate';

export interface ImportField {
  key: string;
  required: boolean;
}

export interface ImportPreviewRow {
  rowNumber: number;
  values: Record<string, string>;
  status: ImportRowStatus;
  errors: string[];
  warnings: string[];
}

export interface ImportSummary {
  total: number;
  valid: number;
  invalid: number;
  duplicate: number;
}

export interface ImportPreview {
  columns: string[];
  fields: ImportField[];
  mapping: Record<string, string>;
  rows: ImportPreviewRow[];
  summary: ImportSummary;
}

export interface ImportResult {
  created: number;
  skippedInvalid: number;
  skippedDuplicate: number;
}

// --- Mappers ---

function mapPreviewRow(raw: ImportPreviewRowRaw): ImportPreviewRow {
  return {
    rowNumber: raw.row_number,
    values: raw.values,
    status: raw.status as ImportRowStatus,
    errors: raw.errors,
    warnings: raw.warnings,
  };
}

function mapPreview(raw: ImportPreviewRaw): ImportPreview {
  return {
    columns: raw.columns,
    fields: raw.fields,
    mapping: raw.mapping,
    rows: raw.rows.map(mapPreviewRow),
    summary: raw.summary,
  };
}

function mapResult(raw: ImportResultRaw): ImportResult {
  return {
    created: raw.created,
    skippedInvalid: raw.skipped_invalid,
    skippedDuplicate: raw.skipped_duplicate,
  };
}

// --- API functions ---

// Builds an Error from a failed import response: the localized message for a mapped API `code`,
// else the raw `detail`, else a generic fallback.
async function importError(res: Response): Promise<Error> {
  const t = await getTranslations('apiErrors');
  return new Error(resolveApiError(t, await parseApiError(res), 'import_failed'));
}

export async function fetchImportPreview(
  entity: string,
  formData: FormData,
): Promise<ImportPreview> {
  const res = await authenticatedFetch(`/imports/${entity}/preview`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) throw await importError(res);
  return mapPreview(await res.json());
}

export async function fetchImportConfirm(
  entity: string,
  formData: FormData,
): Promise<ImportResult> {
  const res = await authenticatedFetch(`/imports/${entity}`, { method: 'POST', body: formData });
  if (!res.ok) throw await importError(res);
  return mapResult(await res.json());
}
