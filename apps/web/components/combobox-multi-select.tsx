'use client';

import { useState } from 'react';
import { Check, ChevronsUpDown, X } from 'lucide-react';
import { AnimatePresence, motion } from 'motion/react';

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
} from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import { ANIMATION_DEFAULT, ANIMATION_FAST } from '@/lib/constants/animations';

export interface ComboboxItem {
  id: number;
  label: string;
}

interface ComboboxMultiSelectProps {
  items: ComboboxItem[];
  selectedIds: number[];
  onToggle: (id: number) => void;
  placeholder: string;
  searchPlaceholder: string;
  emptyMessage: string;
  icon?: React.ReactNode;
  showChips?: boolean;
  surface?: boolean;
  className?: string;
}

export function ComboboxMultiSelect({
  items,
  selectedIds,
  onToggle,
  placeholder,
  searchPlaceholder,
  emptyMessage,
  icon,
  showChips = false,
  surface = false,
  className,
}: ComboboxMultiSelectProps) {
  const [open, setOpen] = useState(false);

  const itemMap = new Map(items.map((item) => [item.id, item.label]));

  return (
    <div className={cn('flex flex-col gap-y-2', className)}>
      {showChips && (
        <AnimatePresence initial={false}>
          {selectedIds.length > 0 && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: ANIMATION_DEFAULT }}
              style={{ overflow: 'hidden', marginTop: -8 }}
            >
              <div className="flex flex-wrap gap-1.5" style={{ paddingTop: 8 }}>
                <AnimatePresence initial={false}>
                  {selectedIds.map((id) => (
                    <motion.span
                      key={id}
                      initial={{ opacity: 0, scale: 0.8 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={{ opacity: 0, scale: 0.8 }}
                      transition={{ duration: ANIMATION_FAST }}
                      className="inline-flex items-center gap-x-1 rounded-full border border-border bg-muted px-2.5 py-0.5 text-paragraph-mini"
                    >
                      {itemMap.get(id) ?? `#${id}`}
                      <button
                        type="button"
                        onClick={() => onToggle(id)}
                        className="rounded-full p-0.5 text-muted-foreground transition-[opacity,transform,color] duration-150 hover:scale-110 hover:text-destructive focus-visible:outline-none focus-visible:scale-110"
                      >
                        <X className="size-3" />
                      </button>
                    </motion.span>
                  ))}
                </AnimatePresence>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      )}

      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            className={cn(
              'h-9 w-full justify-between gap-x-2 border-border px-3 shadow-xs',
              'text-paragraph-sm font-normal',
              selectedIds.length > 0 ? 'text-foreground' : 'text-muted-foreground',
              'hover:border-ring',
              'focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50',
              surface ? 'bg-background' : 'bg-input',
            )}
          >
            <span className="flex items-center gap-x-2 truncate">
              {icon}
              {placeholder}
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
            <CommandInput placeholder={searchPlaceholder} />
            <CommandList>
              <CommandEmpty>{emptyMessage}</CommandEmpty>
              <CommandGroup>
                {items.map((item) => {
                  const isSelected = selectedIds.includes(item.id);
                  return (
                    <CommandItem
                      key={item.id}
                      value={item.label}
                      onSelect={() => onToggle(item.id)}
                    >
                      <Check
                        className={cn(
                          'size-4 shrink-0 transition-all duration-150',
                          isSelected ? 'scale-100 opacity-100' : 'scale-0 opacity-0',
                        )}
                      />
                      {item.label}
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
