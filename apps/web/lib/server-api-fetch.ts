import 'server-only';

import { headers } from 'next/headers';

import { clientIpFromForwardedFor } from '@/lib/utils/client-ip';

const apiUrl = process.env.NEXT_PUBLIC_API_URL as string;

// Header names the API reads in app/rate_limit.py (CLIENT_IP_HEADER, INTERNAL_SECRET_HEADER).
export const CLIENT_IP_HEADER = 'X-Renly-Client-IP';
export const INTERNAL_SECRET_HEADER = 'X-Renly-Internal-Secret';

/*
 * The headers that tell the API which client this server is calling on behalf of. A call from this
 * server reaches the API from the server's own address, so without them every visitor's login,
 * refresh and signup read would share one rate-limit bucket. The IP comes from this server's own
 * request under WEB_TRUSTED_PROXY_COUNT, and INTERNAL_API_SECRET proves to the API that this server
 * sent it. With either unset (or no trustworthy IP) nothing is added and the API keys the call by
 * this server's address, as it would without them.
 */
async function clientForwardingHeaders(): Promise<Record<string, string>> {
  const secret = process.env.INTERNAL_API_SECRET;
  if (!secret) return {};
  const trustedProxyCount = Number(process.env.WEB_TRUSTED_PROXY_COUNT ?? 0);
  const ip = clientIpFromForwardedFor((await headers()).get('x-forwarded-for'), trustedProxyCount);
  if (!ip) return {};
  return { [CLIENT_IP_HEADER]: ip, [INTERNAL_SECRET_HEADER]: secret };
}

/*
 * The one place this server calls the API. Every server-side request goes through here — with or
 * without a bearer token — so none can forget the client-forwarding headers; calls the browser makes
 * itself live in lib/auth-api.ts and never see the secret.
 */
export async function serverApiFetch(endpoint: string, init: RequestInit = {}): Promise<Response> {
  const requestHeaders = new Headers(init.headers);
  for (const [name, value] of Object.entries(await clientForwardingHeaders())) {
    requestHeaders.set(name, value);
  }
  return fetch(`${apiUrl}${endpoint}`, { ...init, headers: requestHeaders });
}
