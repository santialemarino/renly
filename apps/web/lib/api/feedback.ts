import 'server-only';

import { AdminForbiddenError } from '@/lib/api/invites';
import { authenticatedFetch } from '@/lib/authenticated-fetch';
import type { FeedbackCategory } from '@/lib/constants/feedback';

// --- Raw types (API JSON shape, snake_case) ---

interface FeedbackRaw {
  id: number;
  email: string;
  category: FeedbackCategory;
  message: string;
  created_at: string;
}

// --- Frontend types (camelCase) ---

export interface Feedback {
  id: number;
  email: string;
  category: FeedbackCategory;
  message: string;
  createdAt: string;
}

// --- Mappers ---

function mapFeedback(raw: FeedbackRaw): Feedback {
  return {
    id: raw.id,
    email: raw.email,
    category: raw.category,
    message: raw.message,
    createdAt: raw.created_at,
  };
}

// --- API functions ---

// Lists all submitted feedback (admin only). Throws AdminForbiddenError on a 403 so the page can 404.
export async function getFeedback(): Promise<Feedback[]> {
  const res = await authenticatedFetch('/feedback', { method: 'GET' });
  if (res.status === 403) throw new AdminForbiddenError();
  if (!res.ok) throw new Error('Failed to fetch feedback');
  const raw: FeedbackRaw[] = await res.json();
  return raw.map(mapFeedback);
}
