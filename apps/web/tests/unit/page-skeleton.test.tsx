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
    render(
      <PageSkeletonView
        status="Cargando la página…"
        toolbar={{
          filters: [{ kind: 'filter', label: 'Todas' }],
          actions: [{ kind: 'add', label: 'Agregar' }],
        }}
        body="table"
      />,
    );

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

  it('reserves a header warning only when told to, and never shows its text', () => {
    const { rerender } = render(
      <PageSkeletonView
        status="Loading"
        title="Dashboard"
        notice="Showing values in ARS."
        body="dashboard"
      />,
    );
    // The text sizes the placeholder but must not be readable (its figure is a stand-in); jsdom loads
    // no stylesheet, so the class is what can be asserted.
    expect(screen.getByText('Showing values in ARS.')).toHaveClass('invisible');

    rerender(<PageSkeletonView status="Loading" title="Dashboard" body="dashboard" />);
    expect(screen.queryByText('Showing values in ARS.')).not.toBeInTheDocument();
  });
});
