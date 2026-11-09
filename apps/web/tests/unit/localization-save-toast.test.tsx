import type { ComponentProps } from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { LocalizationForm } from '@/app/(protected)/localization/_components/localization-form';
import type { SettingsData } from '@/lib/api/settings';
import en from '../../translations/en.json';
import es from '../../translations/es.json';

/*
 * Saving the localization settings confirms itself in the language just saved. Switching English to
 * Spanish once showed "Localization settings saved." on a page that had just turned Spanish, because
 * the toast was raised with the translator of the render that submitted — the old language's.
 *
 * The form starts with Spanish chosen while the page is still English (what picking it does), and the
 * page re-rendering in Spanish after the save is the provider changing locale here.
 */

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock('sonner', () => ({ toast }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
vi.mock('@/app/(protected)/localization/localization-actions', () => ({
  saveLocalization: vi.fn().mockResolvedValue(undefined),
}));

// The pickers are Radix, which this suite cannot mount; the save path does not touch them.
vi.mock('@/app/(protected)/_components/timezone-combobox', () => ({
  TimezoneCombobox: () => null,
}));
vi.mock('@/components/form-combobox', () => ({ FormCombobox: () => null }));
vi.mock('@/components/pill-toggle-group', () => ({ PillToggleGroup: () => null }));
vi.mock('@repo/ui/components', () => ({
  Button: (props: ComponentProps<'button'> & { blue?: boolean }) => (
    <button {...Object.fromEntries(Object.entries(props).filter(([name]) => name !== 'blue'))} />
  ),
  Hint: (props: ComponentProps<'p'>) => <p {...props} />,
  Label: (props: ComponentProps<'label'>) => <label {...props} />,
  Separator: () => <hr />,
}));

function form(locale: 'en' | 'es', language: 'en' | 'es') {
  const settings = {
    timezone: 'America/Argentina/Buenos_Aires',
    timezoneMode: 'manual',
    language,
    languageMode: 'manual',
  } as SettingsData;
  return (
    <NextIntlClientProvider locale={locale} messages={locale === 'en' ? en : es} timeZone="UTC">
      <LocalizationForm initialSettings={settings} />
    </NextIntlClientProvider>
  );
}

async function save() {
  await act(async () => {
    fireEvent.submit(screen.getByRole('button', { name: /save|guardar/i }).closest('form')!);
  });
}

beforeEach(() => {
  toast.success.mockReset();
});

describe('the localization save confirmation', () => {
  it('is said in the language just chosen', async () => {
    const { rerender } = render(form('en', 'es'));
    await save();
    expect(toast.success).not.toHaveBeenCalledWith(
      en.localization.form.saveSuccess,
      expect.anything(),
    );

    // The page re-renders in Spanish.
    rerender(form('es', 'es'));
    expect(toast.success).toHaveBeenCalledTimes(1);
    expect(toast.success).toHaveBeenCalledWith(es.localization.form.saveSuccess, {
      id: 'localization-save',
    });
  });

  it('is said at once when the language did not change', async () => {
    render(form('en', 'en'));
    await save();
    expect(toast.success).toHaveBeenCalledWith(en.localization.form.saveSuccess, {
      id: 'localization-save',
    });
  });
});
