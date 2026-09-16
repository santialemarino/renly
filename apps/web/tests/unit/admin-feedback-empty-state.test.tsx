import { render, screen } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import { describe, expect, it, vi } from 'vitest';

import { AdminFeedback } from '@/app/(protected)/admin/feedback/_components/admin-feedback';
import type { Feedback } from '@/lib/api/feedback';
import en from '../../translations/en.json';

/*
 * "Nobody has ever sent feedback" and "this page holds none of it" are two different facts, and since
 * SEC-11 paginated this list they can differ: a page past the end is empty while the total is not.
 * Answering the second with the first strands the reader on `?page=9` looking at an empty state, with
 * no pager to step back with — the pager is inside the branch the empty state returns before.
 *
 * Driven through the component rather than through an extracted predicate because the rule IS the
 * branch: the thing worth guarding is which of the two subtrees renders, and a helper returning a
 * boolean would leave the interesting half untested. It mounts here because this component renders no
 * Radix primitive — `Table` and `Badge` are plain elements — which is what the web suite cannot do.
 */

// The pager reads the URL through next/navigation, which has no router in jsdom. Stubbed rather than
// wrapped in a provider: this test is about which subtree renders, and paging is asserted elsewhere.
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

function feedback(id: number): Feedback {
  return {
    id,
    email: `sender${id}@example.com`,
    category: 'idea',
    message: `Message ${id}`,
    createdAt: '2026-03-01T10:00:00Z',
  };
}

function renderAt(props: { feedback: Feedback[]; total: number; page: number }) {
  return render(
    <NextIntlClientProvider locale="en" messages={en} timeZone="America/Buenos_Aires">
      <AdminFeedback {...props} pageSize={25} />
    </NextIntlClientProvider>,
  );
}

describe('the admin feedback empty state', () => {
  it('says nobody has sent feedback only when nobody has', () => {
    renderAt({ feedback: [], total: 0, page: 1 });
    expect(screen.getByText(en.adminFeedback.empty)).toBeInTheDocument();
  });

  it('does NOT say that on an empty page of a list that has rows', () => {
    // The regression: page 9 of a 27-row list is empty, and the old test — the page's own length —
    // called that "no feedback yet".
    renderAt({ feedback: [], total: 27, page: 9 });
    expect(screen.queryByText(en.adminFeedback.empty)).not.toBeInTheDocument();
  });

  it('keeps the pager reachable on that empty page, so the reader can get back', () => {
    // What the wrong branch actually costs: the pager lives after the early return, so choosing it
    // strands the reader with no way back to page 1.
    renderAt({ feedback: [], total: 27, page: 9 });
    expect(screen.getByText('27 messages')).toBeInTheDocument();
  });

  it('renders the rows and the count when the page has some', () => {
    renderAt({ feedback: [feedback(1), feedback(2)], total: 27, page: 1 });
    expect(screen.getByText('Message 1')).toBeInTheDocument();
    expect(screen.getByText('27 messages')).toBeInTheDocument();
  });
});
