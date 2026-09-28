'use client';

import { useState } from 'react';
import { Check } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
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
import { TruncatingTooltip } from '@/components/truncating-tooltip';
import { CATEGORY_ALL } from '@/lib/constants/api-constants';

interface FilterComboboxProps {
  // Concrete option values; the CATEGORY_ALL sentinel is prepended internally.
  items: readonly string[];
  value: string;
  onValueChange: (value: string) => void;
  // Label for a concrete option value.
  labelFor: (value: string) => string;
  // Label shown for the CATEGORY_ALL sentinel.
  allLabel: string;
  icon: LucideIcon;
  align?: 'start' | 'end';
  surface?: boolean;
  className?: string;
}

// Single-select filter combobox for list-page toolbars (all-sentinel + concrete options).
export function FilterCombobox({
  items,
  value,
  onValueChange,
  labelFor,
  allLabel,
  icon: Icon,
  align = 'start',
  surface = false,
  className,
}: FilterComboboxProps) {
  const tCommon = useTranslations('common');
  const [open, setOpen] = useState(false);

  const isAll = value === CATEGORY_ALL;
  const label = isAll ? allLabel : labelFor(value);
  const options = [CATEGORY_ALL, ...items];

  function handleSelect(selected: string) {
    onValueChange(selected);
    setOpen(false);
  }

  return (
    <div className={className}>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            data-testid="filter-combobox-trigger"
            className={cn(
              'h-9 w-full justify-between px-3 gap-x-2 border-border shadow-xs',
              'text-paragraph-sm font-normal',
              isAll ? 'text-muted-foreground' : 'text-foreground',
              'hover:border-border-3',
              'focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring',
              surface ? 'bg-background' : 'bg-input',
            )}
          >
            {/*
             * The label truncates in its own block: `truncate` on the flex row around it draws no
             * ellipsis (the text is just cut). The tooltip gives the whole label back, only when cut.
             */}
            <span className="flex min-w-0 items-center gap-x-2">
              <Icon className="size-4 shrink-0" />
              <TruncatingTooltip text={label} className="block" />
            </span>
            <ComboboxChevron open={open} />
          </Button>
        </PopoverTrigger>
        <PopoverContent
          className="sm:min-w-78 w-(--radix-popover-trigger-width) p-0"
          align={align}
          sideOffset={8}
        >
          <Command>
            <CommandList>
              <CommandEmpty>{tCommon('combobox.empty')}</CommandEmpty>
              <CommandGroup>
                {options.map((option) => {
                  const isSelected = value === option;
                  const optionLabel = option === CATEGORY_ALL ? allLabel : labelFor(option);
                  return (
                    <CommandItem
                      key={option}
                      value={optionLabel}
                      onSelect={() => handleSelect(option)}
                    >
                      <Check
                        className={cn(
                          'size-4 shrink-0 transition-all duration-150',
                          isSelected ? 'scale-100 opacity-100' : 'scale-0 opacity-0',
                        )}
                      />
                      {optionLabel}
                    </CommandItem>
                  );
                })}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
    </div>
  );
}
