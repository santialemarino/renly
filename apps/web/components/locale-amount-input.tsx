'use client';

import { forwardRef, useEffect, useRef, useState } from 'react';
import cc from 'currency-codes';
import { useLocale } from 'next-intl';

import { Input } from '@repo/ui/components';
import {
  formatAmountForInput,
  getDecimalSeparator,
  normalizeAmountFromInput,
} from '@/lib/utils/locale';
import {
  blockDecimalIfIntegerCurrency,
  blockScientificKeys,
  blockSecondDecimal,
  blockSignKeys,
  blockWrongLocaleDecimal,
  composeKeyHandlers,
  limitDecimalsInString,
  sanitizeDecimalChars,
  sanitizeDecimalPaste,
} from '@/lib/utils/numeric-input';

interface LocaleAmountInputProps {
  value?: string;
  onChange?: (value: string) => void;
  onBlur?: () => void;
  name?: string;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  // ISO 4217 currency code — when set, max fraction digits follows the currency's sub-unit precision (JPY=0, BHD=3, USD/EUR=2). Ignored when `maxDecimals` is set explicitly.
  currency?: string;
  // Explicit override for max fraction digits — takes priority over `currency`. Use `0` to forbid decimals entirely (rare; consider IntegerInput instead). Omit both this and `currency` to allow unlimited decimals (e.g. fractional share quantities).
  maxDecimals?: number;
  'aria-invalid'?: boolean | 'true' | 'false';
}

// Locale-aware decimal amount input. Stores canonical `.`-decimal in form state; displays in the user's locale format (e.g. "1234,56" for es-AR, "1234.56" for en-US). Replaces `<Input type="number" step="0.01">` for amount and quantity fields — fixes Chrome's silent rejection of `1234,56` for ARS users. Rule stack (composable, defined in `lib/utils/numeric-input.ts`): block sign keys, block scientific notation, block the wrong-locale decimal separator, block a second decimal (selection-aware), block the decimal entirely for zero-precision currencies (JPY/KRW); change handler runs `sanitizeDecimalChars` so non-keystroke paths (IME, autofill, drag-drop, programmatic input) can't leak letters or whitespace into form state; paste handler uses "last separator wins" so `"1.234,56"` and `"1,234.56"` both yield 1234.56 regardless of locale; onChange truncates fractional digits to the currency's ISO sub-unit precision.
const LocaleAmountInput = forwardRef<HTMLInputElement, LocaleAmountInputProps>(
  ({ value = '', onChange, onBlur, name, currency, maxDecimals, ...rest }, ref) => {
    const locale = useLocale();
    const decimal = getDecimalSeparator(locale);
    const effectiveMaxDecimals =
      maxDecimals !== undefined
        ? maxDecimals
        : currency
          ? (cc.code(currency)?.digits ?? 2)
          : undefined;

    const [displayValue, setDisplayValue] = useState(() => formatAmountForInput(value, locale));
    const prevLocaleRef = useRef(locale);

    // Re-sync display when canonical value changes externally (e.g. form.reset). Skip on locale switch when the display ends with EITHER separator — the user is mid-typing a decimal and the locale change shouldn't migrate the trailing separator. Value-only changes still run through the round-trip check below, so form.reset keeps working.
    useEffect(() => {
      const localeChanged = prevLocaleRef.current !== locale;
      prevLocaleRef.current = locale;
      if (localeChanged && (displayValue.endsWith('.') || displayValue.endsWith(','))) return;
      if (normalizeAmountFromInput(displayValue, locale) !== value) {
        setDisplayValue(formatAmountForInput(value, locale));
      }
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [value, locale]);

    // Re-truncate display when the precision cap tightens (e.g. user typed 123.45 under USD then switched currency to JPY). Independent from the value/locale resync so a precision change can't be masked by a no-op round-trip.
    useEffect(() => {
      if (effectiveMaxDecimals === undefined) return;
      const limited = limitDecimalsInString(displayValue, decimal, effectiveMaxDecimals);
      if (limited !== displayValue) {
        setDisplayValue(limited);
        onChange?.(normalizeAmountFromInput(limited, locale));
      }
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [effectiveMaxDecimals]);

    function applyValue(next: string) {
      const limited = limitDecimalsInString(next, decimal, effectiveMaxDecimals);
      setDisplayValue(limited);
      onChange?.(normalizeAmountFromInput(limited, locale));
    }

    function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
      applyValue(sanitizeDecimalChars(e.target.value, locale));
    }

    function handlePaste(e: React.ClipboardEvent<HTMLInputElement>) {
      e.preventDefault();
      const pasted = e.clipboardData.getData('text/plain');
      const sanitized = sanitizeDecimalPaste(pasted, locale);
      const input = e.currentTarget;
      const start = input.selectionStart ?? input.value.length;
      const end = input.selectionEnd ?? input.value.length;
      applyValue(input.value.slice(0, start) + sanitized + input.value.slice(end));
    }

    const handleKeyDown = composeKeyHandlers(
      blockSignKeys,
      blockScientificKeys,
      blockWrongLocaleDecimal(locale),
      blockSecondDecimal(locale, displayValue),
      blockDecimalIfIntegerCurrency(locale, effectiveMaxDecimals),
    );

    return (
      <Input
        {...rest}
        ref={ref}
        type="text"
        inputMode="decimal"
        name={name}
        value={displayValue}
        onChange={handleChange}
        onBlur={onBlur}
        onKeyDown={handleKeyDown}
        onPaste={handlePaste}
        autoComplete="off"
      />
    );
  },
);

LocaleAmountInput.displayName = 'LocaleAmountInput';

export { LocaleAmountInput };
