'use client';

import * as React from 'react';
import { Label as LabelPrimitive } from 'radix-ui';

import { cn } from '@repo/ui/lib';

function Label({
  className,
  blue = false,
  ...props
}: React.ComponentProps<typeof LabelPrimitive.Root> & { blue?: boolean }) {
  return (
    <LabelPrimitive.Root
      data-slot="label"
      className={cn(
        'flex items-center gap-2 text-paragraph-sm-medium select-none group-data-[disabled=true]:pointer-events-none group-data-[disabled=true]:opacity-50 peer-disabled:cursor-not-allowed peer-disabled:opacity-50',
        blue ? 'text-blue-800' : 'text-foreground',
        className,
      )}
      {...props}
    />
  );
}

export { Label };
