'use client';

import * as React from 'react';
import * as TooltipPrimitive from '@radix-ui/react-tooltip';

import { cn } from '../lib';

function TooltipProvider({
  delayDuration = 0,
  ...props
}: React.ComponentProps<typeof TooltipPrimitive.Provider>) {
  return (
    <TooltipPrimitive.Provider
      data-slot="tooltip-provider"
      delayDuration={delayDuration}
      {...props}
    />
  );
}

function Tooltip({ ...props }: React.ComponentProps<typeof TooltipPrimitive.Root>) {
  return (
    <TooltipProvider>
      <TooltipPrimitive.Root data-slot="tooltip" {...props} />
    </TooltipProvider>
  );
}

function TooltipTrigger({ ...props }: React.ComponentProps<typeof TooltipPrimitive.Trigger>) {
  return <TooltipPrimitive.Trigger data-slot="tooltip-trigger" {...props} />;
}

function TooltipContent({
  className,
  sideOffset = 0,
  children,
  blue = false,
  ...props
}: React.ComponentProps<typeof TooltipPrimitive.Content> & { blue?: boolean }) {
  return (
    <TooltipPrimitive.Portal>
      <TooltipPrimitive.Content
        data-slot="tooltip-content"
        sideOffset={sideOffset}
        style={{ zIndex: 200 }}
        className={cn(
          'animate-in fade-in-0 zoom-in-95 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2 w-fit origin-(--radix-tooltip-content-transform-origin) rounded-md px-2 py-1.5 text-xs text-balance',
          blue ? 'bg-blue-800 text-white' : 'bg-foreground text-background',
          className,
        )}
        {...props}
      >
        {children}
        <TooltipPrimitive.Arrow
          className={cn(
            'size-2.5 translate-y-[calc(-50%-2px)] rotate-45 rounded-[2px]',
            blue ? 'bg-blue-800 fill-blue-800' : 'bg-foreground fill-foreground',
          )}
        />
      </TooltipPrimitive.Content>
    </TooltipPrimitive.Portal>
  );
}

export { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider };
