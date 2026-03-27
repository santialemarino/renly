'use client';

import * as React from 'react';
import * as SwitchPrimitive from '@radix-ui/react-switch';

import { cn } from '@repo/ui/lib';

interface SwitchProps extends React.ComponentProps<typeof SwitchPrimitive.Root> {
  thumbClassName?: string;
  blue?: boolean;
  surface?: boolean;
}

function Switch({
  className,
  thumbClassName,
  blue = false,
  surface = false,
  ...props
}: SwitchProps) {
  return (
    <SwitchPrimitive.Root
      data-slot="switch"
      className={cn(
        'peer inline-flex h-[1.15rem] w-8 shrink-0 items-center rounded-full border shadow-xs transition-all outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:border-ring disabled:cursor-not-allowed disabled:opacity-50',
        surface
          ? 'data-[state=unchecked]:bg-muted data-[state=unchecked]:border-border'
          : 'data-[state=unchecked]:bg-input data-[state=unchecked]:border-transparent dark:data-[state=unchecked]:bg-input/80',
        blue
          ? 'data-[state=checked]:bg-blue-800 data-[state=checked]:border-blue-800 data-[state=checked]:focus-visible:ring-blue-800/20 data-[state=checked]:focus-visible:border-blue-800/50'
          : 'data-[state=checked]:bg-primary data-[state=checked]:border-primary',
        className,
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb
        data-slot="switch-thumb"
        className={cn(
          'bg-background dark:data-[state=unchecked]:bg-foreground dark:data-[state=checked]:bg-primary-foreground pointer-events-none block size-4 rounded-full ring-0 transition-transform data-[state=checked]:translate-x-[calc(100%-2px)] data-[state=unchecked]:translate-x-0',
          thumbClassName,
        )}
      />
    </SwitchPrimitive.Root>
  );
}

export { Switch };
