'use client';

import * as React from 'react';
import * as CheckboxPrimitive from '@radix-ui/react-checkbox';
import { CheckIcon } from 'lucide-react';

import { cn } from '@repo/ui/lib';

function Checkbox({
  className,
  blue = false,
  ...props
}: React.ComponentProps<typeof CheckboxPrimitive.Root> & { blue?: boolean }) {
  return (
    <CheckboxPrimitive.Root
      data-slot="checkbox"
      className={cn(
        'peer bg-input dark:bg-input/30 size-4 shrink-0 rounded-sm border shadow-xs transition-all duration-200 outline-none focus-visible:ring-[3px] disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive',
        blue
          ? 'border-blue-800/50 data-[state=checked]:bg-blue-800 data-[state=checked]:text-white data-[state=checked]:border-blue-800 focus-visible:border-blue-800 focus-visible:ring-blue-800/50'
          : 'border-border-3 data-[state=checked]:bg-contrast data-[state=checked]:text-background dark:data-[state=checked]:bg-contrast data-[state=checked]:border-contrast focus-visible:border-ring focus-visible:ring-ring/50',
        className,
      )}
      {...props}
    >
      <CheckboxPrimitive.Indicator
        data-slot="checkbox-indicator"
        forceMount
        className="grid place-content-center text-current transition-all duration-200 opacity-0 scale-50 data-[state=checked]:opacity-100 data-[state=checked]:scale-100"
      >
        <CheckIcon className="size-3.5" />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  );
}

export { Checkbox };
