'use client';

import { forwardRef } from 'react';
import { format, parse } from 'date-fns';
import { CalendarDays } from 'lucide-react';
import { useLocale } from 'next-intl';
import type { Matcher } from 'react-day-picker';

import { Button, Calendar, Popover, PopoverContent, PopoverTrigger } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import { getDateFnsLocale } from '@/lib/i18n/locales';

const DATE_FORMAT_DISPLAY = 'PPP';
const DATE_FORMAT_VALUE = 'yyyy-MM-dd';

interface DatePickerInputProps {
  value?: string;
  onChange?: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  surface?: boolean;
  className?: string;
  // Earliest selectable day, as YYYY-MM-DD. Days before it are greyed out and unclickable.
  minDate?: string;
  // Latest selectable day, as YYYY-MM-DD (e.g. today, for a field that can't be in the future).
  maxDate?: string;
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
      minDate,
      maxDate,
      'aria-invalid': ariaInvalid,
    },
    ref,
  ) => {
    const locale = useLocale();
    const dateFnsLocale = getDateFnsLocale(locale);
    const date = value ? parse(value, DATE_FORMAT_VALUE, new Date()) : undefined;
    const isValidDate = date && !isNaN(date.getTime());
    /*
     * react-day-picker matchers for the bounds that were passed — a LIST rather than one
     * `{ before, after }` object, because that shape reads as a DateInterval (match dates
     * *between* the two) whereas a day is disabled when it matches ANY entry, which is the
     * intent here. Parsed at local midnight, the same anchor the value strings use, so a
     * boundary day stays selectable instead of being excluded by a stray time component.
     */
    const disabledDays: Matcher[] = [];
    if (minDate) disabledDays.push({ before: parse(minDate, DATE_FORMAT_VALUE, new Date()) });
    if (maxDate) disabledDays.push({ after: parse(maxDate, DATE_FORMAT_VALUE, new Date()) });

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
            disabled={disabledDays}
          />
        </PopoverContent>
      </Popover>
    );
  },
);

DatePickerInput.displayName = 'DatePickerInput';

export { DatePickerInput };
