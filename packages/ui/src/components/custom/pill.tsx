import * as React from 'react';

import { cn } from '@repo/ui/lib';
import { Button } from '../button';

interface PillProps extends Omit<React.ComponentProps<typeof Button>, 'variant' | 'blue' | 'size'> {
  active?: boolean;
}

function Pill({ active = false, className, ...props }: PillProps) {
  return (
    <Button
      type="button"
      variant="outline"
      blue={active}
      className={cn('rounded-md', className)}
      {...props}
    />
  );
}

export { Pill };
