import 'server-only';

import { getAccessToken } from '@/lib/auth';

const apiUrl = process.env.NEXT_PUBLIC_API_URL as string;

/**
 * Makes an authenticated server-side API request with the Bearer token.
 * Throws if the user is not authenticated.
 */
export async function authenticatedFetch(
  endpoint: string,
  options: {
    method: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
    body?: unknown;
  },
): Promise<Response> {
  const accessToken = await getAccessToken();
  if (!accessToken) {
    throw new Error('Not authenticated');
  }

  const headers: Record<string, string> = { Authorization: `Bearer ${accessToken}` };
  const requestOptions: RequestInit = {
    method: options.method,
    headers,
    cache: 'no-store',
  };

  if (options.body !== undefined) {
    if (options.body instanceof FormData) {
      // Let the browser set the multipart Content-Type (with its boundary); don't serialize.
      requestOptions.body = options.body;
    } else {
      headers['Content-Type'] = 'application/json';
      requestOptions.body = JSON.stringify(options.body);
    }
  }

  return fetch(`${apiUrl}${endpoint}`, requestOptions);
}
