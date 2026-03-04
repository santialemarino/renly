'use client';

import * as React from 'react';
import * as RadioGroupPrimitive from '@radix-ui/react-radio-group';
import { CircleIcon } from 'lucide-react';

import { cn } from '@repo/ui/lib';

function RadioGroup({
  className,
  ...props
}: React.ComponentProps<typeof RadioGroupPrimitive.Root>) {
  return (
    <RadioGroupPrimitive.Root
      data-slot="radio-group"
      className={cn('grid gap-3', className)}
      {...props}
    />
  );
}

function RadioGroupItem({
  className,
  blue = false,
  ...props
}: React.ComponentProps<typeof RadioGroupPrimitive.Item> & { blue?: boolean }) {
  return (
    <RadioGroupPrimitive.Item
      data-slot="radio-group-item"
      className={cn(
        'bg-input dark:bg-input/30 aspect-square size-4 shrink-0 rounded-full border shadow-xs transition-all duration-200 outline-none focus-visible:ring-[3px] disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive',
        blue
          ? 'border-blue-800/50 focus-visible:border-blue-800 focus-visible:ring-blue-800/50'
          : 'border-border-3 text-primary focus-visible:border-ring focus-visible:ring-ring/50',
        className,
      )}
      {...props}
    >
      <RadioGroupPrimitive.Indicator
        data-slot="radio-group-indicator"
        forceMount
        className="relative flex items-center justify-center opacity-0 scale-0 data-[state=checked]:opacity-100 data-[state=checked]:scale-100 transition-all duration-200"
      >
        <CircleIcon
          className={cn(
            'absolute top-1/2 left-1/2 size-2 -translate-x-1/2 -translate-y-1/2',
            blue ? 'fill-blue-800' : 'fill-primary',
          )}
        />
      </RadioGroupPrimitive.Indicator>
    </RadioGroupPrimitive.Item>
  );
}

export { RadioGroup, RadioGroupItem };
