'use client';

import * as React from 'react';
import * as SeparatorPrimitive from '@radix-ui/react-separator';

import { cn } from '@repo/ui/lib';

function Separator({
  className,
  orientation = 'horizontal',
  decorative = true,
  blue = false,
  ...props
}: React.ComponentProps<typeof SeparatorPrimitive.Root> & { blue?: boolean }) {
  return (
    <SeparatorPrimitive.Root
      data-slot="separator"
      decorative={decorative}
      orientation={orientation}
      className={cn(
        'shrink-0 data-[orientation=horizontal]:h-px data-[orientation=horizontal]:w-full data-[orientation=vertical]:h-full data-[orientation=vertical]:w-px',
        blue ? 'bg-blue-800/50' : 'bg-border',
        className,
      )}
      {...props}
    />
  );
}

export { Separator };
