import { beforeEach, describe, expect, it, vi } from 'vitest';

import { seedLocalizationCookies } from '@/app/(auth)/login/login-actions';
import type { SettingsData } from '@/lib/api/settings';

/*
 * Login writes a pinned language and zone into the browser's cookies before the first signed-in
 * document: only a document load reads the pin from the settings, and the prefetches and client-side
 * navigations after it render from the cookies. A setting left on 'auto' writes nothing.
 */

const state = vi.hoisted(() => ({
  settings: {} as Partial<SettingsData>,
  seededLocale: [] as string[],
  seededTimezone: [] as string[],
}));

vi.mock('@/lib/api/settings', () => ({ getSettings: async () => state.settings }));
vi.mock('@/app/(protected)/_components/language-auto-sync-actions', () => ({
  seedLocaleCookie: async (value: string) => void state.seededLocale.push(value),
}));
vi.mock('@/app/(protected)/_components/timezone-auto-sync-actions', () => ({
  seedTimezoneCookie: async (value: string) => void state.seededTimezone.push(value),
}));

beforeEach(() => {
  state.seededLocale = [];
  state.seededTimezone = [];
});

describe('seedLocalizationCookies', () => {
  it('writes a pinned language and zone', async () => {
    state.settings = {
      language: 'es',
      languageMode: 'manual',
      timezone: 'Asia/Tokyo',
      timezoneMode: 'manual',
    };
    await seedLocalizationCookies();
    expect(state.seededLocale).toEqual(['es']);
    expect(state.seededTimezone).toEqual(['Asia/Tokyo']);
  });

  it('writes nothing for settings on auto', async () => {
    state.settings = {
      language: 'es',
      languageMode: 'auto',
      timezone: 'Asia/Tokyo',
      timezoneMode: null,
    };
    await seedLocalizationCookies();
    expect(state.seededLocale).toEqual([]);
    expect(state.seededTimezone).toEqual([]);
  });
});
