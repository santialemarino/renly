'use client';

import * as React from 'react';
import { Label as LabelPrimitive } from 'radix-ui';

import { cn } from '@repo/ui/lib';

function Label({
  className,
  blue = false,
  required = false,
  children,
  ...props
}: React.ComponentProps<typeof LabelPrimitive.Root> & { blue?: boolean; required?: boolean }) {
  return (
    <LabelPrimitive.Root
      data-slot="label"
      className={cn(
        'flex items-center gap-2 text-paragraph-sm-medium select-none group-data-[disabled=true]:pointer-events-none group-data-[disabled=true]:opacity-50 peer-disabled:cursor-not-allowed peer-disabled:opacity-50',
        blue ? 'text-blue-800' : 'text-foreground',
        className,
      )}
      {...props}
    >
      {children}
      {/* Required marker: the single source of the asterisk so every label matches (color + spacing).
          -ml-1 offsets the label's gap-2 so the asterisk sits snug against the text. */}
      {required && (
        <span aria-hidden="true" className="-ml-1 text-blue-800">
          *
        </span>
      )}
    </LabelPrimitive.Root>
  );
}

export { Label };
