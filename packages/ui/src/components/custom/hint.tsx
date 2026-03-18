import * as React from 'react';

import { cn } from '@repo/ui/lib';

function Hint({ className, ...props }: React.ComponentProps<'p'>) {
  return <p className={cn('text-paragraph-mini text-muted-foreground', className)} {...props} />;
}

export { Hint };
