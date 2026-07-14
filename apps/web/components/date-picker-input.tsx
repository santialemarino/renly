'use client';

import { forwardRef } from 'react';
import { format, parse } from 'date-fns';
import { CalendarDays } from 'lucide-react';
import { useLocale } from 'next-intl';

import { Button, Calendar, Popover, PopoverContent, PopoverTrigger } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import { getDateFnsLocale } from '@/lib/utils/locale';

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
    const locale = useLocale();
    const dateFnsLocale = getDateFnsLocale(locale);
    const date = value ? parse(value, DATE_FORMAT_VALUE, new Date()) : undefined;
    const isValidDate = date && !isNaN(date.getTime());

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
              // Default state: regular border, hover hint, blue ring on focus-visible.
              'border-border hover:border-ring',
              'focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50',
              // Aria-invalid: red border, no ring (override Button's built-in aria-invalid:ring-3).
              'aria-invalid:border-destructive aria-invalid:ring-0',
              // Aria-invalid + focus-visible: red ring restored (compound variant wins via specificity).
              'aria-invalid:focus-visible:border-destructive aria-invalid:focus-visible:ring-3 aria-invalid:focus-visible:ring-destructive/30',
              !isValidDate && 'text-muted-foreground',
              className,
            )}
          >
            <CalendarDays className="size-4 shrink-0 text-blue-800" />
            {isValidDate
              ? format(date, DATE_FORMAT_DISPLAY, { locale: dateFnsLocale })
              : placeholder}
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-auto" align="start">
          <Calendar
            blue
            mode="single"
            selected={isValidDate ? date : undefined}
            onSelect={handleSelect}
            locale={dateFnsLocale}
          />
        </PopoverContent>
      </Popover>
    );
  },
);

DatePickerInput.displayName = 'DatePickerInput';

export { DatePickerInput };
