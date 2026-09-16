import 'server-only';

import { AdminForbiddenError } from '@/lib/api/types';
import type { Page } from '@/lib/api/types';
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

interface FeedbackListRaw {
  items: FeedbackRaw[];
  total: number;
  page: number;
  page_size: number;
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
export async function getFeedback(page = 1): Promise<Page<Feedback>> {
  const res = await authenticatedFetch(`/feedback?page=${page}`, { method: 'GET' });
  if (res.status === 403) throw new AdminForbiddenError();
  if (!res.ok) throw new Error('Failed to fetch feedback');
  const raw: FeedbackListRaw = await res.json();
  return { items: raw.items.map(mapFeedback), total: raw.total, pageSize: raw.page_size };
}
