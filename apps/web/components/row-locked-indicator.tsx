'use client';

import type { LucideIcon } from 'lucide-react';

import { Tooltip, TooltipContent, TooltipTrigger } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';

interface RowLockedIndicatorProps {
  icon: LucideIcon;
  tooltip: string;
  // Hardcoded English accessible name, matching the RowActionButton convention.
  ariaLabel: string;
  // Box size, defaulting to RowActionButton's. Override to match a denser sub-table's own buttons.
  className?: string;
  iconClassName?: string;
}

/*
 * Non-interactive stand-in for a table row's action button when that action is deliberately withheld —
 * it explains the absence exactly where the user looks for the missing button, so nothing silently
 * vanishes. Deliberately NOT a Button (it performs no action, so the cursor-pointer and button
 * semantics would lie) and deliberately NOT a disabled button either: Radix tooltips never fire on a
 * disabled trigger, so an explanatory tooltip there would never render at all.
 *
 * Focusable so the explanation is reachable by keyboard and not hover-only, with the icon-only
 * focus-visible treatment (a focus-bump driven off the focusable group) since a static muted icon has
 * no hover state to mirror. Defaults to RowActionButton's size-8 box so a row action cell keeps its
 * metrics when the button is swapped out.
 *
 * `role="img"` is load-bearing, not decoration: a bare span maps to role `generic`, on which ARIA
 * PROHIBITS aria-label, so the accessible name can be dropped (Radix adds aria-describedby only while
 * the tooltip is open). Without it a keyboard user can land on a nameless stop.
 */
export function RowLockedIndicator({
  icon: Icon,
  tooltip,
  ariaLabel,
  className,
  iconClassName,
}: RowLockedIndicatorProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          role="img"
          tabIndex={0}
          aria-label={ariaLabel}
          className={cn(
            'group/locked inline-flex size-8 items-center justify-center text-muted-foreground outline-none',
            className,
          )}
        >
          <Icon
            className={cn('size-4 group-focus-visible/locked:animate-focus-bump', iconClassName)}
          />
        </span>
      </TooltipTrigger>
      <TooltipContent>{tooltip}</TooltipContent>
    </Tooltip>
  );
}
