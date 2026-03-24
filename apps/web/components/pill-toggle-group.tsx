'use client';

import { ToggleGroup, ToggleGroupItem } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';

interface PillToggleGroupItem {
  value: string;
  label: string;
}

interface PillToggleGroupProps {
  items: PillToggleGroupItem[];
  value: string;
  onValueChange: (value: string) => void;
  itemClassName?: string;
  className?: string;
}

// Blue pill-style toggle group used across the dashboard (period picker, distribution, currency).
export function PillToggleGroup({
  items,
  value,
  onValueChange,
  itemClassName,
  className,
}: PillToggleGroupProps) {
  return (
    <ToggleGroup
      type="single"
      value={value}
      onValueChange={(v) => v && onValueChange(v)}
      variant="outline"
      size="sm"
      className={cn(
        'border border-border bg-white rounded-full overflow-hidden shadow-xs',
        className,
      )}
    >
      {items.map((item) => (
        <ToggleGroupItem
          key={item.value}
          value={item.value}
          className={cn(
            'border-0 data-[state=on]:bg-blue-800 data-[state=on]:text-white transition-all duration-200 focus-visible:outline-none focus-visible:bg-accent focus-visible:animate-[pulse-scale_0.3s_ease-in-out]',
            itemClassName,
          )}
        >
          {item.label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}
