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
    method: 'GET' | 'POST' | 'PUT' | 'DELETE';
    body?: unknown;
  },
): Promise<Response> {
  const accessToken = await getAccessToken();
  if (!accessToken) {
    throw new Error('Not authenticated');
  }

  const requestOptions: RequestInit = {
    method: options.method,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${accessToken}`,
    },
    cache: 'no-store',
  };

  if (options.body !== undefined) {
    requestOptions.body = JSON.stringify(options.body);
  }

  return fetch(`${apiUrl}${endpoint}`, requestOptions);
}
