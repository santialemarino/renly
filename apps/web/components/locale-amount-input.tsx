'use client';

import { forwardRef, useEffect, useState } from 'react';
import { useLocale } from 'next-intl';

import { Input } from '@repo/ui/components';
import {
  formatAmountForInput,
  getDecimalSeparator,
  normalizeAmountFromInput,
} from '@/lib/utils/locale';

interface LocaleAmountInputProps {
  value?: string;
  onChange?: (value: string) => void;
  onBlur?: () => void;
  name?: string;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  'aria-invalid'?: boolean | 'true' | 'false';
}

// Locale-aware decimal amount input. Stores canonical `.`-decimal in form state; displays in the user's locale format (e.g. "1234,56" for es-AR, "1234.56" for en-US). Replaces `<Input type="number" step="0.01">` for amount and quantity fields — fixes Chrome's silent rejection of `1234,56` for ARS users.
const LocaleAmountInput = forwardRef<HTMLInputElement, LocaleAmountInputProps>(
  ({ value = '', onChange, onBlur, name, ...rest }, ref) => {
    const locale = useLocale();
    const [displayValue, setDisplayValue] = useState(() => formatAmountForInput(value, locale));

    // Re-sync display when canonical value changes externally (e.g. form.reset). Skip when round-tripping the current display would produce the same canonical — avoids clobbering a trailing decimal separator while typing.
    useEffect(() => {
      if (normalizeAmountFromInput(displayValue, locale) !== value) {
        setDisplayValue(formatAmountForInput(value, locale));
      }
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [value, locale]);

    function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
      const newDisplay = e.target.value;
      setDisplayValue(newDisplay);
      onChange?.(normalizeAmountFromInput(newDisplay, locale));
    }

    function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
      // Block sign and scientific notation — preserves the existing `blockNegativeNumberKeys` behavior.
      if (['-', '+', 'e', 'E'].includes(e.key)) {
        e.preventDefault();
        return;
      }
      // Block a second decimal separator.
      const decimal = getDecimalSeparator(locale);
      if (e.key === decimal && displayValue.includes(decimal)) {
        e.preventDefault();
      }
    }

    return (
      <Input
        ref={ref}
        type="text"
        inputMode="decimal"
        name={name}
        value={displayValue}
        onChange={handleChange}
        onBlur={onBlur}
        onKeyDown={handleKeyDown}
        autoComplete="off"
        {...rest}
      />
    );
  },
);

LocaleAmountInput.displayName = 'LocaleAmountInput';

export { LocaleAmountInput };
