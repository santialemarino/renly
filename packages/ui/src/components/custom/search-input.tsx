'use client';

import * as React from 'react';
import { Search, X } from 'lucide-react';

import { cn } from '@repo/ui/lib';
import { Input } from '../input';
import { useUiLabels } from '../ui-labels';

/*
 * `placeholder` is REQUIRED, and that is the accessibility contract rather than a styling preference:
 * a search field carries no visible <label> anywhere in this app, so the placeholder is the only thing
 * naming it. Requiring it makes "this input has an accessible name" a type error to get wrong, which
 * is why there is no aria-label here — an aria-label equal to the placeholder only makes a screen
 * reader say the same words twice.
 */
interface SearchInputProps extends Omit<React.ComponentProps<typeof Input>, 'endIcon'> {
  placeholder: string;
  onClear?: () => void;
}

function SearchInput({ className, containerClassName, onClear, ...props }: SearchInputProps) {
  const labels = useUiLabels();

  const hasValue = Boolean(props.value);

  return (
    <Input
      containerClassName={cn('min-w-48', containerClassName)}
      startIcon={<Search className="size-4 text-muted-foreground" />}
      endIcon={
        onClear ? (
          <button
            type="button"
            aria-label={labels.clear}
            onClick={(e) => {
              onClear();
              // button → absolute endIcon div → Input container div → querySelector input.
              const container = e.currentTarget.parentElement?.parentElement;
              (container?.querySelector('input') as HTMLInputElement | null)?.focus();
            }}
            tabIndex={hasValue ? 0 : -1}
            className={cn(
              'p-0.5 rounded text-muted-foreground transition-[opacity,transform] duration-150 hover:scale-110 focus-visible:outline-none focus-visible:opacity-100 focus-visible:scale-110',
              hasValue
                ? 'opacity-50 hover:opacity-100 scale-100'
                : 'opacity-0 scale-75 pointer-events-none',
            )}
          >
            <X className="size-3.5" />
          </button>
        ) : undefined
      }
      className={className}
      {...props}
    />
  );
}

export { SearchInput };
