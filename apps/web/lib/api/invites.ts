import 'server-only';

import { authenticatedFetch } from '@/lib/authenticated-fetch';

// --- Raw types (API JSON shape, snake_case) ---

interface InviteRaw {
  id: number;
  email: string;
  status: InviteStatus;
  invited_by: number;
  expires_at: string;
  consumed_at: string | null;
  created_at: string;
}

// --- Frontend types (camelCase) ---

export type InviteStatus = 'pending' | 'accepted' | 'revoked' | 'expired';

export interface Invite {
  id: number;
  email: string;
  status: InviteStatus;
  invitedBy: number;
  expiresAt: string;
  consumedAt: string | null;
  createdAt: string;
}

// Thrown when the API denies admin access (403). The /admin page maps this to a 404 so the page's
// existence stays hidden from non-admins (not a 403).
export class AdminForbiddenError extends Error {
  constructor() {
    super('admin_forbidden');
    this.name = 'AdminForbiddenError';
  }
}

// --- Mappers ---

function mapInvite(raw: InviteRaw): Invite {
  return {
    id: raw.id,
    email: raw.email,
    status: raw.status,
    invitedBy: raw.invited_by,
    expiresAt: raw.expires_at,
    consumedAt: raw.consumed_at,
    createdAt: raw.created_at,
  };
}

// --- API functions ---

export async function getInvites(): Promise<Invite[]> {
  const res = await authenticatedFetch('/admin/invites', { method: 'GET' });
  if (res.status === 403) throw new AdminForbiddenError();
  if (!res.ok) throw new Error('Failed to fetch invites');
  const raw: InviteRaw[] = await res.json();
  return raw.map(mapInvite);
}
