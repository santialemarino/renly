'use server';

import {
  fetchImportConfirm,
  fetchImportPreview,
  type ImportPreview,
  type ImportResult,
} from '@/lib/api/imports';
import {
  fetchRestoreConfirm,
  fetchRestorePreview,
  type RestorePreview,
  type RestoreResult,
} from '@/lib/api/restore';
import { authenticatedFetch } from '@/lib/authenticated-fetch';

// Action results carry either the data or a message the client toasts. Returned (not thrown) so the
// API's detail message survives — Next.js sanitizes thrown server-action errors in production.
export type PreviewActionResult = { data: ImportPreview } | { error: string };
export type ConfirmActionResult = { data: ImportResult } | { error: string };
export type RestorePreviewActionResult = { data: RestorePreview } | { error: string };
export type RestoreConfirmActionResult = { data: RestoreResult } | { error: string };

// Dry-run preview of an import file. `formData` carries `file` and an optional `mapping` (JSON).
export async function previewImport(
  entity: string,
  formData: FormData,
): Promise<PreviewActionResult> {
  try {
    return { data: await fetchImportPreview(entity, formData) };
  } catch (error) {
    return { error: error instanceof Error ? error.message : 'import_failed' };
  }
}

// Confirms an import: the API re-validates and bulk-inserts. `formData` carries file, mapping, import_duplicates.
export async function confirmImport(
  entity: string,
  formData: FormData,
): Promise<ConfirmActionResult> {
  try {
    return { data: await fetchImportConfirm(entity, formData) };
  } catch (error) {
    return { error: error instanceof Error ? error.message : 'import_failed' };
  }
}

// Dry-run preview of restoring a Renly export. `formData` carries the export `file`.
export async function previewRestore(formData: FormData): Promise<RestorePreviewActionResult> {
  try {
    return { data: await fetchRestorePreview(formData) };
  } catch (error) {
    return { error: error instanceof Error ? error.message : 'restore_failed' };
  }
}

// Confirms a restore: the API re-validates and inserts the restorable rows. `formData` carries the file.
export async function confirmRestore(formData: FormData): Promise<RestoreConfirmActionResult> {
  try {
    return { data: await fetchRestoreConfirm(formData) };
  } catch (error) {
    return { error: error instanceof Error ? error.message : 'restore_failed' };
  }
}

// Returns the user's full data export as a JSON string for client-side download (AUTH-6).
export async function exportData(): Promise<string> {
  const res = await authenticatedFetch('/me/export', { method: 'GET' });
  if (!res.ok) throw new Error('export_failed');
  return res.text();
}
