import type { LucideIcon } from 'lucide-react';

import { cn } from '@repo/ui/lib';

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
  action?: React.ReactNode;
  className?: string;
}

// A calm, teaching empty state for first-run users: an icon, a title, and a short description of
// what the section is for. Shown in place of the plain "no rows" text until the user has completed
// onboarding, so a returning user who cleared their data isn't treated as a newbie.
export function EmptyState({ icon: Icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center px-6 py-12 gap-y-3 text-center',
        className,
      )}
    >
      <span className="grid size-12 shrink-0 place-items-center bg-muted rounded-full text-muted-foreground">
        <Icon className="size-6" />
      </span>
      <div className="flex flex-col items-center gap-y-1">
        <span className="text-paragraph-sm-medium">{title}</span>
        <span className="max-w-sm text-paragraph-xs text-muted-foreground">{description}</span>
      </div>
      {action}
    </div>
  );
}
