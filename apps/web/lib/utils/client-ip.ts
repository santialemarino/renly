/*
 * Resolves the client IP of a request this server received, from its `X-Forwarded-For` header and
 * the number of trusted proxies in front of it — the same right-counting rule the API applies to its
 * own requests. Each trusted proxy appends the address it saw, so the client is `trustedProxyCount`
 * entries in from the right; anything further left was written by the client and is never trusted.
 *
 * With no trusted proxy (0) there is no answer: Next only fills `X-Forwarded-For` when the request
 * arrives without one, so a server reached directly cannot tell its peer from a value the client sent.
 */
export function clientIpFromForwardedFor(
  forwardedFor: string | null,
  trustedProxyCount: number,
): string | null {
  if (!forwardedFor || !Number.isInteger(trustedProxyCount) || trustedProxyCount <= 0) return null;
  const parts = forwardedFor
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean);
  if (parts.length === 0) return null;
  return parts[Math.max(0, parts.length - trustedProxyCount)] ?? null;
}
