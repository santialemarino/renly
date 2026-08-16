'use client';

import Link from 'next/link';
import type { LucideIcon } from 'lucide-react';

import { Button, Tooltip, TooltipContent, TooltipTrigger } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';

interface RowActionButtonBaseProps {
  icon: LucideIcon;
  tooltip: string;
  // Hardcoded English accessible name, matching the current aria-labels ("Edit", "Delete", ...).
  ariaLabel: string;
  disabled?: boolean;
  // destructive: muted icon turning red on hover (delete). muted: muted icon turning to
  // the foreground color on hover (archive). default: plain ghost (edit / unarchive).
  variant?: 'default' | 'destructive' | 'muted';
}

// Either an action (onClick) or pure navigation (href). A row action that only navigates must render
// a real link so it keeps what a link gives the user for free — open in a new tab, copy address,
// middle-click, prefetch — and so a screen reader announces it as a link rather than a button.
type RowActionButtonProps = RowActionButtonBaseProps &
  (
    | { onClick: (e: React.MouseEvent<HTMLButtonElement>) => void; href?: never }
    | { href: string; onClick?: never }
  );

// Ghost icon button + tooltip used in table row action cells.
export function RowActionButton(props: RowActionButtonProps) {
  const { icon: Icon, tooltip, ariaLabel, disabled, variant = 'default' } = props;
  const className = cn(
    'size-8',
    variant === 'destructive' && 'text-muted-foreground hover:text-destructive',
    variant === 'muted' && 'text-muted-foreground hover:text-foreground',
  );

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        {props.href ? (
          <Button variant="ghost" size="icon" className={className} aria-label={ariaLabel} asChild>
            <Link href={props.href}>
              <Icon className="size-4" />
            </Link>
          </Button>
        ) : (
          <Button
            variant="ghost"
            size="icon"
            className={className}
            onClick={props.onClick}
            disabled={disabled}
            aria-label={ariaLabel}
          >
            <Icon className="size-4" />
          </Button>
        )}
      </TooltipTrigger>
      <TooltipContent>{tooltip}</TooltipContent>
    </Tooltip>
  );
}
