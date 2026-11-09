import type { ComponentProps, ReactElement, ReactNode } from 'react';
import { render, screen, within } from '@testing-library/react';
import { createTranslator, NextIntlClientProvider } from 'next-intl';
import { describe, expect, it, vi } from 'vitest';

import { LandingCta } from '@/app/(public)/_components/landing-cta';
import { LandingHero } from '@/app/(public)/_components/landing-hero';
import { PublicHeader } from '@/app/(public)/_components/public-header';
import { ROUTES } from '@/config/routes';
import type { SignupMode } from '@/lib/auth-api';
import messages from '../../translations/en.json';

/*
 * The public CTAs follow the API's signup mode. While it is invite-only there is no signup a visitor
 * can use — an account starts from the link in an invite email — and "Request access" / "Create your
 * account" both led to a /signup page that could only say so. So in invite mode they are "Log in" and
 * "Have an invite?" (which explains the invite link), and in open mode the signup CTAs come back with
 * no change to the code.
 */

const state = vi.hoisted(() => ({ mode: 'invite' as SignupMode }));

vi.mock('server-only', () => ({}));
vi.mock('next-intl/server', async () => {
  const { createTranslator: create } = await import('next-intl');
  const copy = (await import('../../translations/en.json')).default;
  return {
    getTranslations: async (namespace: string) =>
      create({ locale: 'en', messages: copy, namespace: namespace as never }),
  };
});
vi.mock('@/lib/auth', () => ({
  getSession: async () => null,
  isAuthenticatedSession: () => false,
}));
vi.mock('@/lib/api/signup-context', () => ({
  getSignupContext: async () => ({ mode: state.mode }),
}));
vi.mock('@/app/(public)/_components/reveal', () => ({
  RevealGroup: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  RevealItem: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));
vi.mock('@/components/brand', () => ({ Brand: () => null }));
// An async server component, which a client render inside the hero cannot await: WHERE it is placed
// is asserted through this stand-in, and what it says by rendering the real one on its own below.
vi.mock('@/app/(public)/_components/invite-help', () => ({
  InviteHelp: () => <button type="button" data-testid="invite-help" />,
}));

// Radix cannot mount in this suite (a second React copy): plain stand-ins.
vi.mock('@repo/ui/components', () => {
  const passthrough = ({ children }: { children?: ReactNode }) => <div>{children}</div>;
  return {
    Button: ({
      asChild,
      children,
    }: ComponentProps<'button'> & { asChild?: boolean; blue?: boolean }) =>
      asChild ? children : <button type="button">{children}</button>,
    Popover: passthrough,
    PopoverContent: () => null,
    PopoverDescription: passthrough,
    PopoverHeader: passthrough,
    PopoverTitle: passthrough,
    PopoverTrigger: ({ children }: { children: ReactNode }) => children,
  };
});

const t = createTranslator({ locale: 'en', messages });

async function show(mode: SignupMode) {
  state.mode = mode;
  const parts = await Promise.all([
    PublicHeader(),
    LandingHero({ isAuthenticated: false, signupMode: mode }),
    LandingCta({ signupMode: mode }),
  ]);
  render(
    <NextIntlClientProvider locale="en" messages={messages} timeZone="UTC">
      {parts.map((part, index) => (
        <section key={index} data-testid={`part-${index}`}>
          {part as ReactElement}
        </section>
      ))}
    </NextIntlClientProvider>,
  );
  const [header, hero, cta] = parts.map((_, index) => within(screen.getByTestId(`part-${index}`)));
  return { header: header!, hero: hero!, cta: cta! };
}

function hrefs(scope: ReturnType<typeof within>) {
  return scope.queryAllByRole('link').map((link: HTMLElement) => link.getAttribute('href'));
}

describe('the public CTAs by signup mode', () => {
  it('offer no signup while signup is invite-only', async () => {
    const { header, hero, cta } = await show('invite');

    for (const part of [header, hero, cta]) {
      expect(hrefs(part)).not.toContain(ROUTES.auth.signup);
      expect(hrefs(part)).toContain(ROUTES.auth.login);
    }
    for (const part of [hero, cta]) {
      expect(part.getByTestId('invite-help')).toBeInTheDocument();
    }
    expect(cta.getByText(t('landing.cta.inviteSubtitle'))).toBeInTheDocument();
    expect(cta.queryByText(t('landing.cta.subtitle'))).not.toBeInTheDocument();
  });

  it('offer signup again once it is open', async () => {
    const { header, hero, cta } = await show('open');

    for (const part of [header, hero, cta]) {
      expect(hrefs(part)).toContain(ROUTES.auth.signup);
      expect(part.queryByTestId('invite-help')).toBeNull();
    }
    expect(cta.getByText(t('landing.cta.subtitle'))).toBeInTheDocument();
  });

  it('explain the invite link behind "Have an invite?"', async () => {
    const { InviteHelp } = await vi.importActual<
      typeof import('@/app/(public)/_components/invite-help')
    >('@/app/(public)/_components/invite-help');
    render(await InviteHelp({ size: 'lg' }));
    expect(screen.getByRole('button', { name: t('landing.invite.trigger') })).toBeInTheDocument();
  });
});
