import 'server-only';

import { authenticatedFetch } from '@/lib/authenticated-fetch';

// The signed-in user as the API has them NOW. Read here rather than from the session, whose copy of
// the name is the one from sign-in and goes stale the moment the user renames themselves.
export interface CurrentUser {
  name: string;
  email: string;
}

export async function getCurrentUser(): Promise<CurrentUser> {
  const res = await authenticatedFetch('/auth/me', { method: 'GET' });
  if (!res.ok) throw new Error('Failed to fetch the current user');
  const raw = (await res.json()) as { name: string; email: string };
  return { name: raw.name, email: raw.email };
}
