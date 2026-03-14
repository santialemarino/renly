import * as React from 'react';

import { cn } from '../lib';

function Textarea({
  className,
  blue = false,
  ...props
}: React.ComponentProps<'textarea'> & { blue?: boolean }) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        'text-foreground placeholder:text-muted-foreground selection:bg-primary selection:text-primary-foreground bg-input w-full md:w-[436px] min-w-0 rounded-lg border p-2 text-paragraph-sm outline-none shadow-xs transition-[color,box-shadow] resize-y disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50',
        'min-h-[76px]',
        'focus-visible:ring-[3px]',
        blue
          ? 'border-blue-800/50 focus-visible:border-blue-800 focus-visible:ring-blue-800/30'
          : 'border-border focus-visible:border-ring focus-visible:ring-ring/50',
        className,
      )}
      {...props}
    />
  );
}

export { Textarea };
