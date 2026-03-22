'use client';

import { useState } from 'react';
import { Search } from 'lucide-react';

import {
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

export interface SmartSearchItem {
  id: string;
  label: string;
  icon?: React.ReactNode;
}

export interface SmartSearchGroup {
  heading: string;
  items: SmartSearchItem[];
}

interface SmartSearchProps {
  groups: SmartSearchGroup[];
  placeholder: string;
  inputPlaceholder: string;
  emptyMessage: string;
  onSelect: (groupIndex: number, itemId: string) => void;
  surface?: boolean;
  className?: string;
}

export function SmartSearch({
  groups,
  placeholder,
  inputPlaceholder,
  emptyMessage,
  onSelect,
  surface = false,
  className,
}: SmartSearchProps) {
  const [open, setOpen] = useState(false);

  function handleSelect(groupIndex: number, itemId: string) {
    setOpen(false);
    onSelect(groupIndex, itemId);
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          className={cn(
            'flex h-9 w-full min-w-48 items-center px-3 gap-x-2 border rounded-lg shadow-xs',
            'transition-[border-color,box-shadow] duration-200 ease-in-out',
            'hover:border-ring focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none',
            'text-paragraph-sm text-muted-foreground',
            surface ? 'bg-background' : 'bg-input',
            'border-border',
            className,
          )}
          onClick={() => setOpen(true)}
        >
          <Search className="size-4 shrink-0 text-muted-foreground" />
          {placeholder}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-(--radix-popover-trigger-width) p-0" align="start">
        <Command>
          <CommandInput placeholder={inputPlaceholder} />
          <CommandList>
            <CommandEmpty>{emptyMessage}</CommandEmpty>
            {groups.map((group, groupIndex) =>
              group.items.length > 0 ? (
                <CommandGroup key={group.heading} heading={group.heading}>
                  {group.items.map((item) => (
                    <CommandItem
                      key={item.id}
                      value={`${group.heading} ${item.label}`}
                      onSelect={() => handleSelect(groupIndex, item.id)}
                    >
                      {item.icon}
                      {item.label}
                    </CommandItem>
                  ))}
                </CommandGroup>
              ) : null,
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
