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

// Parses a failed Response into { code, detail, params }. Never throws — a non-JSON body yields empty.
export async function parseApiError(res: Response): Promise<ApiError> {
  try {
    const body = (await res.json()) as Record<string, unknown>;
    const { detail, code, ...rest } = body;
    return {
      code: typeof code === 'string' ? code : undefined,
      detail: typeof detail === 'string' ? detail : undefined,
      params: rest as Record<string, string | number>,
    };
  } catch {
    return { params: {} };
  }
}

// Resolves an API error to a user-facing message: the localized `apiErrors.<code>` string when the
// code is mapped (interpolating the extra params), else the raw English `detail`, else `fallback`.
export function resolveApiError(t: ApiErrorTranslator, error: ApiError, fallback: string): string {
  if (error.code && t.has(error.code)) return t(error.code, error.params);
  return error.detail || fallback;
}
