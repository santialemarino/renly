// The shortest INTERNAL_API_SECRET the API starts with (MIN_INTERNAL_API_SECRET_LENGTH in the API's
// app/config.py). A shorter value here can never equal the API's.
export const MIN_INTERNAL_API_SECRET_LENGTH = 32;

/*
 * The startup warning for an INTERNAL_API_SECRET that is set but shorter than the API accepts, or null.
 * It warns rather than refusing to start: the mismatch costs no request, it only makes the API ignore
 * the forwarded client IP, so every server-side call (sign-in, token refresh, the signup context) falls
 * back to the one bucket keyed by this server's address — which nothing else would surface.
 */
export function internalApiSecretWarning(secret: string | undefined): string | null {
  if (!secret || secret.length >= MIN_INTERNAL_API_SECRET_LENGTH) return null;
  return (
    `INTERNAL_API_SECRET is ${secret.length} characters; the API requires at least ` +
    `${MIN_INTERNAL_API_SECRET_LENGTH}, so it cannot match and the API will rate-limit every ` +
    `server-side call by this server's address. Set the same value of at least ` +
    `${MIN_INTERNAL_API_SECRET_LENGTH} characters on both apps.`
  );
}
