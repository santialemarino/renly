import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { SettingsData } from '@/lib/api/settings';
import requestConfigExport from '../../i18n/request';

/*
 * Which language and zone a request renders in, driven through the real `i18n/request.ts`.
 *
 * The locale cookie belongs to the browser — logout drops it and a fresh browser never had it — while
 * a 'manual' language belongs to the account. So a signed-in user who pinned Spanish must get Spanish
 * on the first render after a login, and on a browser whose cookie still says English; a user on
 * 'auto' keeps following the cookie and then the browser. The timezone follows the same rule.
 */

const req = vi.hoisted(() => ({
  cookies: {} as Record<string, string>,
  acceptLanguage: null as string | null,
  session: null as { user: { accessToken: string; error?: string } } | null,
  settings: null as Partial<SettingsData> | null,
}));

vi.mock('next/headers', () => ({
  cookies: async () => ({
    get: (name: string) => (name in req.cookies ? { name, value: req.cookies[name] } : undefined),
  }),
  headers: async () =>
    new Headers(req.acceptLanguage ? { 'accept-language': req.acceptLanguage } : {}),
}));

vi.mock('next-intl/server', () => ({
  getRequestConfig: (factory: unknown) => factory,
}));

vi.mock('@/lib/auth', () => ({
  getSession: async () => req.session,
  isAuthenticatedSession: (session: typeof req.session) => !!session?.user && !session.user.error,
}));

vi.mock('@/lib/api/settings', () => ({
  getSettings: async () => {
    if (!req.settings) throw new Error('Failed to fetch settings');
    return req.settings;
  },
}));

// `getRequestConfig` is mocked to return the factory itself, so the default export IS the resolver.
const requestConfig = requestConfigExport as unknown as () => Promise<{
  locale: string;
  timeZone?: string;
}>;

function signedIn(settings: Partial<SettingsData>) {
  req.session = { user: { accessToken: 'token' } };
  req.settings = settings;
}

beforeEach(() => {
  req.cookies = {};
  req.acceptLanguage = 'en-US,en;q=0.9';
  req.session = null;
  req.settings = null;
});

describe('request locale', () => {
  it('renders a manual language when the browser has no locale cookie', async () => {
    signedIn({ language: 'es', languageMode: 'manual' });
    expect((await requestConfig()).locale).toBe('es');
  });

  it('renders a manual language over a cookie naming another locale', async () => {
    signedIn({ language: 'es', languageMode: 'manual' });
    req.cookies.NEXT_LOCALE = 'en';
    expect((await requestConfig()).locale).toBe('es');
  });

  it('follows the cookie, then the browser, when the language is auto', async () => {
    signedIn({ language: 'es', languageMode: 'auto' });
    expect((await requestConfig()).locale).toBe('en');
    req.cookies.NEXT_LOCALE = 'es';
    req.acceptLanguage = 'en-US';
    signedIn({ language: 'en', languageMode: 'auto' });
    expect((await requestConfig()).locale).toBe('es');
  });

  it('treats a null mode as auto', async () => {
    signedIn({ language: 'es', languageMode: null });
    expect((await requestConfig()).locale).toBe('en');
  });

  it('ignores a pin it cannot render and falls back to the cookie and browser', async () => {
    signedIn({ language: 'fr', languageMode: 'manual' });
    req.acceptLanguage = 'es-AR';
    expect((await requestConfig()).locale).toBe('es');
  });

  it('falls back to the cookie and browser for a visitor, an errored session, or unreadable settings', async () => {
    req.acceptLanguage = 'es-AR';
    expect((await requestConfig()).locale).toBe('es');

    req.session = { user: { accessToken: 'token', error: 'RefreshTokenError' } };
    req.settings = { language: 'en', languageMode: 'manual' };
    expect((await requestConfig()).locale).toBe('es');

    req.session = { user: { accessToken: 'token' } };
    req.settings = null;
    expect((await requestConfig()).locale).toBe('es');
  });
});

describe('request timezone', () => {
  it('renders a manual zone when the browser has no timezone cookie', async () => {
    signedIn({ timezone: 'Asia/Tokyo', timezoneMode: 'manual' });
    expect((await requestConfig()).timeZone).toBe('Asia/Tokyo');
  });

  it('renders a manual zone over a cookie naming another zone', async () => {
    signedIn({ timezone: 'Asia/Tokyo', timezoneMode: 'manual' });
    req.cookies.NEXT_TIMEZONE = 'America/New_York';
    expect((await requestConfig()).timeZone).toBe('Asia/Tokyo');
  });

  it('follows the cookie, else the ambient zone, when the zone is auto', async () => {
    signedIn({ timezone: 'Asia/Tokyo', timezoneMode: 'auto' });
    expect((await requestConfig()).timeZone).toBeUndefined();
    req.cookies.NEXT_TIMEZONE = 'America/New_York';
    expect((await requestConfig()).timeZone).toBe('America/New_York');
  });

  it('ignores an unknown pinned zone', async () => {
    signedIn({ timezone: 'Mars/Olympus', timezoneMode: 'manual' });
    req.cookies.NEXT_TIMEZONE = 'America/New_York';
    expect((await requestConfig()).timeZone).toBe('America/New_York');
  });
});
