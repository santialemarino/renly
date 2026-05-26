'use client';

import { forwardRef } from 'react';

import { Input } from '@repo/ui/components';
import {
  blockAllSeparators,
  blockScientificKeys,
  blockSignKeys,
  composeKeyHandlers,
  sanitizeIntegerPaste,
} from '@/lib/utils/numeric-input';

interface IntegerInputProps {
  value?: string;
  onChange?: (value: string) => void;
  onBlur?: () => void;
  name?: string;
  placeholder?: string;
  disabled?: boolean;
  surface?: boolean;
  className?: string;
  'aria-invalid'?: boolean | 'true' | 'false';
}

// Natural-number input for fields that store digit-only strings (day-of-month, counts, integer percentages). Replaces `<Input type="number">` and `<Input inputMode="numeric">` everywhere. Rule stack (composable, defined in `lib/utils/numeric-input.ts`): block sign keys, block scientific notation, block both decimal separators. Paste handler strips everything but digits. Range validation stays in Zod — this component only guarantees the value is a digit-only string.
const IntegerInput = forwardRef<HTMLInputElement, IntegerInputProps>(
  ({ value = '', onChange, onBlur, name, ...rest }, ref) => {
    function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
      // Strip any non-digit char that snuck in (e.g. via IME or programmatic input).
      const sanitized = e.target.value.replace(/[^0-9]/g, '');
      onChange?.(sanitized);
    }

    function handlePaste(e: React.ClipboardEvent<HTMLInputElement>) {
      e.preventDefault();
      const pasted = e.clipboardData.getData('text/plain');
      const sanitized = sanitizeIntegerPaste(pasted);
      const input = e.currentTarget;
      const start = input.selectionStart ?? input.value.length;
      const end = input.selectionEnd ?? input.value.length;
      onChange?.(input.value.slice(0, start) + sanitized + input.value.slice(end));
    }

    const handleKeyDown = composeKeyHandlers(
      blockSignKeys,
      blockScientificKeys,
      blockAllSeparators,
    );

    return (
      <Input
        {...rest}
        ref={ref}
        type="text"
        inputMode="numeric"
        name={name}
        value={value}
        onChange={handleChange}
        onBlur={onBlur}
        onKeyDown={handleKeyDown}
        onPaste={handlePaste}
        autoComplete="off"
      />
    );
  },
);

IntegerInput.displayName = 'IntegerInput';

export { IntegerInput };
