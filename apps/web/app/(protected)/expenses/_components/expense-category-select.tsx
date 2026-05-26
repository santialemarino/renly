'use client';

import { useState } from 'react';
import { Check, ChevronsUpDown, Tag } from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';

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
import { CATEGORY_ALL } from '@/lib/constants/api-constants';
import { sortExpenseCategoriesByLabel } from '@/lib/utils/categories';

interface ExpenseCategorySelectProps {
  value: string;
  onValueChange: (value: string) => void;
  surface?: boolean;
  className?: string;
}

export function ExpenseCategorySelect({
  value,
  onValueChange,
  surface = false,
  className,
}: ExpenseCategorySelectProps) {
  const locale = useLocale();
  const t = useTranslations('expenses');
  const tCommon = useTranslations('common');
  const [open, setOpen] = useState(false);

  const isAll = value === CATEGORY_ALL;
  const label = isAll ? tCommon('allCategories') : t(`categories.${value}`);

  const sorted = sortExpenseCategoriesByLabel((key) => t(key), locale);
  const items = [CATEGORY_ALL, ...sorted];

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
            className={cn(
              'h-9 w-full justify-between px-3 gap-x-2 border-border shadow-xs',
              'text-paragraph-sm font-normal',
              isAll ? 'text-muted-foreground' : 'text-foreground',
              'hover:border-ring',
              'focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50',
              surface ? 'bg-background' : 'bg-input',
            )}
          >
            <span className="flex items-center gap-x-2 truncate">
              <Tag className="size-4 shrink-0" />
              {label}
            </span>
            <ChevronsUpDown className="size-3.5 shrink-0 opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent
          className="sm:min-w-78 w-(--radix-popover-trigger-width) p-0"
          align="start"
          sideOffset={8}
        >
          <Command>
            <CommandList>
              <CommandEmpty>{tCommon('groupFilter.empty')}</CommandEmpty>
              <CommandGroup>
                {items.map((cat) => {
                  const isSelected = value === cat;
                  const catLabel =
                    cat === CATEGORY_ALL ? tCommon('allCategories') : t(`categories.${cat}`);
                  return (
                    <CommandItem key={cat} value={catLabel} onSelect={() => handleSelect(cat)}>
                      <Check
                        className={cn(
                          'size-4 shrink-0 transition-all duration-150',
                          isSelected ? 'scale-100 opacity-100' : 'scale-0 opacity-0',
                        )}
                      />
                      {catLabel}
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
