import { render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { LanguageAutoSync } from '@/app/(protected)/_components/language-auto-sync';
import {
  seedLocaleCookie,
  syncBrowserLanguage,
} from '@/app/(protected)/_components/language-auto-sync-actions';
import { TimezoneAutoSync } from '@/app/(protected)/_components/timezone-auto-sync';
import {
  seedTimezoneCookie,
  syncBrowserTimezone,
} from '@/app/(protected)/_components/timezone-auto-sync-actions';
import { detectBrowserTimezone } from '@/lib/constants/timezones';

/*
 * What the protected layout's two sync mounts do with this browser's cookies.
 *
 * 'manual' pins the account's value: it is never overwritten from the browser, and a cookie that is
 * absent (fresh browser, or logout dropped it) or names something else is re-seeded from the pin, so
 * the cookie the root error boundary reads agrees with the render. 'auto' keeps following the browser
 * exactly as before and never seeds.
 */

vi.mock('@/app/(protected)/_components/language-auto-sync-actions', () => ({
  seedLocaleCookie: vi.fn(() => Promise.resolve()),
  syncBrowserLanguage: vi.fn(() => Promise.resolve()),
}));

vi.mock('@/app/(protected)/_components/timezone-auto-sync-actions', () => ({
  seedTimezoneCookie: vi.fn(() => Promise.resolve()),
  syncBrowserTimezone: vi.fn(() => Promise.resolve()),
}));

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(navigator, 'language', 'get').mockReturnValue('en-US');
});

describe('LanguageAutoSync', () => {
  it('seeds the cookie from a manual language when the browser has none', () => {
    render(<LanguageAutoSync storedLanguage="es" storedMode="manual" localeCookie={null} />);
    expect(seedLocaleCookie).toHaveBeenCalledWith('es');
    expect(syncBrowserLanguage).not.toHaveBeenCalled();
  });

  it('re-seeds a cookie that names another locale than the manual one', () => {
    render(<LanguageAutoSync storedLanguage="es" storedMode="manual" localeCookie="en" />);
    expect(seedLocaleCookie).toHaveBeenCalledWith('es');
    expect(syncBrowserLanguage).not.toHaveBeenCalled();
  });

  it('leaves a cookie that already agrees with the manual language alone', () => {
    render(<LanguageAutoSync storedLanguage="es" storedMode="manual" localeCookie="es" />);
    expect(seedLocaleCookie).not.toHaveBeenCalled();
    expect(syncBrowserLanguage).not.toHaveBeenCalled();
  });

  it('follows the browser in auto and never seeds', () => {
    render(<LanguageAutoSync storedLanguage="es" storedMode="auto" localeCookie={null} />);
    expect(syncBrowserLanguage).toHaveBeenCalledWith('en');
    expect(seedLocaleCookie).not.toHaveBeenCalled();
  });
});

describe('TimezoneAutoSync', () => {
  const pinned = 'Asia/Tokyo';
  const other = 'America/New_York';

  it('seeds the cookie from a manual zone when the browser has none', () => {
    render(<TimezoneAutoSync storedTimezone={pinned} storedMode="manual" timezoneCookie={null} />);
    expect(seedTimezoneCookie).toHaveBeenCalledWith(pinned);
    expect(syncBrowserTimezone).not.toHaveBeenCalled();
  });

  it('re-seeds a cookie that names another zone than the manual one', () => {
    render(<TimezoneAutoSync storedTimezone={pinned} storedMode="manual" timezoneCookie={other} />);
    expect(seedTimezoneCookie).toHaveBeenCalledWith(pinned);
    expect(syncBrowserTimezone).not.toHaveBeenCalled();
  });

  it('leaves a cookie that already agrees with the manual zone alone', () => {
    render(
      <TimezoneAutoSync storedTimezone={pinned} storedMode="manual" timezoneCookie={pinned} />,
    );
    expect(seedTimezoneCookie).not.toHaveBeenCalled();
    expect(syncBrowserTimezone).not.toHaveBeenCalled();
  });

  it('follows the browser in auto and never seeds', () => {
    const browserTz = detectBrowserTimezone();
    const stored = browserTz === pinned ? other : pinned;
    render(<TimezoneAutoSync storedTimezone={stored} storedMode="auto" timezoneCookie={null} />);
    expect(syncBrowserTimezone).toHaveBeenCalledWith(browserTz);
    expect(seedTimezoneCookie).not.toHaveBeenCalled();
  });
});
