import 'server-only';

import { getTranslations } from 'next-intl/server';

import { parseApiError, resolveApiError, type ApiError } from '@/lib/i18n/api-errors';

/*
 * Server-side twin of `lib/i18n/api-errors` (the same split as `formatters` / `formatters-server`):
 * that module is deliberately isomorphic and so cannot import `next-intl/server`, while every Server
 * Action needs exactly this — resolve a failed response to a localized reason.
 *
 * Why every action needs it: the Server Action boundary strips prototype chains, so a thrown error
 * arrives client-side as a plain `Error` with its message lost. An action must therefore return the
 * refusal as DATA (`{ ok: false, conflictDetail }`), which means translating it here rather than
 * throwing. `useEntityFormDialog.submitWithLifecycle` understands that shape.
 */

// Resolves a failed response to a localized message (mapped API `code`, else the raw `detail`), or
// null when the body carries neither — the caller then falls back to its own generic error rather
// than surfacing an empty toast. `transform` adapts the parsed error first (dates, say).
export async function localizedApiError(
  res: Response,
  transform?: (error: ApiError) => Promise<ApiError>,
): Promise<string | null> {
  const parsed = await parseApiError(res);
  if (!parsed.code && !parsed.detail) return null;
  const t = await getTranslations('apiErrors');
  return resolveApiError(t, transform ? await transform(parsed) : parsed, '') || null;
}

/*
 * The statuses a mutation can be refused with for a reason worth showing. 400 is the domain-rule
 * refusal (a mismatched funding account, a rejected transfer); 404 covers a link whose target has been
 * deleted in another tab, which `NotFoundError` answers with and which is otherwise indistinguishable
 * from a crash; 409 is the "conflicts with existing state" family (reconciliation-owned entries, a
 * currency lock). Anything else is a genuine failure and stays a throw.
 */
export const REFUSAL_STATUSES = [400, 404, 409];

// Whether a failed response is a refusal whose reason should be surfaced rather than thrown.
export function isRefusal(res: Response): boolean {
  return REFUSAL_STATUSES.includes(res.status);
}
