'use client';

import Link from 'next/link';
import type { LucideIcon } from 'lucide-react';

import { Button, Tooltip, TooltipContent, TooltipTrigger } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';

interface RowActionButtonBaseProps {
  icon: LucideIcon;
  /*
   * The action's name, translated, and the button's ACCESSIBLE NAME as well as its tooltip.
   *
   * There is deliberately no second label prop. There was one until the a11y sweep, holding a
   * hardcoded English copy of this same string, and thirteen of the fifty-five had silently drifted
   * from the tooltip beside them ("Revoke invite" against a tooltip reading "Cancel invite") — a
   * second string for one concept, reviewed half as often and translated not at all.
   */
  tooltip: string;
  disabled?: boolean;
  // destructive: muted icon turning red on hover (delete). muted: muted icon turning to
  // the foreground color on hover (archive). default: plain ghost (edit / unarchive).
  variant?: 'default' | 'destructive' | 'muted';
  // Box and icon size, defaulting to a top-level table row's. Override to match a denser sub-table.
  className?: string;
  iconClassName?: string;
  /*
   * E2E target, and the reason it is not the accessible name: that name is translated now, so a spec
   * keyed on it would only pass in whichever locale the run happened to load. One row action per
   * table needs this — the one a spec drives.
   */
  testId?: string;
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
  const {
    icon: Icon,
    tooltip,
    disabled,
    variant = 'default',
    className,
    iconClassName,
    testId,
  } = props;
  const buttonClassName = cn(
    'size-8',
    variant === 'destructive' && 'text-muted-foreground hover:text-destructive',
    variant === 'muted' && 'text-muted-foreground hover:text-foreground',
    className,
  );
  const icon = <Icon className={cn('size-4', iconClassName)} />;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        {props.href ? (
          <Button
            variant="ghost"
            size="icon"
            className={buttonClassName}
            aria-label={tooltip}
            data-testid={testId}
            asChild
          >
            <Link href={props.href}>{icon}</Link>
          </Button>
        ) : (
          <Button
            variant="ghost"
            size="icon"
            className={buttonClassName}
            onClick={props.onClick}
            disabled={disabled}
            aria-label={tooltip}
            data-testid={testId}
          >
            {icon}
          </Button>
        )}
      </TooltipTrigger>
      <TooltipContent>{tooltip}</TooltipContent>
    </Tooltip>
  );
}
