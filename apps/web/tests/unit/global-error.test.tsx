import { act, render, screen } from '@testing-library/react';
import { createRoot } from 'react-dom/client';
import { renderToString } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

import GlobalError from '@/app/global-error';
import { GlobalErrorContent } from '@/components/global-error-content';

/*
 * The page that renders when the ROOT layout has failed must never render empty.
 *
 * An earlier version loaded its copy on demand after mount: the server render had no heading at all,
 * and a failed chunk load left the page blank forever — no text, no retry — on exactly the occasion
 * the page exists for. So both of the renders a visitor can be shown are asserted here: the very first
 * one (the server's HTML, before any effect or import could run) and the client's, in each locale. The
 * copy is literal so a boundary rendering the wrong locale, or a key path, cannot pass by agreement
 * with the file it read.
 */

vi.mock('next/navigation', () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
// The page's stylesheet and font are build-time concerns the unit environment cannot load.
vi.mock('@/app/globals.css', () => ({}));
vi.mock('next/font/google', () => ({ Plus_Jakarta_Sans: () => ({ className: 'font' }) }));

const COPY = {
  en: { title: 'Something went wrong', retry: 'Try again' },
  es: { title: 'Algo salió mal', retry: 'Reintentar' },
};

describe('global error page', () => {
  it('has a heading and a retry in its very first (server) render', () => {
    const html = renderToString(<GlobalError error={new Error('boom')} reset={() => {}} />);

    expect(html).toMatch(/<html[^>]*lang="en"/);
    expect(html).toMatch(new RegExp(`<h1[^>]*>${COPY.en.title}</h1>`));
    expect(html).toMatch(new RegExp(`<button[^>]*>.*${COPY.en.retry}.*</button>`, 's'));
    expect(html).toContain(`<title>${COPY.en.title}</title>`);
  });

  it.each(['en', 'es'] as const)('renders its heading, retry and title in %s', (locale) => {
    render(<GlobalErrorContent locale={locale} reset={() => {}} />);

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(COPY[locale].title);
    expect(screen.getByRole('button', { name: COPY[locale].retry })).toBeInTheDocument();
    expect(document.title).toBe(COPY[locale].title);
  });

  it('picks the visitor locale from the locale cookie in the browser', async () => {
    document.cookie = 'NEXT_LOCALE=es; path=/';
    const root = createRoot(document);
    await act(async () => {
      root.render(<GlobalError error={new Error('boom')} reset={() => {}} />);
    });

    expect(document.documentElement.lang).toBe('es');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(COPY.es.title);
    await act(async () => root.unmount());
    document.cookie = 'NEXT_LOCALE=; path=/; max-age=0';
  });
});
