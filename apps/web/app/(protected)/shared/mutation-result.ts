import { isRefusal, localizedApiError } from '@/lib/i18n/api-errors-server';

/*
 * How every shared-money mutation reports a refusal, shared by the group and pot actions beside it.
 *
 * It returns the refusal as DATA rather than throwing, which is what
 * `useEntityFormDialog.submitWithLifecycle` understands: the Server Action boundary strips prototype
 * chains, so a thrown class instance reaches the client as a plain `Error` with its message gone.
 *
 * The refusals worth showing are the ones a stale page produces or a rule the user could not have
 * known — you were demoted in another tab (403), you have read-only access to this pot (403), the
 * ownership is already agreed so a holding cannot be taken out (409), the percentages do not total
 * 100 (400), the pot has no value on that date so units cannot be priced (400). None of them is a
 * crash, and every one has something specific to say.
 */
export type SharedMutationResult = { ok: true } | { ok: false; conflictDetail: string };

/*
 * Turns a failed response into either a surfaced refusal or a throw. One helper for the whole module
 * so every group and pot action classifies failures identically — the alternative is twenty copies
 * that drift, and the pot actions alone are ten of them.
 */
export async function toResult(
  res: Response,
  failureMessage: string,
): Promise<SharedMutationResult> {
  if (res.ok) return { ok: true };
  const detail = isRefusal(res) ? await localizedApiError(res) : null;
  if (detail) return { ok: false, conflictDetail: detail };
  throw new Error(failureMessage);
}
