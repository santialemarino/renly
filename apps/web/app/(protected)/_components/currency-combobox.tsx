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

// Meta/test codes that are not real currencies.
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

interface CurrencyComboboxProps {
  value: string | null;
  exclude: string[];
  placeholder: string;
  searchPlaceholder: string;
  noResults: string;
  surface?: boolean;
  compact?: boolean;
  onChange: (code: string) => void;
  onClear?: () => void;
  'aria-invalid'?: boolean | 'true' | 'false';
}
export function CurrencyCombobox({
  value,
  exclude,
  placeholder,
  searchPlaceholder,
  noResults,
  surface = false,
  compact = false,
  onChange,
  onClear,
  'aria-invalid': ariaInvalid,
}: CurrencyComboboxProps) {
  const hasError = ariaInvalid === true || ariaInvalid === 'true';
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [clearing, setClearing] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const typeaheadBuffer = useRef('');
  const typeaheadTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
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
        <Button
          variant="outline"
          size="lg"
          onKeyDown={(e) => {
            if (e.key === 'Backspace' && value && onClear) {
              e.preventDefault();
              setClearing(true);
              setTimeout(() => {
                onClear();
                setClearing(false);
              }, CLEAR_ANIMATION_MS);
              return;
            }
            if (e.key.length !== 1 || e.ctrlKey || e.metaKey || e.altKey) return;
            const ch = e.key.toUpperCase();
            typeaheadBuffer.current += ch;
            if (typeaheadTimer.current) clearTimeout(typeaheadTimer.current);
            typeaheadTimer.current = setTimeout(() => {
              typeaheadBuffer.current = '';
            }, 500);
            const q = typeaheadBuffer.current;
            const match = ALL_CURRENCIES.find(
              (c) => !exclude.includes(c.code) && c.code.startsWith(q),
            );
            if (match) onChange(match.code);
          }}
          className={cn(
            'justify-between w-full min-w-0 group font-normal has-focus-visible:border-ring has-focus-visible:ring-3 has-focus-visible:ring-ring/50',
            surface
              ? 'bg-background hover:bg-background aria-expanded:bg-background'
              : 'bg-input hover:bg-input aria-expanded:bg-input dark:bg-input dark:hover:bg-input dark:aria-expanded:bg-input',
            hasError &&
              'border-destructive focus-visible:border-destructive focus-visible:ring-destructive/20',
          )}
        >
          {value ? (
            <span
              className={cn(
                'inline-flex min-w-0 items-center gap-x-2 overflow-hidden text-foreground transition-opacity duration-100',
                clearing && 'opacity-0',
              )}
            >
              <span className="shrink-0 text-paragraph-mini font-mono">{value}</span>
              {!compact && (
                <span className="text-paragraph-sm truncate">{getCurrencyName(value)}</span>
              )}
              {getCurrencyFlag(value) && <span className="shrink-0">{getCurrencyFlag(value)}</span>}
            </span>
          ) : (
            <span className="min-w-0 text-muted-foreground animate-in fade-in duration-100 truncate">
              {placeholder}
            </span>
          )}
          <span className="inline-flex shrink-0 items-center gap-x-1 ml-auto">
            {onClear && value && (
              <span
                role="button"
                aria-label="Clear"
                tabIndex={0}
                onClick={handleClear}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    handleClear(e as unknown as React.MouseEvent);
                  }
                }}
                className="shrink-0 p-0.5 rounded text-muted-foreground opacity-50 transition-[opacity,transform] duration-150 hover:opacity-100 hover:scale-110 focus-visible:outline-none focus-visible:opacity-100 focus-visible:scale-110"
              >
                <X className="size-3.5" />
              </span>
            )}
            <ChevronDown className="shrink-0 size-4 text-muted-foreground opacity-50 transition-transform duration-200 group-data-[state=open]:rotate-180" />
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
            autoFocus
            value={search}
            onValueChange={handleSearch}
            placeholder={compact ? 'Search...' : searchPlaceholder}
          />
          <Separator />
          <CommandList
            ref={listRef}
            className="pr-1 [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-border"
            onWheel={(e) => e.stopPropagation()}
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
                  {!compact && <span className="truncate text-paragraph-sm">{currency.name}</span>}
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
