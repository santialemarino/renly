'use client';

import * as React from 'react';
import { Check } from 'lucide-react';
import { useTranslations } from 'next-intl';

import {
  Button,
  Command,
  CommandEmpty,
  CommandGroup,
  CommandItem,
  CommandList,
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import { ComboboxChevron } from '@/components/combobox-chevron';

// How long a typed prefix is remembered before the blind type-ahead buffer resets (native <select> feel).
const TYPEAHEAD_RESET_MS = 600;

export interface FormComboboxOption {
  // The stable value passed to onValueChange. Values are strings, like Radix Select — number-valued
  // fields convert at the call site (value.toString() / Number(v)).
  value: string;
  // Shown in the trigger when selected, matched by type-ahead; also the row content unless `render` is set.
  label: string;
  // Extra terms type-ahead/highlight identity should include beyond the label (e.g. a code or synonym).
  keywords?: string[];
  // A leading icon rendered in the row (and, when this option is selected, in the trigger).
  icon?: React.ComponentType<{ className?: string }>;
  disabled?: boolean;
  // Custom row content (the row only — the trigger still shows `label`). For rich rows.
  render?: React.ReactNode;
  // Optional group heading. Ungrouped options render first; grouped options follow, headed, in
  // first-seen order.
  group?: string;
}

interface FormComboboxProps extends Omit<
  React.ComponentProps<typeof Button>,
  'value' | 'onChange' | 'children'
> {
  value: string;
  onValueChange: (value: string) => void;
  options: FormComboboxOption[];
  placeholder?: string;
  emptyText?: string;
  // Matches the base Select's `surface` prop — `bg-background` instead of `bg-input`.
  surface?: boolean;
  triggerClassName?: string;
  contentClassName?: string;
}

// The cmdk item identity string: label + keywords for type-ahead matching, value appended for uniqueness.
function itemValue(option: FormComboboxOption): string {
  return `${option.label} ${option.keywords?.join(' ') ?? ''} ${option.value}`;
}

/*
 * Single-select form-field combobox: a Popover + `Command` list behind a Button trigger. Preferred
 * over the base `Select` for form fields because Radix Popover animates open AND closed (Radix Select
 * snaps shut). It has no search box — like a native <select>, it supports blind type-ahead (typing
 * jumps the highlight to the first matching option) and arrow-key nav, so the list never filters or
 * resizes (no re-flip). Integrates with the form stack: wrap it in `<FormControl>` and it receives
 * id / aria-invalid / aria-describedby on the trigger, so the label, error ring, and FormMessage wire up.
 */
export const FormCombobox = React.forwardRef<HTMLButtonElement, FormComboboxProps>(
  function FormCombobox(
    {
      value,
      onValueChange,
      options,
      placeholder,
      emptyText,
      surface = false,
      disabled,
      triggerClassName,
      contentClassName,
      ...triggerProps
    },
    ref,
  ) {
    const tCommon = useTranslations('common');
    const [open, setOpen] = React.useState(false);
    // cmdk's currently-highlighted item value (controlled so type-ahead can move it).
    const [active, setActive] = React.useState('');
    const listRef = React.useRef<HTMLDivElement>(null);
    const typeahead = React.useRef<{ buffer: string; timer: ReturnType<typeof setTimeout> | null }>(
      {
        buffer: '',
        timer: null,
      },
    );

    const selected = options.find((option) => option.value === value);
    const SelectedIcon = selected?.icon;

    // Group options in first-seen order; ungrouped options share a leading headless group.
    const groups: { heading?: string; options: FormComboboxOption[] }[] = [];
    for (const option of options) {
      const heading = option.group;
      const existing = groups.find((g) => g.heading === heading);
      if (existing) existing.options.push(option);
      else groups.push({ heading, options: [option] });
    }

    function handleOpenChange(next: boolean) {
      setOpen(next);
      // Highlight the current value when opening so arrows/type-ahead start from it.
      if (next) setActive(selected ? itemValue(selected) : '');
    }

    function handleSelect(next: string) {
      onValueChange(next);
      setOpen(false);
    }

    // Blind type-ahead: printable keys build a prefix that jumps the highlight to the first matching
    // option (arrows/Enter stay with cmdk). No search box, so the list never filters or resizes.
    function handleTypeahead(event: React.KeyboardEvent<HTMLDivElement>) {
      if (event.key.length !== 1 || event.metaKey || event.ctrlKey || event.altKey) return;
      const state = typeahead.current;
      state.buffer += event.key.toLowerCase();
      if (state.timer) clearTimeout(state.timer);
      state.timer = setTimeout(() => {
        typeahead.current.buffer = '';
      }, TYPEAHEAD_RESET_MS);
      const match = options.find(
        (option) => !option.disabled && option.label.toLowerCase().startsWith(state.buffer),
      );
      if (match) {
        setActive(itemValue(match));
        event.preventDefault();
      }
    }

    return (
      <Popover open={open} onOpenChange={handleOpenChange}>
        <PopoverTrigger asChild>
          <Button
            ref={ref}
            type="button"
            role="combobox"
            aria-expanded={open}
            variant="outline"
            disabled={disabled}
            className={cn(
              'group/button h-9 w-full justify-between px-3 gap-x-2 border-border shadow-xs text-paragraph-sm font-normal',
              'hover:border-ring hover:bg-muted focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50',
              'aria-invalid:border-destructive aria-invalid:ring-destructive/20',
              selected ? 'text-foreground' : 'text-muted-foreground',
              surface ? 'bg-background' : 'bg-input',
              triggerClassName,
            )}
            {...triggerProps}
          >
            <span className="flex min-w-0 items-center gap-x-2 truncate">
              {SelectedIcon && <SelectedIcon className="size-4 shrink-0" />}
              <span className="truncate">{selected ? selected.label : placeholder}</span>
            </span>
            <ComboboxChevron open={open} />
          </Button>
        </PopoverTrigger>
        <PopoverContent
          className={cn('w-(--radix-popover-trigger-width) p-0', contentClassName)}
          align="start"
          sideOffset={8}
          // No search input to receive focus — focus the list so keydown (arrows + type-ahead) lands
          // inside the Command root.
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            listRef.current?.focus();
          }}
        >
          <Command value={active} onValueChange={setActive} shouldFilter={false}>
            <CommandList
              ref={listRef}
              tabIndex={0}
              onKeyDown={handleTypeahead}
              // Thin, rounded scrollbar (matches the currency/timezone comboboxes).
              className="pr-1 outline-none [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-border"
              // The Popover portals outside any open Dialog, whose react-remove-scroll lock otherwise
              // swallows wheel events over this list — stop propagation so wheel/touchpad scroll works.
              onWheel={(event) => event.stopPropagation()}
            >
              <CommandEmpty>{emptyText ?? tCommon('combobox.empty')}</CommandEmpty>
              {groups.map((group, index) => (
                <CommandGroup key={group.heading ?? `__ungrouped-${index}`} heading={group.heading}>
                  {group.options.map((option) => {
                    const OptionIcon = option.icon;
                    return (
                      <CommandItem
                        key={option.value}
                        // cmdk lowercases the value it passes to onSelect, so we ignore that arg and
                        // select the option's real value from the closure.
                        value={itemValue(option)}
                        disabled={option.disabled}
                        onSelect={() => handleSelect(option.value)}
                      >
                        <Check
                          className={cn(
                            'size-4 shrink-0 transition-all duration-150',
                            value === option.value ? 'scale-100 opacity-100' : 'scale-0 opacity-0',
                          )}
                        />
                        {OptionIcon && <OptionIcon className="size-4 shrink-0" />}
                        {option.render ?? option.label}
                      </CommandItem>
                    );
                  })}
                </CommandGroup>
              ))}
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
    );
  },
);
