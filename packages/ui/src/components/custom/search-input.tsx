'use client';

import * as React from 'react';
import { Search, X } from 'lucide-react';

import { CLOSE_CONTROL, cn } from '@repo/ui/lib';
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
            data-close-kind="field"
            // The `field` clear (lib/close-control): the Input's own focus-within ring is its ring. The
            // negative margin keeps the icon where it sat before the box grew to 24px.
            className={cn(
              CLOSE_CONTROL.field.button,
              '-mr-0.75',
              hasValue ? 'scale-100' : 'opacity-0 scale-75 pointer-events-none',
            )}
          >
            <X className={CLOSE_CONTROL.field.icon} />
          </button>
        ) : undefined
      }
      className={className}
      {...props}
    />
  );
}

export { SearchInput };
