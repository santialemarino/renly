// Maps the API's stable error `code` to a localized message (the `apiErrors` translations namespace),
// falling back to the raw English `detail` for a code the frontend doesn't map. This is the frontend
// half of the error-code contract: the backend stays locale-agnostic and returns `{detail, code, …}`;
// the frontend owns the localized copy. Usable on both the client (`useTranslations('apiErrors')`)
// and the server (`await getTranslations('apiErrors')`) — both translators satisfy `ApiErrorTranslator`.

// The subset of a next-intl translator this module needs: call it with a (runtime) code + optional
// interpolation params, and check whether a code is mapped.
export interface ApiErrorTranslator {
  (code: string, values?: Record<string, string | number>): string;
  has(code: string): boolean;
}

// A failed API response, parsed: the English `detail`, the machine `code`, and any extra fields the
// backend included (e.g. `row_currency`) that a localized message can interpolate.
export interface ApiError {
  code?: string;
  detail?: string;
  params: Record<string, string | number>;
}

/*
 * Params read from response HEADERS rather than the body, keyed by the param a message interpolates.
 * A rate-limited response (`rate_limited`) says how long to wait only in `Retry-After` (whole seconds),
 * and the copy counts minutes, rounded up so "1 minute" never means "wait longer than that". The API
 * exposes the header through CORS, so this works for a browser-side fetch as well as a server one.
 */
export const HEADER_PARAMS = {
  retry_after_minutes: (headers: Headers): number | undefined => {
    const seconds = Number(headers.get('Retry-After'));
    return headers.has('Retry-After') && Number.isInteger(seconds) && seconds >= 0
      ? Math.max(1, Math.ceil(seconds / 60))
      : undefined;
  },
};

// Parses a failed Response into { code, detail, params }. Never throws — a non-JSON body yields empty.
// Header-derived params (HEADER_PARAMS) join the body's extras when the response carries them.
export async function parseApiError(res: Response): Promise<ApiError> {
  const fromHeaders: Record<string, number> = {};
  for (const [param, read] of Object.entries(HEADER_PARAMS)) {
    const value = read(res.headers);
    if (value !== undefined) fromHeaders[param] = value;
  }
  try {
    const body = (await res.json()) as Record<string, unknown>;
    const { detail, code, ...rest } = body;
    return {
      code: typeof code === 'string' ? code : undefined,
      detail: typeof detail === 'string' ? detail : undefined,
      params: { ...(rest as Record<string, string | number>), ...fromHeaders },
    };
  } catch {
    return { params: fromHeaders };
  }
}

/*
 * An ApiError folded into one string and back. Auth.js carries a refused sign-in to the browser only
 * as the `code` of a `CredentialsSignin` (a URL query parameter), so the login path packs the parsed
 * error into it on the server and the form unpacks it to resolve the localized message. Numeric
 * params come back as numbers so a plural message still selects its form.
 */
export function encodeApiError(error: ApiError): string {
  const fields: Record<string, string> = {};
  if (error.code) fields.code = error.code;
  if (error.detail) fields.detail = error.detail;
  for (const [key, value] of Object.entries(error.params)) fields[`param.${key}`] = String(value);
  return new URLSearchParams(fields).toString();
}

// The inverse of encodeApiError; null for any string that does not carry an API error code (an
// ordinary Auth.js code such as `credentials`).
export function decodeApiError(encoded: string | undefined | null): ApiError | null {
  if (!encoded) return null;
  const fields = new URLSearchParams(encoded);
  const code = fields.get('code');
  if (!code) return null;
  const params: Record<string, string | number> = {};
  for (const [key, value] of fields) {
    if (!key.startsWith('param.')) continue;
    const numeric = Number(value);
    params[key.slice('param.'.length)] = value !== '' && Number.isFinite(numeric) ? numeric : value;
  }
  return { code, detail: fields.get('detail') ?? undefined, params };
}

// Resolves an API error to a user-facing message: the localized `apiErrors.<code>` string when the
// code is mapped (interpolating the extra params), else the raw English `detail`, else `fallback`.
export function resolveApiError(t: ApiErrorTranslator, error: ApiError, fallback: string): string {
  if (error.code && t.has(error.code)) return t(error.code, error.params);
  return error.detail || fallback;
}
