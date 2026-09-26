import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { PageSkeletonView } from '@/app/(protected)/_components/page-skeleton';

/*
 * What a loading route tells assistive technology. The placeholders are grey boxes that say nothing,
 * so the whole signal is the busy region and the status line — before this component existed a slow
 * page showed the PREVIOUS page, unchanged, with `aria-busy` nowhere in the document.
 */

describe('PageSkeletonView', () => {
  it('marks the pending region busy and says what is happening', () => {
    render(<PageSkeletonView status="Cargando la página…" toolbar body="table" />);

    expect(screen.getByRole('status')).toHaveTextContent('Cargando la página…');
    expect(document.querySelectorAll('[aria-busy="true"]')).toHaveLength(1);
    // The busy region holds the placeholders, not the status line, which must stay announceable.
    expect(document.querySelector('[aria-busy="true"]')).not.toContainElement(
      screen.getByRole('status'),
    );
  });

  it('paints the real header when the page title is known', () => {
    render(
      <PageSkeletonView status="Loading" title="Expenses" subtitle="Track spending" body="table" />,
    );

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Expenses');
    expect(screen.getByText('Track spending')).toBeInTheDocument();
  });

  it('paints a placeholder header when the title is data it cannot know', () => {
    render(<PageSkeletonView status="Loading" backLink body="sections" />);

    expect(screen.queryByRole('heading')).not.toBeInTheDocument();
  });
});
