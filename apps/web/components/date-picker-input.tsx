'use client';

import { forwardRef } from 'react';
import { format, parse } from 'date-fns';
import { CalendarDays } from 'lucide-react';

import { Button, Calendar, Popover, PopoverContent, PopoverTrigger } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';

const DATE_FORMAT_DISPLAY = 'PPP';
const DATE_FORMAT_VALUE = 'yyyy-MM-dd';

interface DatePickerInputProps {
  value?: string;
  onChange?: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  surface?: boolean;
  className?: string;
  'aria-invalid'?: boolean | 'true' | 'false';
}

// A form-compatible date picker that stores the value as a YYYY-MM-DD string.
const DatePickerInput = forwardRef<HTMLButtonElement, DatePickerInputProps>(
  (
    {
      value,
      onChange,
      placeholder,
      disabled,
      surface = false,
      className,
      'aria-invalid': ariaInvalid,
    },
    ref,
  ) => {
    const date = value ? parse(value, DATE_FORMAT_VALUE, new Date()) : undefined;
    const isValidDate = date && !isNaN(date.getTime());
    const hasError = ariaInvalid === true || ariaInvalid === 'true';

    function handleSelect(selected: Date | undefined) {
      if (selected) {
        onChange?.(format(selected, DATE_FORMAT_VALUE));
      }
    }

    return (
      <Popover>
        <PopoverTrigger asChild>
          <Button
            ref={ref}
            variant="outline"
            disabled={disabled}
            aria-invalid={ariaInvalid}
            className={cn(
              'h-9 w-full justify-start gap-x-2 px-3 shadow-xs',
              'text-paragraph-sm font-normal',
              'transition-[border-color,box-shadow] duration-200 ease-in-out',
              surface ? 'bg-background' : 'bg-input',
              // Suppress Button's built-in unconditional aria-invalid ring; we only
              // want a destructive ring on focus-visible to match Input's behavior.
              'aria-invalid:ring-0',
              hasError
                ? 'border-destructive focus-visible:border-destructive focus-visible:ring-[3px] focus-visible:ring-destructive/30'
                : 'border-border hover:border-ring focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50',
              !isValidDate && 'text-muted-foreground',
              className,
            )}
          >
            <CalendarDays className="size-4 shrink-0 text-blue-800" />
            {isValidDate ? format(date, DATE_FORMAT_DISPLAY) : placeholder}
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-auto" align="start">
          <Calendar
            blue
            mode="single"
            selected={isValidDate ? date : undefined}
            onSelect={handleSelect}
          />
        </PopoverContent>
      </Popover>
    );
  },
);

DatePickerInput.displayName = 'DatePickerInput';

export { DatePickerInput };
