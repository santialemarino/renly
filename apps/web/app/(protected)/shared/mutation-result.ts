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
 * The same result, for the mutations whose RESPONSE BODY a caller needs rather than only its success.
 * Two of them do: a guided flow creates a pot and then has to act on the id it was given, and moves
 * holdings in and then has to state the value they turned out to be worth. Discarding the body and
 * re-reading would be a second round trip for a figure the write already returned.
 */
export type SharedDataResult<T> = { ok: true; data: T } | { ok: false; conflictDetail: string };

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

/*
 * The same classification, carrying the response body through the mapper the reads already use.
 *
 * It takes the mapper rather than returning raw JSON so a snake_case wire shape never escapes the API
 * boundary into a component — the same rule `lib/api/*` follows, which is also why the two mappers
 * these callers need are exported from there instead of copied here.
 */
export async function toDataResult<TRaw, T>(
  res: Response,
  map: (raw: TRaw) => T,
  failureMessage: string,
): Promise<SharedDataResult<T>> {
  if (res.ok) return { ok: true, data: map((await res.json()) as TRaw) };
  const detail = isRefusal(res) ? await localizedApiError(res) : null;
  if (detail) return { ok: false, conflictDetail: detail };
  throw new Error(failureMessage);
}
