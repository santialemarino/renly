import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { Slot } from 'radix-ui';

import { cn } from '@repo/ui/lib';

const badgeVariants = cva(
  'inline-flex w-fit shrink-0 items-center justify-center gap-1 overflow-hidden border border-transparent px-2 py-0.5 text-xs font-medium whitespace-nowrap transition-[color,box-shadow] focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 aria-invalid:border-destructive aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 [&>svg]:pointer-events-none [&>svg]:size-3',
  {
    variants: {
      variant: {
        default: 'rounded-full bg-primary text-primary-foreground [a&]:hover:bg-primary/90',
        secondary: 'rounded-full bg-secondary text-secondary-foreground [a&]:hover:bg-secondary/90',
        destructive:
          'rounded-full bg-destructive text-white focus-visible:ring-destructive/20 dark:bg-destructive/60 dark:focus-visible:ring-destructive/40 [a&]:hover:bg-destructive/90',
        outline:
          'rounded-full border-border text-foreground [a&]:hover:bg-accent [a&]:hover:text-accent-foreground',
        ghost: 'rounded-full [a&]:hover:bg-accent [a&]:hover:text-accent-foreground',
        link: 'rounded-full text-primary underline-offset-4 [a&]:hover:underline',
        square: 'py-0 rounded border-border text-muted-foreground font-mono',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  },
);

function Badge({
  className,
  variant = 'default',
  asChild = false,
  blue = false,
  ...props
}: React.ComponentProps<'span'> &
  VariantProps<typeof badgeVariants> & {
    asChild?: boolean;
    blue?: boolean;
  }) {
  const Comp = asChild ? Slot.Root : 'span';

  return (
    <Comp
      data-slot="badge"
      data-variant={variant}
      className={cn(
        badgeVariants({ variant }),
        blue &&
          'bg-blue-800 text-white [a&]:hover:bg-blue-900 focus-visible:ring-blue-800/50 focus-visible:border-blue-800/40 border-transparent',
        className,
      )}
      {...props}
    />
  );
}

export { Badge, badgeVariants };
