'use client';

import { useRef, useState } from 'react';
import { ChevronDown } from 'lucide-react';

import {
  Button,
  Command,
  CommandEmpty,
  CommandInput,
  CommandItem,
  CommandList,
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import { IANA_TIMEZONES } from '@/lib/constants/timezones';

interface TimezoneComboboxProps {
  value: string | null;
  placeholder: string;
  searchPlaceholder: string;
  noResults: string;
  surface?: boolean;
  disabled?: boolean;
  onChange: (tz: string) => void;
  'aria-invalid'?: boolean | 'true' | 'false';
}

export function TimezoneCombobox({
  value,
  placeholder,
  searchPlaceholder,
  noResults,
  surface = false,
  disabled = false,
  onChange,
  'aria-invalid': ariaInvalid,
}: TimezoneComboboxProps) {
  const hasError = ariaInvalid === true || ariaInvalid === 'true';
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const listRef = useRef<HTMLDivElement>(null);
  const q = search.toLowerCase();

  const filtered = q ? IANA_TIMEZONES.filter((tz) => tz.toLowerCase().includes(q)) : IANA_TIMEZONES;

  function handleSearch(v: string) {
    setSearch(v);
    if (!v)
      requestAnimationFrame(() => {
        if (listRef.current) listRef.current.scrollTop = 0;
      });
  }

  return (
    <Popover open={disabled ? false : open} onOpenChange={disabled ? undefined : setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="lg"
          disabled={disabled}
          className={cn(
            'w-full min-w-0 justify-between group has-focus-visible:border-ring has-focus-visible:ring-3 has-focus-visible:ring-ring/50 font-normal',
            surface
              ? 'bg-background hover:bg-background aria-expanded:bg-background'
              : 'bg-input hover:bg-input aria-expanded:bg-input dark:bg-input dark:hover:bg-input dark:aria-expanded:bg-input',
            hasError &&
              'border-destructive focus-visible:border-destructive focus-visible:ring-destructive/20',
          )}
        >
          <span className={cn('truncate text-paragraph-sm', !value && 'text-muted-foreground')}>
            {value || placeholder}
          </span>
          <ChevronDown className="shrink-0 size-4 opacity-50 transition-transform group-aria-expanded:rotate-180" />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        className="w-(--radix-popover-trigger-width) p-0"
        align="start"
        sideOffset={4}
      >
        <Command shouldFilter={false}>
          <CommandInput
            placeholder={searchPlaceholder}
            value={search}
            onValueChange={handleSearch}
          />
          <CommandList ref={listRef}>
            <CommandEmpty>{noResults}</CommandEmpty>
            {filtered.map((tz) => (
              <CommandItem
                key={tz}
                value={tz}
                onSelect={() => {
                  onChange(tz);
                  setOpen(false);
                }}
              >
                <span className="truncate text-paragraph-sm">{tz}</span>
              </CommandItem>
            ))}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
