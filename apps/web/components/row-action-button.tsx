'use client';

import type { LucideIcon } from 'lucide-react';

import { Button, Tooltip, TooltipContent, TooltipTrigger } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import { AnimatedIcon } from '@/components/animated-icon';

interface RowActionButtonProps {
  icon: LucideIcon;
  tooltip: string;
  // Hardcoded English accessible name, matching the current aria-labels ("Edit", "Delete", ...).
  ariaLabel: string;
  onClick: (e: React.MouseEvent<HTMLButtonElement>) => void;
  disabled?: boolean;
  // destructive: muted icon turning red on hover (delete). muted: muted icon turning to
  // the foreground color on hover (archive). default: plain ghost (edit / unarchive).
  variant?: 'default' | 'destructive' | 'muted';
}

// Ghost icon button + tooltip used in table row action cells.
export function RowActionButton({
  icon: Icon,
  tooltip,
  ariaLabel,
  onClick,
  disabled,
  variant = 'default',
}: RowActionButtonProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          data-animate-icon
          className={cn(
            'size-8',
            variant === 'destructive' && 'text-muted-foreground hover:text-destructive',
            variant === 'muted' && 'text-muted-foreground hover:text-foreground',
          )}
          onClick={onClick}
          disabled={disabled}
          aria-label={ariaLabel}
        >
          <AnimatedIcon icon={Icon} className="size-4" />
        </Button>
      </TooltipTrigger>
      <TooltipContent>{tooltip}</TooltipContent>
    </Tooltip>
  );
}
