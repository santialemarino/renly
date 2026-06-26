import { ChevronDown } from 'lucide-react';

import { cn } from '@repo/ui/lib';

// Single source for a combobox/dropdown trigger chevron: consistent size + opacity, rotates 180°
// on open (transition covers the `rotate` property via `transition-transform` in Tailwind v4).
// Every Popover-based combobox trigger uses this so the affordance is identical across the app.
export function ComboboxChevron({ open, className }: { open: boolean; className?: string }) {
  return (
    <ChevronDown
      className={cn(
        'size-4 shrink-0 opacity-50 transition-transform duration-200',
        open && 'rotate-180',
        className,
      )}
    />
  );
}
