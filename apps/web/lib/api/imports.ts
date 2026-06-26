import 'server-only';

import { authenticatedFetch } from '@/lib/authenticated-fetch';

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

// Reads the `{detail}` message from a failed import response, falling back to a generic message.
async function importError(res: Response): Promise<Error> {
  try {
    const body = await res.json();
    if (body && typeof body.detail === 'string') return new Error(body.detail);
  } catch {
    // The error body wasn't JSON; fall through to the generic message.
  }
  return new Error('import_failed');
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
