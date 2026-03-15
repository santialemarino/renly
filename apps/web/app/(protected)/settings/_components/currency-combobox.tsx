'use client';

import { useRef, useState } from 'react';
import cc from 'currency-codes';
import { iso31661 } from 'iso-3166';
import { ChevronDown, X } from 'lucide-react';

import {
  Button,
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  Popover,
  PopoverContent,
  PopoverTrigger,
  Separator,
} from '@repo/ui/components';
import { cn } from '@repo/ui/lib';

const CLEAR_ANIMATION_MS = 100;

// Meta/test codes that are not real currencies
const EXCLUDED_CODES = new Set(['XXX', 'XTS']);

const ALL_CURRENCIES = cc.data
  .filter((c) => !EXCLUDED_CODES.has(c.code))
  .map((c) => ({ code: c.code, name: c.currency }))
  .sort((a, b) => a.code.localeCompare(b.code));

function getCurrencyName(code: string): string {
  return cc.code(code)?.currency ?? code;
}

// Allowlist of currently active ISO 3166-1 alpha-2 codes; dissolved regions are excluded.
const VALID_REGIONS = new Set(iso31661.map((c) => c.alpha2));

/*
 * Derives the flag emoji from the first two letters of the currency code (e.g. "USD" → "US" → 🇺🇸).
 * Returns null for supranational codes (X*) and any region not in the current ISO 3166-1 list.
 */
function getCurrencyFlag(code: string): string | null {
  if (code.startsWith('X')) return null;
  const country = code.slice(0, 2).toUpperCase();
  if (!VALID_REGIONS.has(country)) return null;
  return [...country].map((c) => String.fromCodePoint(0x1f1e6 - 65 + c.charCodeAt(0))).join('');
}

export function CurrencyCombobox({
  value,
  exclude,
  placeholder,
  searchPlaceholder,
  noResults,
  onChange,
  onClear,
}: {
  value: string | null;
  exclude: string[];
  placeholder: string;
  searchPlaceholder: string;
  noResults: string;
  onChange: (code: string) => void;
  onClear?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [clearing, setClearing] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const q = search.toLowerCase();
  // Pass 1 — filter: drop the sibling selected currency and any non-matching entries.
  // When q is empty every currency passes (only the excluded one is dropped).
  const filtered = ALL_CURRENCIES.filter(
    (c) =>
      !exclude.includes(c.code) &&
      (!q || c.code.toLowerCase().includes(q) || c.name.toLowerCase().includes(q)),
  ).sort((a, b) => {
    // Pass 2 — sort: no query → keep original alphabetical order from ALL_CURRENCIES.
    // With a query, score each match so the most relevant results bubble to the top:
    // 4 = exact code match, 3 = code prefix, 2 = name prefix, 1 = contains anywhere.
    if (!q) return 0;
    const score = (c: typeof a) => {
      const code = c.code.toLowerCase();
      const name = c.name.toLowerCase();
      if (code === q) return 4;
      if (code.startsWith(q)) return 3;
      if (name.startsWith(q)) return 2;
      return 1;
    };
    return score(b) - score(a);
  });

  function handleSearch(v: string) {
    setSearch(v);
    if (!v)
      requestAnimationFrame(() => {
        if (listRef.current) listRef.current.scrollTop = 0;
      });
  }

  function handleClear(e: React.MouseEvent) {
    e.stopPropagation();
    setClearing(true);
    setTimeout(() => {
      onClear!();
      setClearing(false);
    }, CLEAR_ANIMATION_MS);
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" className="justify-between w-full bg-white group">
          {value ? (
            <span
              className={cn(
                'inline-flex items-center gap-x-2 text-foreground transition-opacity duration-100',
                clearing && 'opacity-0',
              )}
            >
              <span className="text-paragraph-mini font-mono">{value}</span>
              <span className="text-paragraph-sm">{getCurrencyName(value)}</span>
            </span>
          ) : (
            <span className="text-muted-foreground animate-in fade-in duration-100">
              {placeholder}
            </span>
          )}
          <span className="inline-flex items-center gap-x-1 ml-auto">
            {onClear && value && (
              <span
                role="button"
                aria-label="Clear"
                onClick={handleClear}
                className="shrink-0 p-0.5 rounded text-muted-foreground hover:text-foreground"
              >
                <X className="size-3.5" />
              </span>
            )}
            <ChevronDown className="size-4 shrink-0 opacity-50 transition-transform duration-200 group-data-[state=open]:rotate-180" />
          </span>
        </Button>
      </PopoverTrigger>
      <PopoverContent
        className="w-(--radix-popover-trigger-width) p-0"
        align="start"
        sideOffset={8}
      >
        <Command shouldFilter={false} className="gap-y-2">
          <CommandInput
            value={search}
            onValueChange={handleSearch}
            placeholder={searchPlaceholder}
          />
          <Separator />
          <CommandList
            ref={listRef}
            className="pr-1 [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-border"
          >
            <CommandEmpty>{noResults}</CommandEmpty>
            <CommandGroup>
              {filtered.map((currency) => (
                <CommandItem
                  key={currency.code}
                  value={`${currency.code} ${currency.name}`}
                  onSelect={() => {
                    onChange(currency.code);
                    setOpen(false);
                  }}
                >
                  <span className="shrink-0 text-paragraph-mini font-mono">{currency.code}</span>
                  <span className="truncate text-paragraph-sm">{currency.name}</span>
                  {getCurrencyFlag(currency.code) && (
                    <span className="ml-auto shrink-0 pr-1">{getCurrencyFlag(currency.code)}</span>
                  )}
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
