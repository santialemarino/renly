import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { NextIntlClientProvider } from 'next-intl';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ErrorState } from '@/components/error-state';
import en from '../../translations/error-boundary/en.json';
import es from '../../translations/error-boundary/es.json';

/*
 * What every error boundary renders, and the one thing its retry has to do.
 *
 * The messages given to the provider are ONLY `common.errorBoundary`, because that is all
 * `app/global-error.tsx` can hand it: the root layout's provider is gone at that level. A component
 * that started reading any other key would render a raw key path on exactly the page that exists for
 * when everything else has failed — the key-path assertions are what catch it, since next-intl answers
 * a missing message with its own non-empty key path rather than with nothing.
 */

const router = vi.hoisted(() => ({ refresh: vi.fn() }));

vi.mock('next/navigation', () => ({
  useRouter: () => router,
}));

function renderIn(locale: 'en' | 'es', props: { showHomeLink?: boolean } = {}) {
  const errorBoundary = { en, es }[locale];
  const reset = vi.fn();
  render(
    <NextIntlClientProvider
      locale={locale}
      messages={{ common: { errorBoundary } }}
      onError={() => {}}
    >
      <ErrorState reset={reset} {...props} />
    </NextIntlClientProvider>,
  );
  return { reset };
}

beforeEach(() => {
  router.refresh.mockClear();
});

describe('ErrorState', () => {
  it.each(['en', 'es'] as const)(
    'renders its copy in %s from the error namespace alone',
    (locale) => {
      const copy = { en, es }[locale];
      renderIn(locale, { showHomeLink: true });

      expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(copy.title);
      expect(screen.getByText(copy.description)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: copy.retry })).toBeInTheDocument();
      expect(screen.getByRole('link', { name: copy.home })).toHaveAttribute('href', '/');
      // Any namespace: a key outside the one provided renders as its own dotted path, e.g. common.x.
      expect(document.body.textContent).not.toMatch(/\bcommon\./);
    },
  );

  it('offers the home link only where asked, since inside the shell the nav is still there', () => {
    renderIn('en');
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('retries by refreshing the server data AND clearing the boundary', async () => {
    // reset() alone re-renders the payload the router already holds — the error — so a retry that
    // skips the refresh fails again forever; a refresh without reset() leaves the boundary up.
    const { reset } = renderIn('en');
    await userEvent.click(screen.getByRole('button', { name: en.retry }));

    expect(router.refresh).toHaveBeenCalledTimes(1);
    expect(reset).toHaveBeenCalledTimes(1);
  });
});
