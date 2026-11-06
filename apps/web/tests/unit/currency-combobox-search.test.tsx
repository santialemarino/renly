import { createElement, type ReactNode } from 'react';
import { render } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import { describe, expect, it, vi } from 'vitest';

import { CurrencyCombobox } from '@/app/(protected)/_components/currency-combobox';
import en from '../../translations/en.json';
import es from '../../translations/es.json';

/*
 * The currency combobox's search field is placeholdered in the reader's language at both sizes: the
 * caller's own placeholder at full size, and a short translated "Search..." in the compact trigger
 * (too narrow for "Search currencies..."), which was once a hardcoded English string.
 *
 * The Radix and cmdk pieces resolve a second React copy under jsdom, so `@repo/ui/components` is
 * replaced by plain elements that always render their children: the search field is in the DOM
 * without opening anything.
 */

vi.mock('@repo/ui/components', () => {
  const plain = (tag: string) =>
    function Plain({ children, ...props }: Record<string, unknown> & { children?: ReactNode }) {
      const rest = Object.fromEntries(
        Object.entries(props).filter(
          ([key]) =>
            !['asChild', 'variant', 'size', 'onValueChange', 'shouldFilter', 'heading'].includes(
              key,
            ),
        ),
      );
      return createElement(tag, rest, children);
    };
  return {
    Button: plain('button'),
    Command: plain('div'),
    CommandEmpty: plain('div'),
    CommandGroup: plain('div'),
    CommandInput: plain('input'),
    CommandItem: plain('div'),
    CommandList: plain('div'),
    Popover: plain('div'),
    PopoverContent: plain('div'),
    PopoverTrigger: plain('div'),
    Separator: plain('hr'),
    Tooltip: plain('span'),
    TooltipContent: plain('span'),
    TooltipTrigger: plain('span'),
  };
});

function searchPlaceholder(locale: 'en' | 'es', compact: boolean): string | null {
  const { container } = render(
    <NextIntlClientProvider locale={locale} messages={locale === 'en' ? en : es} timeZone="UTC">
      <CurrencyCombobox
        value={null}
        exclude={[]}
        placeholder="Currency"
        searchPlaceholder="Search currencies..."
        noResults="None"
        compact={compact}
        onChange={() => {}}
      />
    </NextIntlClientProvider>,
  );
  return container.querySelector('input')?.getAttribute('placeholder') ?? null;
}

describe('the currency search field', () => {
  it.each([
    ['en', 'Search...'],
    ['es', 'Buscar...'],
  ] as const)('is short and translated in the compact trigger (%s)', (locale, expected) => {
    expect(searchPlaceholder(locale, true)).toBe(expected);
  });

  it("takes the caller's placeholder at full size", () => {
    expect(searchPlaceholder('es', false)).toBe('Search currencies...');
  });
});
