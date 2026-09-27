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
  disabled?: boolean;
  // Accessible name for the group. Radix already gives the root `role="group"`, but the items only
  // carry their own words — so without this a screen reader announces the choices and never the
  // question. Optional because a caller with a visible, adjacent heading may already answer it.
  ariaLabel?: string;
  itemClassName?: string;
  className?: string;
}

/*
 * Blue pill-style toggle group used across the dashboard (period picker, distribution, currency).
 *
 * `shrink-0` is load-bearing. The root needs `overflow-hidden` to clip the items' backgrounds to the
 * pill, and an element with `overflow` other than visible has an automatic minimum size of ZERO in a
 * flex row — so beside a title in a card header the group shrank below its own labels and cut them
 * off mid-word ("Por colección" lost 19px at 390px). Not shrinking, the labels always show whole and
 * the row around it has to make room, which is the layout's job and not the control's.
 */
export function PillToggleGroup({
  items,
  value,
  onValueChange,
  disabled,
  ariaLabel,
  itemClassName,
  className,
}: PillToggleGroupProps) {
  return (
    <ToggleGroup
      type="single"
      value={value}
      onValueChange={(v) => v && onValueChange(v)}
      disabled={disabled}
      aria-label={ariaLabel}
      variant="outline"
      size="sm"
      className={cn(
        'shrink-0 border border-border bg-white rounded-full overflow-hidden shadow-xs',
        className,
      )}
    >
      {items.map((item) => (
        <ToggleGroupItem
          key={item.value}
          value={item.value}
          className={cn(
            'border-0 data-[state=on]:bg-blue-800 data-[state=on]:text-white transition-all duration-200 focus-visible:outline-none focus-visible:bg-accent focus-visible:animate-pulse-scale',
            itemClassName,
          )}
        >
          {item.label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}
