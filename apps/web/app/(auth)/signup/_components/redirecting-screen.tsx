'use client';

import { CircleCheck } from 'lucide-react';

import { cn } from '@repo/ui/lib';

export function RedirectingScreen({
  title,
  description,
  className,
}: {
  title: string;
  description: string;
  className?: string;
}) {
  return (
    <div className={cn('flex flex-col items-center justify-center gap-y-6 py-6', className)}>
      <div className="relative flex items-center justify-center">
        <div className="absolute size-24 rounded-full bg-green-50" />
        <CircleCheck className="relative size-16 text-green-500 animate-in zoom-in-50 duration-500" />
      </div>

      <div className="flex flex-col items-center gap-y-2 text-center">
        <p className="text-paragraph-semibold text-foreground">{title}</p>
        <div className="flex items-center gap-x-2 text-paragraph-sm text-muted-foreground">
          <div className="size-3.5 shrink-0 rounded-full border-2 border-muted-foreground/20 border-t-muted-foreground/70 animate-spin" />
          <span>{description}</span>
        </div>
      </div>
    </div>
  );
}
