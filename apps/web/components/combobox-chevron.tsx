import { ChevronDown } from 'lucide-react';

import { cn } from '@repo/ui/lib';

// Single source for a combobox/dropdown trigger chevron. Mirrors the base Select chevron exactly so
// every dropdown trigger's affordance is identical: size-4, opacity-50, muted at rest and fading to
// foreground when the trigger (a `group/button` Button) is hovered, and rotating 180° on open. The
// transition lists `color` and `rotate` explicitly — in Tailwind v4 `rotate-*` sets the `rotate`
// property (not `transform`), so a `transform`-only transition would not animate the rotation.
export function ComboboxChevron({ open, className }: { open: boolean; className?: string }) {
  return (
    <ChevronDown
      className={cn(
        'size-4 shrink-0 opacity-50 text-muted-foreground transition-[color,rotate] duration-200 group-hover/button:text-foreground',
        open && 'rotate-180',
        className,
      )}
    />
  );
}
