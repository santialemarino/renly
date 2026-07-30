'use client';

import type { LucideIcon } from 'lucide-react';

import { Tooltip, TooltipContent, TooltipTrigger } from '@repo/ui/components';

interface RowLockedIndicatorProps {
  icon: LucideIcon;
  tooltip: string;
  // Hardcoded English accessible name, matching the RowActionButton convention.
  ariaLabel: string;
}

/*
 * Non-interactive stand-in for a table row's action buttons when the row is derived and its actions
 * were withheld — it explains the absence exactly where the user looks for the missing buttons.
 * Deliberately NOT a Button (it performs no action, so the cursor-pointer and button semantics would
 * lie) and deliberately NOT a disabled button either: Radix tooltips never fire on a disabled
 * trigger, so an explanatory tooltip there would explain nothing.
 *
 * Focusable so the explanation is reachable by keyboard and not hover-only, with the icon-only
 * focus-visible treatment (a focus-bump driven off the focusable group) since a static muted icon has
 * no hover state to mirror. Matches RowActionButton's size-8 box so the cell keeps its metrics.
 */
export function RowLockedIndicator({ icon: Icon, tooltip, ariaLabel }: RowLockedIndicatorProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          tabIndex={0}
          aria-label={ariaLabel}
          className="group/locked flex size-8 items-center justify-center text-muted-foreground outline-none"
        >
          <Icon className="size-4 group-focus-visible/locked:animate-focus-bump" />
        </span>
      </TooltipTrigger>
      <TooltipContent>{tooltip}</TooltipContent>
    </Tooltip>
  );
}
